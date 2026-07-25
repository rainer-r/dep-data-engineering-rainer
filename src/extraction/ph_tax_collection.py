import os
import re
import time
import random
import json
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.core.config import CONFIG as cfg
from src.extraction.base import BaseExtractor

# Selenium for dynamic content fallback
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
except ImportError:
    webdriver = None


class TaxCollectionExtractor(BaseExtractor):
    """Resilient Scraper Extractor for BIR Tax Collection Statistics."""

    def __init__(self, use_selenium: bool = True):
        super().__init__(name="ph_tax_collection")
        self.target_url = cfg["BIR_TARGET_URL"]
        self.output_dir: Path = cfg["BIR_RAW_DIR"]
        self.use_selenium = use_selenium

    def harvest_links(self) -> List[str]:
        self.logger.info(f"Harvesting links from {self.target_url}")
        
        parsed_input = urlparse(self.target_url)
        if parsed_input.path.lower().endswith(('.xlsx', '.xls')):
            self.logger.info(f"Input URL is a direct file download: {self.target_url}")
            return [self.target_url]

        try:
            response = requests.get(self.target_url, headers=cfg["HEADERS"], timeout=cfg["TIMEOUT"])
            response.raise_for_status()
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch page {self.target_url}: {e}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        links = []
        
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(self.target_url, href)
            parsed_url = urlparse(full_url)
            if parsed_url.path.lower().endswith(('.xlsx', '.xls')):
                links.append(full_url)

        next_data_script = soup.find("script", id="__NEXT_DATA__")
        if next_data_script:
            try:
                data = json.loads(next_data_script.string)
                def find_urls(obj):
                    found = []
                    if isinstance(obj, str):
                        if obj.lower().endswith(('.xlsx', '.xls')) or (urlparse(obj).path.lower().endswith(('.xlsx', '.xls'))):
                            found.append(urljoin(self.target_url, obj))
                    elif isinstance(obj, dict):
                        for v in obj.values():
                            found.extend(find_urls(v))
                    elif isinstance(obj, list):
                        for item in obj:
                            found.extend(find_urls(item))
                    return found
                links.extend(find_urls(data))
            except (json.JSONDecodeError, TypeError) as e:
                self.logger.warning(f"Failed to parse __NEXT_DATA__: {e}")

        url_pattern = re.compile(r'["\'](https?://[^"\']+\.(?:xlsx|xls)[^"\']*|/[^"\']+\.(?:xlsx|xls)[^"\']*)["\']')
        for script in soup.find_all("script"):
            if script.string and "self.__next_f.push" in script.string:
                matches = url_pattern.findall(script.string.replace("\\/", "/"))
                for match in matches:
                    links.append(urljoin(self.target_url, match))

        if not links and self.use_selenium and webdriver and Options:
            self.logger.info("No Excel links found in static HTML; attempting Selenium render.")
            try:
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument(f"user-agent={cfg['HEADERS']['User-Agent']}")
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                driver = webdriver.Chrome(options=chrome_options)
                try:
                    driver.get(self.target_url)
                    driver.implicitly_wait(10)
                    page_source = driver.page_source
                finally:
                    driver.quit()

                soup = BeautifulSoup(page_source, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    full_url = urljoin(self.target_url, href)
                    if urlparse(full_url).path.lower().endswith((".xlsx", ".xls")):
                        links.append(full_url)
            except Exception as e:
                self.logger.warning(f"Selenium rendering failed: {e}")
        elif not links and not self.use_selenium:
            self.logger.info("Selenium disabled (--no-selenium); skipping dynamic rendering fallback.")

        deduped = list(set(links))
        self.logger.info(f"Found {len(deduped)} potential Excel files.")
        return deduped

    def download_file(self, url: str, manifest: Dict) -> Optional[Path]:
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = f"download_{int(time.time())}.xlsx"
        
        target_path = self.output_dir / filename
        rel_path = str(target_path.relative_to(cfg["RAW_DATA_DIR"]))
        
        if target_path.exists():
            current_hash = self.calculate_sha256(target_path)
            if manifest.get(rel_path, {}).get("checksum") == current_hash:
                self.logger.info(f"Skipping {filename} - checksum matches manifest.")
                return target_path

        attempt = 0
        while attempt < cfg["MAX_RETRIES"]:
            temp_path = target_path.with_suffix(target_path.suffix + ".tmp")
            try:
                self.logger.info(f"Downloading {url} (Attempt {attempt + 1})")
                delay = random.uniform(*cfg["DELAY_RANGE"])
                time.sleep(delay)

                with requests.get(url, headers=cfg["HEADERS"], stream=True, timeout=cfg["TIMEOUT"]) as r:
                    r.raise_for_status()
                    with open(temp_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=cfg["CHUNK_SIZE"]):
                            if chunk:
                                f.write(chunk)
                    
                    checksum = self.calculate_sha256(temp_path)
                    os.replace(temp_path, target_path)
                    
                    manifest[rel_path] = {
                        "source": "bir_tax_collection",
                        "url": url,
                        "filename": filename,
                        "relative_path": rel_path,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "size_bytes": target_path.stat().st_size,
                        "checksum": checksum,
                    }
                    self.logger.info(f"Successfully downloaded {filename}")
                    return target_path

            except (requests.RequestException, IOError) as e:
                attempt += 1
                if temp_path.exists():
                    temp_path.unlink()
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                self.logger.warning(f"Error downloading {url}: {e}. Retrying in {wait_time:.2f}s...")
                time.sleep(wait_time)

        self.logger.error(f"Failed to download {url} after {cfg['MAX_RETRIES']} attempts.")
        return None

    def extract(self) -> bool:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        manifest = self.load_manifest()
        links = self.harvest_links()
        
        if not links:
            self.logger.warning("No BIR tax files found to download.")
            return False

        success_count = 0
        for link in links:
            if self.download_file(link, manifest):
                success_count += 1
                self.save_manifest(manifest)

        self.logger.info(f"Tax collection ingestion complete. Downloaded {success_count}/{len(links)} files.")
        return success_count > 0


def main():
    """Standalone entrypoint for debugging.

    Uses the runner's root logger for proper console + file output.
    To run: ``python src/extraction/ph_tax_collection.py``
    """
    from src.orchestration.runner import setup_root_logger
    setup_root_logger()
    extractor = TaxCollectionExtractor()
    extractor.extract()


if __name__ == "__main__":
    main()
