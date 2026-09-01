"""Orchestration for the validation layer.

``run_validation()`` is the single entry point: it runs the global validator
plus any selected source validators (registry: global, gaa, tax, saaodb),
combines their reports into one JSON document that is always written to the
validation-report location, prints a compact console summary, and returns the
process exit code — ``0`` when clear, ``1`` when any ``must`` fails or a
validator errors, and ``1`` under ``strict`` when any ``should`` fails.

The combined document has a stable top level: ``run_started_at``,
``selected_sources``, ``strict``, ``exit_code``, ``summary_counts`` (the
aggregate of the per-source ``counts()``), and ``reports`` — an ordered map
with all four blocks always present (``global``, ``gaa``, ``tax``, ``saaodb``);
a skipped source gets an empty block with a ``"skipped": true`` marker.
Settled by the grill session 2026-08-30; do not re-litigate.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.core.config import CONFIG as cfg
from src.validation.base import ValidationReport, setup_logging
from src.validation.global_checks import GlobalValidator
from src.validation.ph_gaa import GAAValidator
from src.validation.ph_saaodb import SAAODBValidator
from src.validation.ph_tax_collection import TaxCollectionValidator

# Fixed run order: global always runs; selected sources run in registry order.
REGISTRY: Dict[str, type[Any]] = {
    "global": GlobalValidator,
    "gaa": GAAValidator,
    "tax": TaxCollectionValidator,
    "saaodb": SAAODBValidator,
}

_SOURCE_KEYS = tuple(key for key in REGISTRY if key != "global")

_logger = setup_logging("validate.orchestrator")


def _normalise_selected(selected=None) -> List[str]:
    """Return the unique, ordered source keys to run.

    ``None`` means all three source keys. A plain string is treated as one
    key. ``"global"`` is dropped — the global validator always runs. Unknown
    keys are logged and skipped; strict name validation is the CLI's job.
    """
    iterable: Iterable[str]
    if selected is None:
        iterable = _SOURCE_KEYS
    elif isinstance(selected, str):
        iterable = (selected,)
    else:
        iterable = selected
    out: List[str] = []
    for key in iterable:
        if key == "global":
            continue
        if key not in REGISTRY:
            _logger.warning("unknown validation source key %r ignored", key)
            continue
        if key not in out:
            out.append(key)
    return out


def _aggregate_counts(reports: Dict[str, ValidationReport]) -> Dict[str, int]:
    """Sum the per-source ``counts()`` (skipped blocks contribute zero)."""
    agg = dict(total=0, passed=0, failed=0, failed_must=0, failed_should=0)
    for rep in reports.values():
        counts = rep.counts()
        for key in agg:
            agg[key] += counts[key]
    return agg


def _build_document(
    started_at: str,
    selected: List[str],
    strict: bool,
    exit_code: int,
    reports: Dict[str, ValidationReport],
) -> Dict[str, Any]:
    """Assemble the always-written report document top level."""
    reports_doc: Dict[str, Any] = {}
    for key in REGISTRY:
        rep = reports.get(key)
        if rep is None:
            reports_doc[key] = {"source": key, "skipped": True}
        else:
            reports_doc[key] = rep.to_dict()
    return {
        "run_started_at": started_at,
        "selected_sources": selected,
        "strict": strict,
        "exit_code": exit_code,
        "summary_counts": _aggregate_counts(reports),
        "reports": reports_doc,
    }


def _write_report(document: Dict[str, Any], report_path: Path) -> None:
    """Always attempt to write the report JSON; a write failure is logged."""
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(document, f, indent=2)
            f.write("\n")
    except OSError as exc:
        _logger.error("cannot write validation report %s: %s", report_path, exc)


def _compute_exit_code(
    reports: Dict[str, ValidationReport], strict: bool
) -> int:
    """``1`` on any failed ``must``, any validator error, or any failure under
    ``strict``; otherwise ``0``. Skipped sources contribute nothing."""
    if any(rep.must_failed() for rep in reports.values()):
        return 1
    if any(rep.errors for rep in reports.values()):
        return 1
    if strict and any(rep.counts()["failed"] for rep in reports.values()):
        return 1
    return 0


def _print_summary(
    reports: Dict[str, ValidationReport],
    report_path: Path,
    exit_code: int,
) -> None:
    """Compact human table: per-source passed/counts plus the must failures."""
    header = ["source", "status", "total", "passed", "failed", "must", "should"]
    rows: List[List[Any]] = []
    for key in REGISTRY:
        rep = reports.get(key)
        if rep is None:
            rows.append([key, "SKIPPED", 0, 0, 0, 0, 0])
            continue
        counts = rep.counts()
        rows.append([
            key,
            "PASS" if rep.passed() else "FAIL",
            counts["total"], counts["passed"], counts["failed"],
            counts["failed_must"], counts["failed_should"],
        ])
    widths = [
        max(len(str(row[i])) for row in rows + [header])
        for i in range(len(header))
    ]
    template = "  ".join(
        "{" + str(i) + ":<" + str(widths[i]) + "}" for i in range(len(header))
    )
    print("Validation report -> %s" % report_path)
    print(template.format(*header))
    for row in rows:
        print(template.format(*row))
    failed_must: List[str] = []
    for key in REGISTRY:
        rep = reports.get(key)
        if rep is None:
            continue
        for result in rep.must_failed():
            failed_must.append("[%s] %s: %s" % (key, result.check, result.detail))
    if failed_must:
        print("must failures:")
        for line in failed_must[:10]:
            print("  %s" % line)
        if len(failed_must) > 10:
            print("  ... and %d more" % (len(failed_must) - 10))
    print("exit code: %d" % exit_code)


def run_validation(
    selected=None,
    strict: bool = False,
    skip_live: bool = False,
    logger: Optional[logging.Logger] = None,
    report_file: Optional[Path] = None,
    print_summary: bool = True,
) -> int:
    """Run the global validator plus the selected sources; return the exit code.

    The combined report document is **always** written to ``report_file``
    (default ``cfg["VALIDATION_REPORT_FILE"]`` =
    ``data/validation_report.json``). A validator that raises is caught,
    logged, and recorded in that source's report ``errors`` — the run
    continues, still exits 1, and still writes the report.

    ``print_summary`` (default ``True``) switches the compact console table
    on/off. The CLI passes ``False`` under ``--json`` so stdout carries only
    the report document (which the CLI prints from the always-written file).
    """
    log = logger if logger is not None else _logger
    keys = _normalise_selected(selected)
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    reports: Dict[str, ValidationReport] = {}
    for key in REGISTRY:
        if key != "global" and key not in keys:
            continue
        try:
            validator = REGISTRY[key](skip_live=skip_live)
            rep = validator.validate()
        except Exception as exc:  # noqa: BLE001 — never abort the run
            log.error("validator %s raised: %s", key, exc)
            rep = ValidationReport(source=key)
            rep.errors.append(str(exc))
        reports[key] = rep

    exit_code = _compute_exit_code(reports, strict)
    report_path = (
        Path(report_file) if report_file else cfg["VALIDATION_REPORT_FILE"]
    )
    _write_report(
        _build_document(started_at, keys, strict, exit_code, reports),
        report_path,
    )
    if print_summary:
        _print_summary(reports, report_path, exit_code)
    return exit_code
