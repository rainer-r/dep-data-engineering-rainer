"""
TaxTracePH — DBM SAAODB Extractor

Extracts Statement of Appropriations, Allotments, Obligations, Disbursements,
and Balances (SAAODB) reports from the DBM website (2011-2026).

Scrapes the DBM WordPress page for ``.htm``, ``.pdf``, and ``.xlsx`` download
links using static HTML parsing (``requests`` + ``BeautifulSoup``). No Selenium
is needed because all links are embedded in the static page HTML.

For each year (2011-2026) and quarter (Q1-Q4), the extractor selects the
"best" file to download using a priority system:

  Priority 1: Final - Month DD, YYYY  (named date in Final)
  Priority 2: Final Revised
  Priority 3: Final                    (bare "Final")
  Priority 4: Updated - Month DD, YYYY (named date in Updated)
  Priority 5: Updated                  (bare "Updated")
  Priority 6: Preliminary              (any Preliminary variant)
  Priority 7: Bare quarter name        (e.g. "2nd Quarter")

Within the same priority level, ``.pdf`` is preferred over ``.htm``.
Links with text "Download Excel" or ".xlsx" extension are skipped.
"""

import os
import re
import time
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.core.config import CONFIG as cfg
from src.extraction.base import BaseExtractor


# Ensure the SAAODB raw data directory exists on import
cfg["SAAODB_RAW_DIR"].mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Link-text priority scoring
# ---------------------------------------------------------------------------

def score_link_text(text: str) -> int:
    """Score a link's display text by status priority (lower = better).

    Priority order:
      1 = Final with a named date       (e.g. "Final - July 9, 2024")
      2 = Final Revised                 (e.g. "(Final-Revised)")
      3 = Final (bare)                  (e.g. "Final", "(Final)")
      4 = Updated with a named date     (e.g. "Updated - May 29, 2023")
      5 = Updated (bare)                (e.g. "Updated", "(Updated)")
      6 = Preliminary                   (any text containing "Preliminary")
      7 = Fallback / bare quarter name  ("1st Quarter", "2nd Quarter", etc.)

    Returns 99 for links that should be skipped entirely (e.g. "Download Excel").
    """
    t = text.strip().lower()

    # Skip download-excel links
    if "download excel" in t or "download" in t or "excel" in t:
        return 99

    # Remove leading/trailing parentheses for matching
    clean = t.strip("() ")

    # Priority 1: Final with date
    if "final -" in t and re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december)", t):
        return 1
    if "final" in t and not "preliminary" in t and re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", t, re.IGNORECASE):
        return 1

    # Priority 2: Final Revised
    if "final" in clean and "revised" in clean:
        return 2

    # Priority 3: Final (bare)
    if clean == "final" or t == "(final)":
        return 3

    # Priority 4: Updated with date (but not Preliminary-Updated)
    if "updated" in t and "preliminary" not in t and re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december)", t):
        return 4
    if "updated" in t and "preliminary" not in t and re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", t, re.IGNORECASE):
        return 4

    # Priority 5: Updated (bare)
    if clean == "updated" or t == "(updated)":
        return 5

    # Priority 6: Preliminary (also catches "Preliminary-Updated")
    if "preliminary" in t or "prelim" in t:
        return 6

    # Priority 7: Bare quarter name or anything else
    return 7


# ---------------------------------------------------------------------------
# Year / quarter detection from URL path
# ---------------------------------------------------------------------------

_QUARTER_PATTERNS = [
    # Modern style: /1stQuarter/, /2ndQuarter/, /2nd_Quarter/, etc.
    (r"(?:/|^)1stQuarter", "Q1"),
    (r"(?:/|^)2ndQuarter", "Q2"),
    (r"(?:/|^)2nd_Quarter", "Q2"),
    (r"(?:/|^)3rdQuarter", "Q3"),
    (r"(?:/|^)4thQuarter", "Q4"),
    (r"(?:/|^)4th_Quarter", "Q4"),
    # /Q1/, /Q2/, /Q3/, /Q4/ (2015 style)
    (r"/Q1/", "Q1"),
    (r"/Q2/", "Q2"),
    (r"/Q3/", "Q3"),
    (r"/Q4/", "Q4"),
]


def detect_year(href: str) -> Optional[str]:
    """Extract 4-digit year from ``/SAOB{YYYY}/`` pattern."""
    m = re.search(r"/SAOB(\d{4})/", href)
    if m:
        return m.group(1)
    return None


def detect_quarter(href: str, text: str, year: str) -> str:
    """Detect quarter (Q1-Q4) from URL path, falling back to link text.

    Uses path patterns first. For older years (2011-2014) where the URL
    structure is inconsistent, falls back to month names or ordinal text
    in the link text.
    """
    # Try path-based patterns first
    for pattern, q in _QUARTER_PATTERNS:
        if re.search(pattern, href, re.IGNORECASE):
            return q

    if not year:
        return "?"

    year_int = int(year)

    # ---- 2011-2013: URL contains month-like indicators ----
    if year_int <= 2013:
        t = text.lower()
        # Check URL for clues (these years have varied filenames)
        if any(x in href for x in ["SAOB2.htm", "SAOB2_", "March", "1stQ"]):
            return "Q1"
        if any(x in href for x in ["June", "2ndQ", "FirstQ"]):
            return "Q2"
        if any(x in href for x in ["Sept", "3rdQ"]):
            return "Q3"
        if any(x in href for x in ["Dec", "4th", "4TH"]):
            return "Q4"
        # Fallback to text
        if "1st" in t or "first" in t:
            return "Q1"
        if "2nd" in t or "second" in t:
            return "Q2"
        if "3rd" in t or "third" in t:
            return "Q3"
        if "4th" in t or "fourth" in t:
            return "Q4"
        return "?"

    # ---- 2014: inconsistent paths, rely on text ----
    if year_int == 2014:
        t = text.lower()
        if "1st" in t:
            return "Q1"
        if "2nd" in t or "2ND" in href:
            return "Q2"
        if "3rd" in t or "3rd" in href:
            return "Q3"
        if "4th" in t or "4TH" in href or "Preliminary" in t or "FINAL" in href:
            return "Q4"
        return "?"

    # Default fallback: try ordinal in text
    t = text.lower()
    if "1st" in t or "first" in t:
        return "Q1"
    if "2nd" in t or "second" in t:
        return "Q2"
    if "3rd" in t or "third" in t:
        return "Q3"
    if "4th" in t or "fourth" in t:
        return "Q4"

    return "?"


# ---------------------------------------------------------------------------
# Extractor class
# ---------------------------------------------------------------------------

class DBMSAAODBExtractor(BaseExtractor):
    """Extractor for DBM SAAODB reports (2011-2026).

    Scrapes the DBM WordPress page for all downloadable report links,
    groups them by year and quarter, then selects the best file for each
    quarter based on status priority and file format preference.

    Downloads only ``.htm`` and ``.pdf`` files (``.xlsx`` is skipped).

    See module docstring for the priority scheme.
    """

    def __init__(self, **kwargs):
        super().__init__(name="ph_saaodb", **kwargs)
        self.target_url: str = cfg["DBM_SAAODB_URL"]
        self.output_dir: Path = cfg["SAAODB_RAW_DIR"]

    # ------------------------------------------------------------------
    # Link harvesting
    # ------------------------------------------------------------------

    def harvest_links(self) -> List[dict]:
        """Scrape the DBM page for all download links.

        Returns a list of dicts with keys:
          - year:     str (e.g., "2016")
          - quarter:  str (e.g., "Q2")
          - text:     str (link display text)
          - url:      str (absolute download URL)
          - ext:      str (``htm``, ``pdf``, or ``xlsx``)
          - score:    int (priority score, 1-7 or 99 for skip)
        """
        self.logger.info(f"Harvesting links from {self.target_url}")

        try:
            response = requests.get(
                self.target_url,
                headers=cfg["HEADERS"],
                timeout=cfg["TIMEOUT"],
            )
            response.raise_for_status()
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch page {self.target_url}: {e}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        raw_links: List[dict] = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)
            full_url = urljoin(self.target_url, href)

            # Determine file extension
            ext = None
            if ".xlsx" in href.lower():
                ext = "xlsx"
            elif ".xls" in href.lower():
                ext = "xlsx"
            elif ".pdf" in href.lower():
                ext = "pdf"
            elif ".htm" in href.lower() or ".html" in href.lower():
                ext = "htm"

            if ext is None:
                continue

            # Determine year
            year = detect_year(href)
            if year is None:
                continue

            # Determine quarter
            quarter = detect_quarter(href, text, year)
            if quarter == "?":
                continue

            raw_links.append({
                "year": year,
                "quarter": quarter,
                "text": text,
                "url": full_url,
                "ext": ext,
                "score": score_link_text(text),
            })

        self.logger.info(
            f"Found {len(raw_links)} total download links across "
            f"{len(set(l['year'] for l in raw_links))} years."
        )
        return raw_links

    # ------------------------------------------------------------------
    # Priority-based selection: best file per (year, quarter)
    # ------------------------------------------------------------------

    def select_best_files(self, links: List[dict]) -> List[dict]:
        """Select the single best file per (year, quarter) by priority.

        Selection logic:
          1. Filter out ``xlsx`` links entirely (user preference).
          2. Group by (year, quarter).
          3. Within each group, find the minimum (best) score.
          4. Among links with the best score, prefer ``.pdf`` over ``.htm``.
          5. Return exactly one link per (year, quarter).

        Returns a list of link dicts (one per selected file).
        """
        # Filter out xlsx
        non_xlsx = [l for l in links if l["ext"] != "xlsx" and l["score"] < 99]

        # Group by (year, quarter)
        from collections import defaultdict
        groups: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
        for link in non_xlsx:
            key = (link["year"], link["quarter"])
            groups[key].append(link)

        selected: List[dict] = []
        for key, group in sorted(groups.items()):
            # Find best score
            best_score = min(l["score"] for l in group)
            candidates = [l for l in group if l["score"] == best_score]

            # Prefer PDF over HTM at same score
            pdfs = [l for l in candidates if l["ext"] == "pdf"]
            if pdfs:
                chosen = pdfs[0]
            else:
                chosen = candidates[0]

            selected.append(chosen)

        years_covered = sorted(set(l["year"] for l in selected))
        quarters_covered = len(selected)
        self.logger.info(
            f"Selected {quarters_covered} best files across "
            f"{len(years_covered)} years: {years_covered[0]}–{years_covered[-1]}"
        )
        return selected

    # ------------------------------------------------------------------
    # File download with manifest tracking
    # ------------------------------------------------------------------

    def download_file(self, link: dict, manifest: Dict) -> Optional[Path]:
        """Download a single file with retry, checksum, and manifest tracking.

        Uses SHA-256 checksums for idempotency — skips if the file is
        already on disk with a matching checksum.

        Parameters
        ----------
        link:
            Dict with keys ``year``, ``quarter``, ``text``, ``url``, ``ext``.
        manifest:
            The current manifest dict, mutated in-place on success.

        Returns
        -------
        ``Path`` of the downloaded file, or ``None`` on failure.
        """
        url = link["url"]
        year = link["year"]
        quarter = link["quarter"]
        ext = link["ext"]
        text = link["text"]

        # Build a unique filename: {year}_{quarter}_{text_slug}.{ext}
        # Sanitise the text portion for filesystem safety
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", text).strip("_")
        if not slug:
            slug = f"{year}_{quarter}"
        if len(slug) > 80:
            slug = slug[:80]
        filename = f"{year}_{quarter}_{slug}.{ext}"

        target_path = self.output_dir / filename
        rel_path = str(target_path.relative_to(cfg["RAW_DATA_DIR"]))

        # Idempotency check
        if target_path.exists():
            current_hash = self.calculate_sha256(target_path)
            if manifest.get(rel_path, {}).get("checksum") == current_hash:
                self.logger.info(
                    f"Skipping {filename} — checksum matches manifest."
                )
                return target_path

        # Download with retry/backoff
        attempt = 0
        while attempt < cfg["MAX_RETRIES"]:
            temp_path = target_path.with_suffix(target_path.suffix + ".tmp")
            try:
                delay = random.uniform(*cfg["DELAY_RANGE"])
                time.sleep(delay)

                self.logger.info(
                    f"Downloading {filename} [{year} {quarter}] "
                    f"(attempt {attempt + 1}/{cfg['MAX_RETRIES']})"
                )

                with requests.get(
                    url,
                    headers=cfg["HEADERS"],
                    stream=True,
                    timeout=cfg["TIMEOUT"],
                ) as r:
                    r.raise_for_status()
                    with open(temp_path, "wb") as f:
                        for chunk in r.iter_content(
                            chunk_size=cfg["CHUNK_SIZE"]
                        ):
                            if chunk:
                                f.write(chunk)

                checksum = self.calculate_sha256(temp_path)
                os.replace(temp_path, target_path)

                manifest[rel_path] = {
                    "source": "dbm_saaodb",
                    "url": url,
                    "filename": filename,
                    "relative_path": rel_path,
                    "year": year,
                    "quarter": quarter,
                    "link_text": text,
                    "timestamp": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    ),
                    "size_bytes": target_path.stat().st_size,
                    "checksum": checksum,
                }
                self.logger.info(
                    f"Successfully downloaded {filename} "
                    f"({target_path.stat().st_size:,} bytes)"
                )
                return target_path

            except (requests.RequestException, IOError) as e:
                attempt += 1
                if temp_path.exists():
                    temp_path.unlink()
                wait_time = (2**attempt) + random.uniform(0, 1)
                self.logger.warning(
                    f"Error downloading {url}: {e}. "
                    f"Retrying in {wait_time:.2f}s..."
                )
                time.sleep(wait_time)

        self.logger.error(
            f"Failed to download {filename} after "
            f"{cfg['MAX_RETRIES']} attempts."
        )
        return None

    # ------------------------------------------------------------------
    # Main extraction workflow
    # ------------------------------------------------------------------

    def extract(self) -> bool:
        """Execute the full SAAODB extraction workflow.

        Steps
        -----
        1. Fetch the DBM page and harvest all download links.
        2. Select the best file for each (year, quarter) by priority.
        3. Download each selected file with manifest tracking.
        4. Report success / failure.

        Returns ``True`` if at least one new file was downloaded,
        ``False`` otherwise.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        manifest = self.load_manifest()
        raw_links = self.harvest_links()

        if not raw_links:
            self.logger.warning(
                "No DBM SAAODB links found on page."
            )
            return False

        selected = self.select_best_files(raw_links)

        if not selected:
            self.logger.warning(
                "No DBM SAAODB files selected for download."
            )
            return False

        success_count = 0
        for link in selected:
            result = self.download_file(link, manifest)
            if result:
                success_count += 1
                self.save_manifest(manifest)

        self.logger.info(
            f"SAAODB ingestion complete. "
            f"Downloaded {success_count}/{len(selected)} file(s) "
            f"across {len(set(l['year'] for l in selected))} years."
        )
        return success_count > 0


def main():
    """Standalone entrypoint for debugging.

    Uses the runner's root logger for proper console + file output.
    To run: ``python src/extraction/ph_saaodb.py``
    """
    from src.orchestration.runner import setup_root_logger

    setup_root_logger()
    extractor = DBMSAAODBExtractor()
    extractor.extract()


if __name__ == "__main__":
    main()