"""Global validator - the source-agnostic check over the shared manifest.

Checks that ``data/raw/manifest.json`` exists, parses as a JSON object, that
every manifest entry resolves to a file under ``raw_dir``, that every registered
file's SHA-256 recomputed in streaming chunks matches its manifest checksum, and
that depth-1 raw files with known extensions that are not registered surface as
a ``should`` warning. Nothing here deletes or modifies data.

The validator deliberately has no expected-schema artifact: ``source`` is
``"global"`` and there is no ``global.json`` in ``data/reference/schemas/``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.config import CONFIG as cfg
from src.validation.base import (
    SEVERITY_MUST,
    SEVERITY_SHOULD,
    BaseValidator,
    ValidationReport,
    ValidationResult,
)

_UNREGISTERED_EXTENSIONS = {".xlsx", ".htm", ".pdf", ".parquet", ".md"}
_SOURCE_SUBDIRS = ("gaa", "tax", "saaodb")


class GlobalValidator(BaseValidator):
    """Source-agnostic validator over the shared manifest and raw-data tree."""

    source = "global"
    source_label = "Shared manifest + entire raw-data tree"

    # -- helpers ------------------------------------------------------------

    def _read_manifest(self) -> Optional[Dict[str, Any]]:
        """Return the manifest dict, or None when missing/not a JSON object."""
        if not self.manifest_file.exists():
            return None
        try:
            with open(self.manifest_file, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        return doc if isinstance(doc, dict) else None

    def _sha256(self, path: Path) -> str:
        """SHA-256 of a file, streamed in chunks (no full-file loads)."""
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            while block := f.read(cfg["CHUNK_SIZE"]):
                digest.update(block)
        return digest.hexdigest()

    def _checksum_check(self, rep, rel_path: str, entry: Any) -> None:
        """One ``must`` result per registered file: on-disk sha256 vs manifest."""
        check_id = "global.checksum.%s" % rel_path
        path = self.raw_dir / rel_path
        if not path.is_file():
            rep.add(
                ValidationResult(
                    check_id, SEVERITY_MUST, False,
                    detail="manifest-registered file missing on disk: %s" % rel_path,
                    actual="missing", expected=rel_path,
                )
            )
            return
        expected = entry.get("checksum") if isinstance(entry, dict) else None
        if not isinstance(expected, str) or not expected:
            rep.add(
                ValidationResult(
                    check_id, SEVERITY_MUST, False,
                    detail="manifest entry has no string checksum: %s" % rel_path,
                    actual="missing checksum key", expected="checksum hex string",
                )
            )
            return
        try:
            actual = self._sha256(path)
        except OSError as e:
            rep.add(
                ValidationResult(
                    check_id, SEVERITY_MUST, False,
                    detail="manifest-registered file unreadable: %s (%s)"
                           % (rel_path, e),
                    actual="unreadable", expected=rel_path,
                )
            )
            return
        rep.add(
            ValidationResult(
                check_id, SEVERITY_MUST, actual == expected,
                detail="%s recomputed sha256 %s" % (
                    rel_path, "matches manifest" if actual == expected
                    else "does NOT match manifest"),
                actual=actual, expected=expected,
            )
        )

    def _unregistered_check(self, rep, manifest: Dict[str, Any]) -> None:
        """Depth-1 scan for known-extension files not registered in the manifest."""
        registered = set(manifest)
        unregistered = []
        for sub in _SOURCE_SUBDIRS:
            subdir = self.raw_dir / sub
            if not subdir.is_dir():
                continue
            for p in sorted(subdir.iterdir()):
                if p.name.startswith(".") or not p.is_file():
                    continue  # hidden entries + dotfiles are never reported
                if p.suffix.lower() not in _UNREGISTERED_EXTENSIONS:
                    continue
                rel = "%s/%s" % (sub, p.name)
                if rel not in registered:
                    unregistered.append(rel)
        rep.add(
            ValidationResult(
                "global.unregistered_files", SEVERITY_SHOULD, not unregistered,
                detail="raw file(s) on disk not registered in the manifest: %s"
                       % (unregistered or "none"),
                actual=unregistered or None, expected="[]",
            )
        )

    # -- main ---------------------------------------------------------------

    def validate(self) -> ValidationReport:
        rep = self.report()

        manifest_exists = self.manifest_file.is_file()
        rep.add(
            ValidationResult(
                "global.manifest_exists", SEVERITY_MUST, manifest_exists,
                detail="manifest file %s %s" % (
                    self.manifest_file,
                    "exists" if manifest_exists else "is missing"),
                actual="present" if manifest_exists else "missing",
                expected="manifest file exists",
            )
        )

        manifest = self._read_manifest()
        rep.add(
            ValidationResult(
                "global.manifest_parseable", SEVERITY_MUST, manifest is not None,
                detail="manifest %s" % (
                    "parses as a JSON object" if manifest is not None
                    else "missing or unparseable"),
                actual=("parseable JSON object" if manifest is not None
                        else "missing or unparseable"),
                expected="parseable JSON object",
            )
        )

        if manifest is None:
            # missing/unparseable manifest: the three manifest checks fail together
            rep.add(
                ValidationResult(
                    "global.manifest_files_on_disk", SEVERITY_MUST, False,
                    detail="manifest unavailable; cannot verify registered files on disk",
                    actual="no manifest",
                    expected="manifest entries exist under %s" % self.raw_dir,
                )
            )
            rep.add(
                ValidationResult(
                    "global.unregistered_files", SEVERITY_SHOULD, True,
                    detail="manifest unavailable; unregistered-file scan skipped",
                    actual="skipped", expected="manifest with registered keys",
                )
            )
            return rep

        missing = sorted(rel for rel in manifest
                         if not (self.raw_dir / rel).is_file())
        rep.add(
            ValidationResult(
                "global.manifest_files_on_disk", SEVERITY_MUST, not missing,
                detail="manifest entries missing on disk: %s" % (missing or "none"),
                actual=len(manifest) - len(missing), expected=len(manifest),
            )
        )

        for rel_path in sorted(manifest):
            self._checksum_check(rep, rel_path, manifest[rel_path])

        self._unregistered_check(rep, manifest)
        return rep
