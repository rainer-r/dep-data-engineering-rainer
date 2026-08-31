"""Orchestrator and public-export tests for the validation layer.

Exercises ``run_validation()`` against synthetic raw trees (fully offline):
subset selection, the always-written combined document, exit-code semantics
(``must`` fail, ``should``-only pass, ``--strict`` escalation, a raising
validator), and the package's public exports.
"""

from __future__ import annotations

import json

from pathlib import Path

from src.core.config import CONFIG
from src.validation import (
    GAAValidator,
    GlobalValidator,
    SAAODBValidator,
    SEVERITY_MUST,
    SEVERITY_SHOULD,
    TaxCollectionValidator,
    ValidationReport,
    ValidationResult,
    run_validation,
)
from src.validation.orchestrator import REGISTRY
from tests.conftest import (
    GLOBAL_UNREGISTERED,
    SCHEMAS_DIR,
    TAX_FILENAMES,
    make_gaa_tree,
    make_manifest_tree,
    make_saaodb_tree,
    make_tax_tree,
)


# ---- fixture-tree builders --------------------------------------------------

def _patch_cfg(monkeypatch, root) -> None:
    """Point the orchestrator's config defaults at a fixture raw tree."""
    monkeypatch.setitem(CONFIG, "RAW_DATA_DIR", root)
    monkeypatch.setitem(CONFIG, "MANIFEST_FILE", root / "manifest.json")
    monkeypatch.setitem(CONFIG, "SCHEMAS_DIR", SCHEMAS_DIR)


def _combined_tree(root):
    """gaa + tax + saaodb fixture trees with one manifest covering every file."""
    make_gaa_tree(root)
    make_tax_tree(root)
    make_saaodb_tree(root)
    rels = [
        "gaa/gaa.parquet", "gaa/README.md",
        "tax/%s" % TAX_FILENAMES["annual"],
        "tax/%s" % TAX_FILENAMES["monthly"],
        "tax/%s" % TAX_FILENAMES["partial"],
        "saaodb/2011Q1.htm", "saaodb/2026Q1.pdf",
    ]
    files = {rel: (root / rel).read_bytes() for rel in rels}
    make_manifest_tree(root, files)
    return root


def _tax_only_tree(root, *, unregistered: bool = True):
    """Tax fixture tree (+ optional unregistered workbook) with a manifest."""
    make_tax_tree(root)
    rels = [
        "tax/%s" % TAX_FILENAMES["annual"],
        "tax/%s" % TAX_FILENAMES["monthly"],
        "tax/%s" % TAX_FILENAMES["partial"],
    ]
    files = {rel: (root / rel).read_bytes() for rel in rels}
    extra = [GLOBAL_UNREGISTERED[0]] if unregistered else None
    make_manifest_tree(root, files, extra=extra)
    return root


def _record_invocations(calls, cls, monkeypatch) -> None:
    orig = cls.validate

    def spy(self):
        calls.append(cls.source)
        return orig(self)

    monkeypatch.setattr(cls, "validate", spy)


# ---- orchestration ----------------------------------------------------------

def test_subset_selection_runs_only_selected_plus_global(tmp_path, monkeypatch):
    root = _combined_tree(tmp_path)
    _patch_cfg(monkeypatch, root)
    report_file = tmp_path / "report.json"

    calls = []
    for cls in (GlobalValidator, GAAValidator, TaxCollectionValidator,
                SAAODBValidator):
        _record_invocations(calls, cls, monkeypatch)
    run_validation(["gaa"], skip_live=True, report_file=report_file)

    assert calls == ["global", "gaa"]

    doc = json.loads(report_file.read_text(encoding="utf-8"))
    assert set(doc) == {"run_started_at", "selected_sources", "strict",
                        "exit_code", "summary_counts", "reports"}
    assert doc["selected_sources"] == ["gaa"]
    assert doc["strict"] is False
    assert set(doc["reports"]) == {"global", "gaa", "tax", "saaodb"}
    for key in ("global", "gaa"):
        block = doc["reports"][key]
        assert "skipped" not in block
        assert block["source"] == key
        assert block["counts"]["total"] > 0
        assert "results" in block and "errors" in block
    assert doc["reports"]["tax"] == {"source": "tax", "skipped": True}
    assert doc["reports"]["saaodb"] == {"source": "saaodb", "skipped": True}


def test_registry_order_is_global_gaa_tax_saaodb():
    assert list(REGISTRY) == ["global", "gaa", "tax", "saaodb"]


def test_all_sources_combined_document_and_aggregate(tmp_path, monkeypatch):
    root = _combined_tree(tmp_path)
    _patch_cfg(monkeypatch, root)
    report_file = tmp_path / "report.json"
    run_validation(skip_live=True, report_file=report_file)  # selected=None

    doc = json.loads(report_file.read_text(encoding="utf-8"))
    assert doc["selected_sources"] == ["gaa", "tax", "saaodb"]
    assert list(doc["reports"]) == ["global", "gaa", "tax", "saaodb"]
    for key in ("global", "gaa", "tax", "saaodb"):
        block = doc["reports"][key]
        assert "skipped" not in block
        assert block["counts"]["total"] > 0
    per_source = [doc["reports"][key]["counts"] for key in ("global", "gaa",
                                                            "tax", "saaodb")]
    for metric in ("total", "passed", "failed", "failed_must", "failed_should"):
        assert doc["summary_counts"][metric] == sum(b[metric] for b in per_source)


def test_must_failure_yields_exit_code_1(tmp_path, monkeypatch):
    root = _combined_tree(tmp_path)
    _patch_cfg(monkeypatch, root)
    report_file = tmp_path / "report.json"
    # the mini GAA parquet trips the row_count must gate (3 vs 4,538,396)
    code = run_validation(["gaa"], skip_live=True, report_file=report_file)
    doc = json.loads(report_file.read_text(encoding="utf-8"))
    assert doc["reports"]["gaa"]["counts"]["failed_must"] >= 1
    assert code == 1
    assert doc["exit_code"] == 1


def test_should_only_failures_pass_normally_and_fail_under_strict(
        tmp_path, monkeypatch):
    root = _tax_only_tree(tmp_path, unregistered=True)
    _patch_cfg(monkeypatch, root)
    report_file = tmp_path / "report.json"
    code = run_validation(["tax"], skip_live=True, report_file=report_file)
    doc = json.loads(report_file.read_text(encoding="utf-8"))
    assert code == 0
    assert doc["exit_code"] == 0
    assert doc["strict"] is False
    assert doc["summary_counts"]["failed_must"] == 0
    assert doc["summary_counts"]["failed"] >= 1   # global + tax warns
    assert doc["summary_counts"]["failed_should"] >= 1

    strict_file = tmp_path / "report_strict.json"
    code_strict = run_validation(["tax"], strict=True, skip_live=True,
                                 report_file=strict_file)
    doc_strict = json.loads(strict_file.read_text(encoding="utf-8"))
    assert code_strict == 1
    assert doc_strict["exit_code"] == 1
    assert doc_strict["strict"] is True


def test_raising_validator_is_caught_report_written_exit_1(tmp_path,
                                                           monkeypatch):
    root = _combined_tree(tmp_path)
    _patch_cfg(monkeypatch, root)

    def boom(self):
        raise RuntimeError("fixture boom")

    monkeypatch.setattr(TaxCollectionValidator, "validate", boom)
    report_file = tmp_path / "report.json"
    code = run_validation(["tax", "gaa"], skip_live=True,
                          report_file=report_file)

    doc = json.loads(report_file.read_text(encoding="utf-8"))
    assert doc["reports"]["tax"]["errors"] == ["fixture boom"]
    assert doc["reports"]["tax"]["results"] == []
    # the global validator and the other selected source still ran
    assert doc["reports"]["global"]["counts"]["total"] > 0
    assert len(doc["reports"]["gaa"]["results"]) > 0
    assert code == 1
    assert doc["exit_code"] == 1


def test_always_writes_report_with_path_and_nested_bytes_payloads(
        tmp_path, monkeypatch):
    """The always-write guarantee holds for every payload the checks record."""
    root = _tax_only_tree(tmp_path, unregistered=False)
    _patch_cfg(monkeypatch, root)

    def weird(self):
        rep = ValidationReport(source="tax")
        rep.add(ValidationResult(
            "tax.path_expected", SEVERITY_MUST, False,
            actual={"nested": b"%PDF"},
            expected=Path("data/reference/schemas/missing.json")))
        return rep

    monkeypatch.setattr(TaxCollectionValidator, "validate", weird)
    report_file = tmp_path / "report.json"
    code = run_validation(["tax"], skip_live=True, report_file=report_file)
    assert code == 1
    doc = json.loads(report_file.read_text(encoding="utf-8"))
    result = doc["reports"]["tax"]["results"][0]
    assert result["expected"] == "data/reference/schemas/missing.json"
    assert result["actual"] == {"nested": "%PDF"}


def test_string_and_unknown_selected_are_tolerated(tmp_path, monkeypatch):
    root = _tax_only_tree(tmp_path, unregistered=False)
    _patch_cfg(monkeypatch, root)
    report_file = tmp_path / "report.json"
    assert run_validation("tax", skip_live=True, report_file=report_file) == 0
    doc = json.loads(report_file.read_text(encoding="utf-8"))
    assert doc["selected_sources"] == ["tax"]

    report_file2 = tmp_path / "report2.json"
    assert run_validation(["tax", "tax", "bogus", "global"], skip_live=True,
                          report_file=report_file2) == 0
    doc2 = json.loads(report_file2.read_text(encoding="utf-8"))
    assert doc2["selected_sources"] == ["tax"]


# ---- public exports ---------------------------------------------------------

def test_public_exports_import_cleanly():
    from src.validation import __all__ as public_names
    assert set(public_names) == {
        "SEVERITY_MUST", "SEVERITY_SHOULD",
        "ValidationResult", "ValidationReport",
        "GlobalValidator", "GAAValidator", "TaxCollectionValidator",
        "SAAODBValidator", "run_validation",
    }
    assert SEVERITY_MUST == "must"
    assert SEVERITY_SHOULD == "should"
    for cls in (GlobalValidator, GAAValidator, TaxCollectionValidator,
                SAAODBValidator):
        assert cls.source in ("global", "gaa", "tax", "saaodb")
    assert callable(run_validation)
    result = ValidationResult("demo.check", SEVERITY_MUST, True)
    assert result.passed
    assert ValidationReport(source="demo").counts()["total"] == 0