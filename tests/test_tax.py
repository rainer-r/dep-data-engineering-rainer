"""BIR tax validator tests — tiny workbook fixtures."""

from src.validation.ph_tax_collection import TaxCollectionValidator
from tests.conftest import (
    SCHEMAS_DIR,
    TAX_FILENAMES,
    _broken_partial_year,
    _good_partial_year,
    make_tax_tree,
)


def test_good_workbooks_pass_layout_contracts(tax_validator, by_id):
    rep = tax_validator.validate()
    ids = by_id(rep)
    assert ids["tax.expected_schema"][0].passed
    assert ids["tax.registered_files_present"][0].passed
    for r in ids.get("tax.sheet_expectations", []):
        assert r.passed, r.detail
    for r in ids.get("tax.layout_contract", []):
        assert r.passed, r.detail
    for name in ("tax.annual_year_columns", "tax.total_column_present",
                 "tax.notes_sheet_attribution"):
        assert ids[name][0].passed, f"{name}: {ids[name][0].detail}"
    assert ids["tax.unregistered_files"][0].passed


def test_broken_workbook_fails_layout(tmp_path, by_id):
    root = make_tax_tree(tmp_path)
    _broken_partial_year(root / "tax" / TAX_FILENAMES["partial"])
    v = TaxCollectionValidator(raw_dir=root, schema_dir=SCHEMAS_DIR)
    ids = by_id(v.validate())
    layout_fails = [r for r in ids.get("tax.layout_contract", []) if not r.passed]
    assert layout_fails
    assert "20260616" in layout_fails[0].detail


def test_corrupt_workbook_fails_openable(tax_raw_dir, by_id):
    (tax_raw_dir / "tax" / TAX_FILENAMES["partial"]).write_bytes(b"not an xlsx")
    v = TaxCollectionValidator(raw_dir=tax_raw_dir, schema_dir=SCHEMAS_DIR)
    ids = by_id(v.validate())
    assert "tax.registered_openable" in ids
    assert not ids["tax.registered_openable"][0].passed


def test_unregistered_workbook_warns(tax_raw_dir, by_id):
    _good_partial_year(tax_raw_dir / "tax" / "EXTRA_not_registered.xlsx")
    v = TaxCollectionValidator(raw_dir=tax_raw_dir, schema_dir=SCHEMAS_DIR)
    ids = by_id(v.validate())
    assert ids["tax.unregistered_files"][0].passed is False
    actual = ids["tax.unregistered_files"][0].actual or []
    assert any("EXTRA_not_registered.xlsx" in name for name in actual)