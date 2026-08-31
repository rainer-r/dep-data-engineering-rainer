"""Tests for the validation base contract: results, reports, registry check."""

from src.validation.base import (
    SEVERITY_MUST,
    SEVERITY_SHOULD,
    ValidationReport,
    ValidationResult,
)
from src.validation.ph_gaa import GAAValidator
from tests.conftest import SCHEMAS_DIR


def test_result_to_dict_serialises_sets():
    r = ValidationResult("demo.check", SEVERITY_SHOULD, True,
                         actual={"b", "a"}, expected={"x", "y"})
    d = r.to_dict()
    assert d["check"] == "demo.check"
    assert d["actual"] == ["a", "b"]
    assert d["expected"] == ["x", "y"]


def test_report_passed_with_only_should_failures():
    rep = ValidationReport(source="demo")
    rep.add(ValidationResult("a.should_check", SEVERITY_SHOULD, False,
                             actual=1, expected=2))
    assert rep.passed()  # should failures alone do not fail the report
    assert rep.counts()["failed_should"] == 1
    assert rep.counts()["total"] == 1


def test_report_failed_when_must_failure():
    rep = ValidationReport(source="demo")
    rep.add(ValidationResult("a.must_check", SEVERITY_MUST, False))
    assert not rep.passed()
    assert rep.counts()["failed_must"] == 1


def test_report_failed_when_error_recorded():
    rep = ValidationReport(source="demo")
    rep.errors.append("boom")
    assert not rep.passed()


def test_register_schema_passes_with_committed_artifact(tmp_path):
    v = GAAValidator(raw_dir=tmp_path, schema_dir=SCHEMAS_DIR)
    r = v.register_schema_check()
    assert r.check == "gaa.expected_schema"
    assert r.severity == SEVERITY_MUST
    assert r.passed
    assert r.actual == "gaa"
    assert r.expected == "gaa"


def test_register_schema_fails_when_missing(tmp_path):
    v = GAAValidator(raw_dir=tmp_path, schema_dir=tmp_path)  # empty dir
    r = v.register_schema_check()
    assert not r.passed
    assert r.actual == "missing"


def test_register_schema_fails_on_unparseable(tmp_path):
    (tmp_path / "gaa.json").write_text("{not json", encoding="utf-8")
    v = GAAValidator(raw_dir=tmp_path, schema_dir=tmp_path)
    r = v.register_schema_check()
    assert not r.passed
    assert "parseable" in r.detail.lower()


def test_register_schema_fails_on_source_mismatch(tmp_path):
    (tmp_path / "gaa.json").write_text('{"source": "tax"}', encoding="utf-8")
    v = GAAValidator(raw_dir=tmp_path, schema_dir=tmp_path)
    r = v.register_schema_check()
    assert not r.passed
    assert r.actual == "tax"
    assert r.expected == "gaa"


def test_load_schema_returns_empty_when_missing(tmp_path):
    v = GAAValidator(raw_dir=tmp_path, schema_dir=tmp_path)
    assert v.load_schema() == {}