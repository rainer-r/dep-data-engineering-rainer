"""DBM SAAODB validator tests — htm + 1-page pdf stubs, fully offline."""

from src.validation.ph_saaodb import SAAODBValidator
from tests.conftest import SCHEMAS_DIR, make_saaodb_tree


def test_good_htm_and_l1_pdf_checks(saaodb_validator, by_id):
    rep = saaodb_validator.validate()
    ids = by_id(rep)
    assert ids["saaodb.expected_schema"][0].passed
    # structural checks for the one htm stub
    assert ids["saaodb.htm_readable"][0].passed
    assert ids["saaodb.htm_header_vocab"][0].passed
    assert ids["saaodb.htm_expense_group_header"][0].passed
    # L1 checks for the one pdf stub
    assert ids["saaodb.pdf_magic"][0].passed
    assert ids["saaodb.pdf_openable"][0].passed
    # the 1-page blank stub must fail the should-tier page/vocab checks
    assert not ids["saaodb.pdf_min_pages"][0].passed
    assert "saaodb.pdf_header_vocab" in ids
    assert not ids["saaodb.pdf_header_vocab"][0].passed
    # drift check is skipped offline and still passes
    drift = ids["saaodb.live_source_drift"][0]
    assert drift.passed
    assert "skipped" in drift.detail


def test_bad_htm_fails_vocab_and_group_header(tmp_path, by_id):
    root = make_saaodb_tree(tmp_path, good_htm=False, with_pdf=False)
    v = SAAODBValidator(raw_dir=root, schema_dir=SCHEMAS_DIR, skip_live=True)
    ids = by_id(v.validate())
    assert ids["saaodb.htm_readable"][0].passed
    assert not ids["saaodb.htm_header_vocab"][0].passed
    assert not ids["saaodb.htm_expense_group_header"][0].passed


def test_fixture_fails_only_completeness_gates(saaodb_validator, by_id):
    # The mini fixture trips the completeness gates (61 files / 61 quarters),
    # so the report is not fully green — but the *content* checks all pass and
    # the only must failures are the two completeness gates.
    rep = saaodb_validator.validate()
    must_failed = {r.check for r in rep.results
                   if r.severity == "must" and not r.passed}
    assert must_failed == {"saaodb.file_count", "saaodb.quarter_coverage"}
    ids = by_id(rep)
    # should-tier L1 checks still fail as designed on the 1-page blank stub
    assert ids["saaodb.pdf_min_pages"][0].passed is False
    assert ids["saaodb.pdf_header_vocab"][0].passed is False


def test_extension_by_period_for_fixture(tmp_path, by_id):
    # 2011Q1 -> htm (<=2014Q2), 2026Q1 -> pdf (>=2014Q3): both correct
    root = make_saaodb_tree(tmp_path, good_htm=True, with_pdf=True)
    v = SAAODBValidator(raw_dir=root, schema_dir=SCHEMAS_DIR, skip_live=True)
    ids = by_id(v.validate())
    assert ids["saaodb.extension_by_period"][0].passed
    assert ids["saaodb.quarter_coverage"][0].passed is False  # 2 quarters != 61