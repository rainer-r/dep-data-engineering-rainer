"""
TaxTracePH — Validation Layer Framework.

Shared framework for the per-source validators (mirrors the extraction-layer
pattern in ``src/extraction/base.py``):

- ``BaseValidator`` (ABC): per-source validator with the expected-schema
  artifact (``data/reference/schemas/<source>.json``) as its contract.
- ``ValidationResult``: one assertion with a stable ``check`` id, a
  severity tier (``must`` blocks, ``should`` warns), and actual vs expected.
- ``ValidationReport``: the always-emitted artifact for one source. The
  orchestrator (``src/validation/orchestrator.py``) combines reports into
  ``data/validation_report.json``.

Semantics (per ADR 005 / grill session 2026-08-30):
- ``must``  — a failed check means the data does not satisfy its contract.
- ``should`` — a failed check is a warning or a known anomaly that a human
  must see (e.g. stale source README, unregistered new file, network drift
  check unreachable).
"""

from __future__ import annotations

import abc
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.config import CONFIG as cfg

SEVERITY_MUST = "must"
SEVERITY_SHOULD = "should"


def setup_logging(name: str = "validate") -> logging.Logger:
    """Child logger that propagates to the root (handlers live on root)."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = True
    return logger


@dataclass
class ValidationResult:
    """One executable assertion with its outcome (never raises)."""

    check: str            # stable id, e.g. "gaa.row_count"
    severity: str         # SEVERITY_MUST | SEVERITY_SHOULD
    passed: bool
    detail: str = ""
    actual: Any = None
    expected: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check": self.check,
            "severity": self.severity,
            "passed": self.passed,
            "detail": self.detail,
            "actual": self.actual if not isinstance(self.actual, set) else sorted(self.actual),
            "expected": self.expected if not isinstance(self.expected, set) else sorted(self.expected),
        }


@dataclass
class ValidationReport:
    """All results for one source, plus any execution errors."""

    source: str
    results: List[ValidationResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def add(self, result: ValidationResult) -> None:
        self.results.append(result)

    def must_failed(self) -> List[ValidationResult]:
        return [r for r in self.results if r.severity == SEVERITY_MUST and not r.passed]

    def passed(self) -> bool:
        return not self.must_failed() and not self.errors

    def counts(self) -> Dict[str, int]:
        failed = [r for r in self.results if not r.passed]
        return {
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": len(failed),
            "failed_must": sum(1 for r in failed if r.severity == SEVERITY_MUST),
            "failed_should": sum(1 for r in failed if r.severity == SEVERITY_SHOULD),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "started_at": self.started_at,
            "passed": self.passed(),
            "counts": self.counts(),
            "errors": self.errors,
            "results": [r.to_dict() for r in self.results],
        }

    def to_markdown(self) -> str:
        lines = [
            f"## {self.source}",
            "",
            f"- **Passed:** {self.passed()}",
            f"- **Counts:** {self.counts()}",
            f"- **Errors:** {self.errors or 'none'}",
            "",
            "| check | severity | status | detail |",
            "|-------|----------|--------|--------|",
        ]
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            detail = r.detail.replace("|", "\\|")[:160]
            lines.append(f"| `{r.check}` | {r.severity} | {status} | {detail} |")
        return "\n".join(lines)


class BaseValidator(abc.ABC):
    """Abstract base for a per-source raw-data validator.

    Subclasses implement ``validate()`` and return a ``ValidationReport``.
    The contract artifact (data dictionary + expected values) lives in
    ``data/reference/schemas/<source>.json`` and is loaded via
    ``load_schema()``.
    """

    source: str = ""          # stable source key: "gaa" | "tax" | "saaodb" | "global"
    source_label: str = ""
    schema_name: str = ""     # expected-schema artifact slug; defaults to source (e.g. "bir_tax")

    def __init__(
        self,
        skip_live: bool = False,
        raw_dir: Optional[Path] = None,
        manifest_file: Optional[Path] = None,
        schema_dir: Optional[Path] = None,
    ):
        self.skip_live = skip_live
        self.raw_dir = Path(raw_dir) if raw_dir else cfg["RAW_DATA_DIR"]
        self.manifest_file = Path(manifest_file) if manifest_file else cfg["MANIFEST_FILE"]
        self.schema_dir = Path(schema_dir) if schema_dir else cfg["SCHEMAS_DIR"]
        self.logger = setup_logging(f"validate.{self.source}")

    @property
    def schema_path(self) -> Path:
        slug = self.schema_name or self.source
        return self.schema_dir / f"{slug}.json"

    def load_schema(self) -> dict:
        """Load the expected-schema artifact, or ``{}`` when missing/unparseable.

        Missing artifacts are surfaced by ``register_schema_check()``; callers
        must tolerate an empty dict (checks degrade to failures).
        """
        if not self.schema_path.exists():
            self.logger.warning("expected schema artifact %s missing", self.schema_path)
            return {}
        try:
            with open(self.schema_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            self.logger.warning(
                "expected schema artifact %s not parseable: %s", self.schema_path, e
            )
            return {}

    def register_schema_check(self) -> ValidationResult:
        """Registry check: artifact exists, parses, and its ``source`` matches.

        Emits ``<source>.expected_schema`` as a ``must`` result. Never raises.
        """
        path = self.schema_path
        if not path.exists():
            return ValidationResult(
                f"{self.source}.expected_schema", SEVERITY_MUST, False,
                detail="expected schema artifact missing: %s" % path,
                actual="missing", expected=path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except json.JSONDecodeError as e:
            return ValidationResult(
                f"{self.source}.expected_schema", SEVERITY_MUST, False,
                detail="expected schema artifact not parseable JSON: %s" % e,
                actual="unparseable JSON", expected="parseable JSON")
        doc_source = doc.get("source") if isinstance(doc, dict) else type(doc).__name__
        if isinstance(doc, dict) and doc_source == self.source:
            return ValidationResult(
                f"{self.source}.expected_schema", SEVERITY_MUST, True,
                detail="expected schema artifact %s parses and source matches" % path.name,
                actual=doc_source, expected=self.source)
        return ValidationResult(
            f"{self.source}.expected_schema", SEVERITY_MUST, False,
            detail="expected schema artifact source key %r != %r" % (doc_source, self.source),
            actual=doc_source, expected=self.source)

    def load_manifest(self) -> dict:
        if not self.manifest_file.exists():
            return {}
        with open(self.manifest_file, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}

    def report(self) -> ValidationReport:
        return ValidationReport(source=self.source)

    @abc.abstractmethod
    def validate(self) -> ValidationReport:
        """Run every check for this source. Subclasses implement."""
        raise NotImplementedError