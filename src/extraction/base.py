import abc
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict

from src.core.config import CONFIG as cfg


def setup_logging(name: str = "ingest") -> logging.Logger:
    """Get a child logger that propagates to the root logger.

    Handlers are configured once on the root logger by
    ``src.orchestration.runner.setup_root_logger()``, so this function
    only sets the child's level — no duplicate handlers needed.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    # Propagate to root logger (default is ``True``, but be explicit)
    logger.propagate = True
    return logger


class BaseExtractor(abc.ABC):
    """Abstract Base Class for all Data Extractors in TaxTracePH."""

    def __init__(self, name: str):
        self.name = name
        self.logger = setup_logging(f"ingest.{name}")

    @staticmethod
    def calculate_sha256(file_path: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def load_manifest(self) -> Dict:
        if cfg["MANIFEST_FILE"].exists():
            try:
                with open(cfg["MANIFEST_FILE"], "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.logger.error(f"Failed to load manifest: {e}. Starting fresh.")
        return {}

    def save_manifest(self, manifest: Dict):
        cfg["MANIFEST_FILE"].parent.mkdir(parents=True, exist_ok=True)
        with open(cfg["MANIFEST_FILE"], "w") as f:
            json.dump(manifest, f, indent=4)

    @abc.abstractmethod
    def extract(self) -> bool:
        """Execute extraction workflow. Must be implemented by subclasses."""
        pass
