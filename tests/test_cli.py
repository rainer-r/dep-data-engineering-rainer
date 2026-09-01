"""CLI tests — ``scripts/validate.py`` exercised in-process via ``main([...])``.

The public seam under test is ``main()``; ``cfg`` is monkeypatched to fixture
raw trees (report_file / raw_dir / schema_dir / manifest seams) so runs are
fully offline. Covers the five acceptance criteria: all-sources default,
``--json`` prints one valid JSON document while the report file is still
written, exit codes match the orchestration semantics, and invalid source
names fail clearly without a traceback. Covers the four acceptance criteria.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate import main
from src.core.config import CONFIG
from tests.conftest import (
    GLOBAL_UNREGISTERED,
    SCHEMAS_DIR,
    TAX_FILENAMES,
    make_gaa_tree,
    make_manifest_tree,
    make_saaodb_tree,
    make_tax_tree,
)


# ---- fixture-tree builders -------------------------------------------------

def _patch_config(monkeypatch, root: Path, report_file: Path) -> None:
    """Point the CLI's config defaults (report/raw/manifest/schema seams) at a
    fixture raw tree."""
    monkeypatch.setitem(CONFIG, "RAW_DATA_DIR", root)
    monkeypatch.setitem(CONFIG, "MANIFEST_FILE", root / "manifest.json")
    monkeypatch.setitem(CONFIG, "SCHEMAS_DIR", SCHEMAS_DIR)
    monkeypatch.setitem(CONFIG, "VALIDATION_REPORT_FILE", report_file)


def _tax_files(root: Path) -> dict:
    rels = [
        "tax/%s" % TAX_FILENAMES["annual"],
        "tax/%s" % TAX_FILENAMES["monthly"],
        "tax/%s" % TAX_FILENAMES["partial"],
    ]
    return {rel: (root / rel).read_bytes() for rel in rels}


def _clean_tax_tree(root: Path) -> Path:
    """tax/ with the three contract workbooks + a manifest covering all files."""
    make_tax_tree(root)
    make_manifest_tree(root, _tax_files(root))
    return root


def _tax_tree_with_unregistered(root: Path) -> Path:
    """Like ``_clean_tax_tree``, plus one unregistered workbook (a ``should``)."""
    make_tax_tree(root)
    make_manifest_tree(root, _tax_files(root), extra=GLOBAL_UNREGISTERED)
    return root


def _combined_tree(root: Path) -> Path:
    """gaa + tax + saaodb fixture trees with one manifest covering every file."""
    make_gaa_tree(root)
    make_tax_tree(root)
    make_saaodb_tree(root)
    rels = set(_tax_files(root)) | {
        "gaa/gaa.parquet", "gaa/README.md",
        "saaodb/2011Q1.htm", "saaodb/2026Q1.pdf",
    }
    files = {rel: (root / rel).read_bytes() for rel in rels}
    make_manifest_tree(root, files)
    return root


# ---- AC1: no --source flag -> all sources + global, offline ----------------

def test_no_source_flag_runs_all_sources_plus_global_offline(tmp_path,
                                                             monkeypatch):
    root = _combined_tree(tmp_path)
    report_file = tmp_path / "validation_report.json"
    _patch_config(monkeypatch, root, report_file)

    code = main(["--skip-live"])

    # fixtures intentionally trip some must gates (GAA row count / SAAODB
    # count) - AC1 is about *what runs*, exit codes are AC3's concern.
    assert code in (0, 1)
    doc = json.loads(report_file.read_text(encoding="utf-8"))
    assert doc["selected_sources"] == ["gaa", "tax", "saaodb"]
    assert list(doc["reports"]) == ["global", "gaa", "tax", "saaodb"]
    for key in ("global", "gaa", "tax", "saaodb"):
        block = doc["reports"][key]
        assert "skipped" not in block
        assert block["counts"]["total"] > 0
    # offline: the SAAODB live-drift check ran skipped via --skip-live
    drift = [r for r in doc["reports"]["saaodb"]["results"]
             if r["check"] == "saaodb.live_source_drift"][0]
    assert drift["passed"] is True
    assert "skipped" in drift["detail"]


# ---- AC2: --json prints one valid JSON document ----------------------------

def test_json_flag_prints_single_valid_document_and_still_writes_report(
        tmp_path, monkeypatch, capsys):
    root = _clean_tax_tree(tmp_path)
    report_file = tmp_path / "validation_report.json"
    _patch_config(monkeypatch, root, report_file)

    code = main(["--skip-live", "--source", "tax", "--json"])

    assert code == 0
    assert report_file.exists()          # report file is still always written
    out = capsys.readouterr().out
    doc = json.loads(out)                # exactly one valid JSON document
    assert doc["selected_sources"] == ["tax"]
    assert doc["strict"] is False
    assert doc["reports"]["tax"]["counts"]["total"] > 0
    assert "Validation report ->" not in out   # human summary is replaced
    assert doc == json.loads(report_file.read_text(encoding="utf-8"))


def test_without_json_prints_human_summary(tmp_path, monkeypatch, capsys):
    root = _clean_tax_tree(tmp_path)
    report_file = tmp_path / "validation_report.json"
    _patch_config(monkeypatch, root, report_file)

    code = main(["--skip-live", "--source", "tax"])

    assert code == 0
    out = capsys.readouterr().out
    assert "Validation report ->" in out
    assert "exit code: 0" in out
    assert "tax" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)                  # not JSON - it is the human table


# ---- AC3: exit codes match orchestration semantics -------------------------

def test_exit_code_zero_on_clean_run(tmp_path, monkeypatch):
    root = _clean_tax_tree(tmp_path)
    report_file = tmp_path / "validation_report.json"
    _patch_config(monkeypatch, root, report_file)

    assert main(["--skip-live", "--source", "tax"]) == 0


def test_exit_code_one_on_must_failure(tmp_path, monkeypatch):
    root = _combined_tree(tmp_path)
    report_file = tmp_path / "validation_report.json"
    _patch_config(monkeypatch, root, report_file)

    code = main(["--skip-live", "--source", "gaa"])

    assert code == 1
    doc = json.loads(report_file.read_text(encoding="utf-8"))
    assert doc["reports"]["gaa"]["counts"]["failed_must"] >= 1
    assert doc["exit_code"] == 1


def test_exit_code_one_under_strict_when_should_fails(tmp_path, monkeypatch):
    root = _tax_tree_with_unregistered(tmp_path)
    report_file = tmp_path / "validation_report.json"
    _patch_config(monkeypatch, root, report_file)

    assert main(["--skip-live", "--source", "tax"]) == 0     # should only
    code = main(["--strict", "--skip-live", "--source", "tax"])
    assert code == 1                                            # escalated
    doc = json.loads(report_file.read_text(encoding="utf-8"))
    assert doc["strict"] is True
    assert doc["exit_code"] == 1
    assert doc["summary_counts"]["failed_must"] == 0
    assert doc["summary_counts"]["failed_should"] >= 1


# ---- AC4: invalid source names ---------------------------------------------

def test_invalid_source_prints_clear_error_without_traceback(capsys):
    code = main(["--source", "gaa,wat"])
    assert code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (captured.err
            == "Error: Invalid source(s): wat. Valid: gaa, tax, saaodb\n")
    assert "Traceback" not in captured.err


def test_invalid_sources_sorted_alphabetically(capsys):
    code = main(["--source", "zzz,aaa"])
    assert code == 1
    captured = capsys.readouterr()
    assert (captured.err
            == "Error: Invalid source(s): aaa, zzz. Valid: gaa, tax, saaodb\n")
