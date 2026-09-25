"""Runner shim tests — ``validate_raw_data`` delegates to the validation layer.

Covers the three acceptance criteria against fixture raw trees (fully offline):
the returned dict carries every legacy key the summary printer reads (AC1), the
``scripts/ingest.py`` import + call contract is unchanged (AC2), and the counts
match the fixture contents (AC3). Also covers the settled derivations (orphans
via re-scan, parquet errors from ``global.checksum.*`` failures) and the
never-raise guarantee.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import src.orchestration.runner as runner
from src.core.config import CONFIG
from src.orchestration.runner import print_summary, validate_raw_data
from tests.conftest import (
    SCHEMAS_DIR,
    TAX_FILENAMES,
    make_gaa_tree,
    make_manifest_tree,
    make_saaodb_tree,
    make_tax_tree,
)

VALIDATION_KEYS = {
    "gaa_files",
    "tax_files",
    "saaodb_files",
    "manifest_exists",
    "manifest_entries",
    "manifest_orphans",
    "parquet_errors",
}


# ---- fixture-tree builders --------------------------------------------------


def _patch_cfg(monkeypatch, root: Path, report_file: Path) -> None:
    """Point the runner's config defaults at a fixture raw tree."""
    monkeypatch.setitem(CONFIG, "RAW_DATA_DIR", root)
    monkeypatch.setitem(CONFIG, "GAA_RAW_DIR", root / "gaa")
    monkeypatch.setitem(CONFIG, "BIR_RAW_DIR", root / "tax")
    monkeypatch.setitem(CONFIG, "SAAODB_RAW_DIR", root / "saaodb")
    monkeypatch.setitem(CONFIG, "MANIFEST_FILE", root / "manifest.json")
    monkeypatch.setitem(CONFIG, "SCHEMAS_DIR", SCHEMAS_DIR)
    monkeypatch.setitem(CONFIG, "VALIDATION_REPORT_FILE", report_file)


def _combined_tree(root: Path) -> Path:
    """gaa + tax + saaodb fixture trees with one manifest covering every file."""
    make_gaa_tree(root)
    make_tax_tree(root)
    make_saaodb_tree(root)
    rels = [
        "gaa/gaa.parquet",
        "gaa/README.md",
        "tax/%s" % TAX_FILENAMES["annual"],
        "tax/%s" % TAX_FILENAMES["monthly"],
        "tax/%s" % TAX_FILENAMES["partial"],
        "saaodb/2011Q1.htm",
        "saaodb/2026Q1.pdf",
    ]
    files = {rel: (root / rel).read_bytes() for rel in rels}
    make_manifest_tree(root, files)
    return root


def _results() -> dict:
    return {
        "extractors": {"GAA (Hugging Face)": {"success": True}},
        "overall_success": True,
    }


# ---- AC3: counts match the fixture tree -------------------------------------


def test_counts_match_fixture_contents(tmp_path, monkeypatch):
    root = _combined_tree(tmp_path)
    _patch_cfg(monkeypatch, root, tmp_path / "validation_report.json")

    validation = validate_raw_data(logging.getLogger("test_shim"))

    assert set(validation) == VALIDATION_KEYS
    assert validation["gaa_files"] == 2
    assert validation["tax_files"] == 3
    assert validation["saaodb_files"] == 2
    assert validation["manifest_exists"] is True
    assert validation["manifest_entries"] == 7
    assert validation["manifest_orphans"] == []
    assert validation["parquet_errors"] == []


def test_missing_manifest_returns_legacy_shape_without_raising(tmp_path,
                                                              monkeypatch):
    root = _combined_tree(tmp_path)
    (root / "manifest.json").unlink()
    _patch_cfg(monkeypatch, root, tmp_path / "validation_report.json")

    validation = validate_raw_data(logging.getLogger("test_shim"))

    assert set(validation) == VALIDATION_KEYS
    assert validation["manifest_exists"] is False
    assert validation["manifest_entries"] == 0
    assert validation["manifest_orphans"] == []
    assert validation["parquet_errors"] == []


def test_manifest_key_missing_on_disk_is_an_orphan(tmp_path, monkeypatch):
    root = _combined_tree(tmp_path)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tax/ghost.xlsx"] = {
        "relative_path": "tax/ghost.xlsx",
        "checksum": "0" * 64,
        "size_bytes": 0,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _patch_cfg(monkeypatch, root, tmp_path / "validation_report.json")

    validation = validate_raw_data(logging.getLogger("test_shim"))

    assert validation["manifest_entries"] == 8
    assert validation["manifest_orphans"] == ["tax/ghost.xlsx"]


def test_corrupt_parquet_appears_in_parquet_errors(tmp_path, monkeypatch):
    root = _combined_tree(tmp_path)
    parquet = root / "gaa/gaa.parquet"
    body = bytearray(parquet.read_bytes())
    body[0] ^= 0xFF
    parquet.write_bytes(bytes(body))
    _patch_cfg(monkeypatch, root, tmp_path / "validation_report.json")

    validation = validate_raw_data(logging.getLogger("test_shim"))

    assert validation["parquet_errors"] == [str(parquet)]
def test_missing_registered_parquet_is_orphan_not_parquet_error(
        tmp_path, monkeypatch):
    """A manifest-registered .parquet missing on disk is an orphan only —
    never a parquet error (the legacy magic-byte scan only walked files that
    exist on disk)."""
    root = _combined_tree(tmp_path)
    (root / "gaa/gaa.parquet").unlink()
    _patch_cfg(monkeypatch, root, tmp_path / "validation_report.json")

    validation = validate_raw_data(logging.getLogger("test_shim"))

    assert validation["manifest_orphans"] == ["gaa/gaa.parquet"]
    assert validation["parquet_errors"] == []


# ---- delegate call (settled arguments) --------------------------------------


def test_delegates_to_run_validation_with_settled_arguments(tmp_path,
                                                            monkeypatch):
    root = _combined_tree(tmp_path)
    _patch_cfg(monkeypatch, root, tmp_path / "validation_report.json")
    calls = []

    def fake_run_validation(selected=None, strict=False, skip_live=False,
                            logger=None, report_file=None, print_summary=True):
        calls.append({
            "selected": selected,
            "strict": strict,
            "skip_live": skip_live,
            "logger": logger,
            "print_summary": print_summary,
        })
        return 0

    monkeypatch.setattr(runner, "run_validation", fake_run_validation)
    test_logger = logging.getLogger("test_shim")

    validation = validate_raw_data(test_logger)

    assert len(calls) == 1
    assert calls[0]["selected"] == {"gaa", "tax", "saaodb"}
    assert calls[0]["strict"] is False
    assert calls[0]["skip_live"] is True
    assert calls[0]["logger"] is test_logger
    assert calls[0]["print_summary"] is False


# ---- never raise ------------------------------------------------------------


def test_run_validation_exception_returns_default_dict(tmp_path, monkeypatch):
    root = _combined_tree(tmp_path)
    _patch_cfg(monkeypatch, root, tmp_path / "validation_report.json")

    def boom(*args, **kwargs):
        raise RuntimeError("fixture boom")

    monkeypatch.setattr(runner, "run_validation", boom)

    validation = validate_raw_data(logging.getLogger("test_shim"))

    assert set(validation) == VALIDATION_KEYS
    assert validation == {
        "gaa_files": 0,
        "tax_files": 0,
        "saaodb_files": 0,
        "manifest_exists": False,
        "manifest_entries": 0,
        "manifest_orphans": [],
        "parquet_errors": [],
    }


# ---- AC1/AC2: the summary printer keeps rendering ---------------------------


def test_print_summary_human_renders_shim_dict_without_keyerror(
        tmp_path, monkeypatch, capsys):
    root = _combined_tree(tmp_path)
    _patch_cfg(monkeypatch, root, tmp_path / "validation_report.json")
    validation = validate_raw_data(logging.getLogger("test_shim"))

    print_summary(_results(), validation, json_output=False)

    out = capsys.readouterr().out
    assert "EXTRACTION SUMMARY" in out
    assert "GAA Files:" in out
    assert "Manifest Entries:" in out
    assert str(validation["gaa_files"]) in out
    assert str(validation["manifest_entries"]) in out


def test_print_summary_json_renders_shim_dict_without_keyerror(
        tmp_path, monkeypatch, capsys):
    root = _combined_tree(tmp_path)
    _patch_cfg(monkeypatch, root, tmp_path / "validation_report.json")
    validation = validate_raw_data(logging.getLogger("test_shim"))

    print_summary(_results(), validation, json_output=True)

    out = capsys.readouterr().out
    doc = json.loads(out)
    assert doc["validation"] == validation


# ---- AC2: ingest contract is unchanged --------------------------------------


def test_ingest_import_and_call_shape_unchanged():
    """``scripts/ingest.py`` imports ``validate_raw_data`` and calls it as
    ``validate_raw_data(logger)`` — the public contract must not change."""
    from src.orchestration.runner import validate_raw_data as vrd
    assert callable(vrd)
    assert vrd.__code__.co_argcount == 1