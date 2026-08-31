"""Validator for the DBM SAAODB source (14 .htm + 47 .pdf).

Contract: ``data/reference/schemas/saaodb.json``. The completeness gate is the
quarterly grid 2011Q1..2026Q1 (61 successive quarters). The .htm files are
self-describing HTML tables; the .pdf files get L1 integrity + header-vocab
checks now, with deep table parsing deferred to M3.
"""

from __future__ import annotations

import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from src.core.config import CONFIG as cfg
from src.validation.base import (
    SEVERITY_MUST,
    SEVERITY_SHOULD,
    BaseValidator,
    ValidationReport,
    ValidationResult,
)

_FILENAME_Q_RE = re.compile(r"(20\d{2})\s*[-_]?[Qq]([1-4])")
_EXT_UP_TO = (2014, 2)          # quarters <= (2014,2) must be .htm
_DBM_URL = cfg["DBM_SAAODB_URL"]
_HEADERS = {"User-Agent": cfg["HEADERS"]["User-Agent"]}

_LIVE_YEAR_Q_RE = re.compile(r"(20\d{2})\s*[-_]?[Qq]([1-4])")
_LIVE_ORDINAL_RE = re.compile(r"SAOB(20\d{2})[^>]{0,60}?(1st|2nd|3rd|4th)", re.IGNORECASE)
_ORDINAL_TO_Q = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4}


def _quarter_grid(start_year, start_quarter, end_year, end_quarter):
    """All (year, quarter) pairs in the inclusive quarterly grid."""
    pairs, y, q = [], start_year, start_quarter
    while (y, q) <= (end_year, end_quarter):
        pairs.append((y, q))
        if q == 4:
            y, q = y + 1, 1
        else:
            q += 1
    return pairs


def _normalise(text: str) -> str:
    """Uppercase, punctuation removed, whitespace collapsed."""
    return " ".join(re.sub(r"[^A-Z0-9]", " ", text.upper()).split())


class SAAODBValidator(BaseValidator):
    """Validates data/raw/saaodb/ against the SAAODB expected-schema artifact."""

    source = "saaodb"
    source_label = "DBM SAAODB (Statement of Appropriations...)"

    # -- helpers ------------------------------------------------------------

    def _on_disk_pairs(self) -> set:
        pairs = set()
        for p in (self.raw_dir / "saaodb").glob("*"):
            if not p.is_file():
                continue
            m = _FILENAME_Q_RE.search(p.name)
            if m:
                pairs.add((int(m.group(1)), int(m.group(2))))
        return pairs

    def _check_htm(self, rep, path: Path) -> None:
        name = path.name
        try:
            soup = BeautifulSoup(
                path.read_text(encoding="utf-8", errors="replace"), "html.parser"
            )
        except OSError as e:
            rep.add(ValidationResult(
                "saaodb.htm_readable", SEVERITY_MUST, False,
                detail="%s unreadable: %s" % (name, e), actual=name, expected="readable"))
            return
        rep.add(ValidationResult(
            "saaodb.htm_readable", SEVERITY_MUST, True,
            detail="%s parsed OK" % name, actual=name, expected="readable"))
        tables = soup.find_all("table")
        text = _normalise(soup.get_text(" ", strip=True))
        vocab_ok = all(tok in text for tok in
                       ("STATEMENT OF ALLOTMENT", "ALLOTMENT", "OBLIGATIONS", "UNOBLIGATED"))
        rep.add(ValidationResult(
            "saaodb.htm_header_vocab", SEVERITY_MUST, vocab_ok,
            detail="%s table text must carry ALLOTMENT/OBLIGATIONS/UNOBLIGATED vocabulary" % name,
            actual=len(tables), expected=4))
        group_ok = False
        for tr in (tables[0].find_all("tr") if tables else []):
            cells = [_normalise(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
            joined = " ".join(cells)
            if all(tok in joined for tok in ("PS", "MOOE", "CO", "TOTAL")):
                group_ok = True
                break
        rep.add(ValidationResult(
            "saaodb.htm_expense_group_header", SEVERITY_MUST, group_ok,
            detail="%s must expose a PS/MOOE/CO/TOTAL group header row" % name,
            actual=name, expected="group header row"))

    # -- pdf + live checks --------------------------------------------------

    def _check_pdf(self, rep, path: Path) -> None:
        name = path.name
        with open(path, "rb") as f:
            magic = f.read(4)
        rep.add(ValidationResult(
            "saaodb.pdf_magic", SEVERITY_MUST, magic == b"%PDF",
            detail="%s magic bytes %r" % (name, magic), actual=magic, expected=b"%PDF"))
        try:
            reader = PdfReader(str(path))
            n_pages = len(reader.pages)
        except Exception as e:  # noqa: BLE001 — corrupt/truncated PDF
            rep.add(ValidationResult(
                "saaodb.pdf_openable", SEVERITY_MUST, False,
                detail="%s cannot open: %s" % (name, e), actual=name, expected="openable"))
            return
        rep.add(ValidationResult(
            "saaodb.pdf_openable", SEVERITY_MUST, True,
            detail="%s opened (%d pages)" % (name, n_pages), actual=n_pages, expected=">0"))
        rep.add(ValidationResult(
            "saaodb.pdf_min_pages", SEVERITY_SHOULD, n_pages >= 2,
            detail="%s page count %d" % (name, n_pages), actual=n_pages, expected=">=2"))
        first_text = ""
        try:
            first_text = (reader.pages[0].extract_text() or "")
        except Exception:  # noqa: BLE001
            pass
        norm = _normalise(first_text)
        vocab_ok = ("ALLOTMENT" in norm or "APPROPRIATIONS" in norm) and "OBLIGATION" in norm
        rep.add(ValidationResult(
            "saaodb.pdf_header_vocab", SEVERITY_SHOULD, vocab_ok,
            detail="%s first-page fiscal vocabulary present" % name,
            actual=name, expected="ALLOTMENT/APPROPRIATIONS + OBLIGATION"))

    def _live_source_max_pair(self):
        """Fetch the DBM page; newest quarter it lists, or None when unreachable/skipped."""
        if self.skip_live:
            return None
        try:
            r = requests.get(_DBM_URL, timeout=15, headers=_HEADERS)
            r.raise_for_status()
        except Exception:  # noqa: BLE001 — network unreachable
            return None
        pairs = {(int(m.group(1)), int(m.group(2)))
                 for m in _LIVE_YEAR_Q_RE.finditer(r.text)}
        for m in _LIVE_ORDINAL_RE.finditer(r.text):
            pairs.add((int(m.group(1)), _ORDINAL_TO_Q[m.group(2).lower()]))
        return max(pairs) if pairs else None

    # -- main ---------------------------------------------------------------

    def validate(self) -> ValidationReport:
        schema = self.load_schema()
        rep = self.report()
        rep.add(self.register_schema_check())
        grid = schema["coverage"]["grid"]
        expected_pairs = set(_quarter_grid(
            grid["start_year"], grid["start_quarter"],
            grid["end_year"], grid["end_quarter"],
        ))

        saaodb_dir = self.raw_dir / "saaodb"
        files = sorted(p for p in saaodb_dir.glob("*") if p.is_file())
        htm = [p for p in files if p.suffix.lower() == ".htm"]
        pdf = [p for p in files if p.suffix.lower() == ".pdf"]
        other = [p.name for p in files if p.suffix.lower() not in (".htm", ".pdf")]

        rep.add(ValidationResult(
            "saaodb.file_count", SEVERITY_MUST, len(files) == 61,
            detail="%d files (htm=%d, pdf=%d, other=%d) vs expected 61"
            % (len(files), len(htm), len(pdf), len(other)),
            actual=len(files), expected=61))
        rep.add(ValidationResult(
            "saaodb.no_foreign_formats", SEVERITY_SHOULD, not other,
            detail="unexpected non-htm/pdf files: %s" % (other or "none"),
            actual=other or None, expected="[]"))

        # coverage: every quarter in the grid has exactly one file ----------
        on_disk = self._on_disk_pairs()
        rep.add(ValidationResult(
            "saaodb.quarter_coverage", SEVERITY_MUST, on_disk == expected_pairs,
            detail="quarters on disk=%d expected=%d; missing=%s extra=%s"
            % (len(on_disk), len(expected_pairs),
               sorted(expected_pairs - on_disk)[:6], sorted(on_disk - expected_pairs)[:6]),
            actual=len(on_disk), expected=len(expected_pairs)))

        # extension follows the series boundary -----------------------------
        ext_ok = True
        for y, q in sorted(on_disk):
            want_htm = (y, q) <= _EXT_UP_TO
            m = None
            for p in files:
                mm = _FILENAME_Q_RE.search(p.name)
                if mm and (int(mm.group(1)), int(mm.group(2))) == (y, q):
                    m = p
                    break
            if m is not None:
                is_htm = m.suffix.lower() == ".htm"
                if is_htm != want_htm:
                    ext_ok = False
                    rep.add(ValidationResult(
                        "saaodb.extension_by_period", SEVERITY_MUST, False,
                        detail="%s should be %s" % (m.name, "htm" if want_htm else "pdf"),
                        actual=m.suffix, expected="htm" if want_htm else "pdf"))
        if ext_ok:
            rep.add(ValidationResult(
                "saaodb.extension_by_period", SEVERITY_MUST, True,
                detail="all files use the expected format for their period",
                actual=len(files), expected="htm<=2014Q2, pdf>=2014Q3"))

        # -- per-file structural checks (PART3 continues) --
        for p in htm:
            self._check_htm(rep, p)
        for p in pdf:
            self._check_pdf(rep, p)

        # live drift detector (source published beyond our coverage?) --------
        if self.skip_live:
            rep.add(ValidationResult(
                "saaodb.live_source_drift", SEVERITY_SHOULD, True,
                detail="skipped via --skip-live", actual="skipped", expected="live fetch"))
        else:
            max_pair = self._live_source_max_pair()
            end = (grid["end_year"], grid["end_quarter"])
            if max_pair is None:
                rep.add(ValidationResult(
                    "saaodb.live_source_drift", SEVERITY_SHOULD, True,
                    detail="source unreachable or no quarters found - drift check unresolved",
                    actual=None, expected=end))
            else:
                fresh = max_pair > end
                rep.add(ValidationResult(
                    "saaodb.live_source_drift", SEVERITY_SHOULD, not fresh,
                    detail="source now lists up to %dQ%d (our coverage ends %dQ%d)"
                    % (max_pair[0], max_pair[1], end[0], end[1]),
                    actual=max_pair, expected=end))
        return rep