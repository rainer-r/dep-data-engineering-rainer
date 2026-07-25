import random
import time
from pathlib import Path
from typing import Dict, List, Optional

from huggingface_hub import HfApi, hf_hub_download

from src.core.config import CONFIG as cfg
from src.extraction.base import BaseExtractor


class GAAExtractor(BaseExtractor):
    """Extractor for Hugging Face General Appropriations Act (GAA) dataset with idempotent file-by-file downloads."""

    def __init__(self):
        super().__init__(name="ph_gaa")
        self.repo_id = cfg["GAA_REPO_ID"]
        self.output_dir: Path = cfg["GAA_RAW_DIR"]
        self.allow_patterns = ["*.parquet", "*.json", "*.csv", "*.md"]

    def _matches_patterns(self, filename: str) -> bool:
        """Check if filename matches any of the allowed patterns."""
        import fnmatch
        return any(fnmatch.fnmatch(filename.lower(), pattern.lower()) for pattern in self.allow_patterns)

    def list_repo_files(self) -> List[str]:
        """Get list of files matching patterns from HF Hub dataset repo."""
        self.logger.info(f"Listing files from HF Hub dataset: {self.repo_id}")
        api = HfApi()
        try:
            repo_info = api.dataset_info(repo_id=self.repo_id)
            all_files = [sibling.rfilename for sibling in repo_info.siblings]
            matched_files = [f for f in all_files if self._matches_patterns(f)]
            self.logger.info(f"Found {len(matched_files)} matching files out of {len(all_files)} total files.")
            return matched_files
        except Exception as e:
            self.logger.error(f"Failed to list repo files: {e}")
            return []

    def download_file(self, filename: str, manifest: Dict) -> Optional[Path]:
        """Download a single file from HF Hub with retry logic and SHA256 verification."""
        target_path = self.output_dir / filename
        rel_path = str(target_path.relative_to(cfg["RAW_DATA_DIR"]))

        # Check if file already exists with matching checksum
        if target_path.exists():
            current_hash = self.calculate_sha256(target_path)
            if manifest.get(rel_path, {}).get("checksum") == current_hash:
                self.logger.info(f"Skipping {filename} - checksum matches manifest.")
                return target_path

        downloaded_path = self.output_dir / filename
        attempt = 0
        while attempt < cfg["MAX_RETRIES"]:
            try:
                self.logger.info(f"Downloading {filename} (Attempt {attempt + 1}/{cfg['MAX_RETRIES']})")
                delay = random.uniform(*cfg["DELAY_RANGE"])
                time.sleep(delay)

                # hf_hub_download writes directly to output_dir/filename via local_dir
                hf_hub_download(
                    repo_id=self.repo_id,
                    filename=filename,
                    repo_type="dataset",
                    local_dir=self.output_dir,
                    local_dir_use_symlinks=False,
                )

                if not downloaded_path.exists():
                    raise FileNotFoundError(f"Downloaded file not found at {downloaded_path}")

                checksum = self.calculate_sha256(downloaded_path)
                size = downloaded_path.stat().st_size
                manifest[rel_path] = {
                    "source": "bettergovph/gaa",
                    "filename": filename,
                    "relative_path": rel_path,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "size_bytes": size,
                    "checksum": checksum,
                }
                self.logger.info(f"Successfully downloaded {filename} ({size:,} bytes | SHA256: {checksum[:8]}...)")
                return downloaded_path

            except Exception as e:
                attempt += 1
                # Clean up any partial download left by hf_hub_download
                if downloaded_path.exists():
                    downloaded_path.unlink()
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                self.logger.warning(f"Error downloading {filename}: {e}. Retrying in {wait_time:.2f}s...")
                time.sleep(wait_time)

        self.logger.error(f"Failed to download {filename} after {cfg['MAX_RETRIES']} attempts.")
        return None

    def extract(self) -> bool:
        self.logger.info(f"Starting GAA dataset extraction from HF Hub: {self.repo_id}")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        try:
            manifest = self.load_manifest()
            files = self.list_repo_files()

            if not files:
                self.logger.warning("No matching files found in repository.")
                return False

            success_count = 0
            for filename in sorted(files):
                if self.download_file(filename, manifest):
                    success_count += 1
                    self.save_manifest(manifest)

            self.logger.info(f"GAA Extraction completed successfully. Downloaded {success_count}/{len(files)} files.")
            return success_count > 0

        except Exception as e:
            self.logger.error(f"GAA Extraction failed: {e}")
            return False


def main():
    """Standalone entrypoint for debugging.

    Uses the runner's root logger for proper console + file output.
    To run: ``python src/extraction/ph_gaa.py``
    """
    from src.orchestration.runner import setup_root_logger
    setup_root_logger()
    extractor = GAAExtractor()
    extractor.extract()


if __name__ == "__main__":
    main()
