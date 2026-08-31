"""GAA validator tests — mini parquet fixtures exercise pass and must-fail paths."""

from src.validation.ph_gaa import GAAValidator
from tests.conftest import SCHEMAS_DIR, make_gaa_tree


def test_mini_parquet_layout_and_fail_paths(gaa_validator, by_id):
    rep = gaa_validator.validate()
    ids = by_id(rep)
    assert ids["gaa.expected_schema"][0].passed
    assert ids["gaa.files_present"][0].passed
    assert ids["gaa.parquet_magic"][0].passed
    assert ids["gaa.column_set"][0].passed          # 22-column contract holds
    assert ids["gaa.column_types"][0].passed        # dtypes match the artifact
    # deliberately wrong literals must fail (anti-tautology: literals written out):
    assert not ids["gaa.row_count"][0].passed
    assert ids["gaa.row_count"][0].actual == 3      # mini has 3 rows
    assert not ids["gaa.year_coverage"][0].passed


def test_expected_schema_is_first_result(gaa_validator):
    rep = gaa_validator.validate()
    assert rep.results[0].check == "gaa.expected_schema"
    assert rep.results[0].passed


def test_unexpected_exp_class_codes_fail(tmp_path, by_id):
    root = make_gaa_tree(tmp_path, exp_codes=["99"], reg_ids=["01"])
    v = GAAValidator(raw_dir=root, schema_dir=SCHEMAS_DIR)
    ids = by_id(v.validate())
    assert not ids["gaa.exp_class_codes"][0].passed
    assert ids["gaa.exp_class_codes"][0].actual == ["99"]


def test_unexpected_region_codes_warn(tmp_path, by_id):
    root = make_gaa_tree(tmp_path, reg_ids=["ZZ"], exp_codes=["1"])
    v = GAAValidator(raw_dir=root, schema_dir=SCHEMAS_DIR)
    ids = by_id(v.validate())
    assert ids["gaa.region_codes"][0].passed is False
    assert ids["gaa.region_codes"][0].severity == "should"


def test_known_negative_anomaly_literal(tmp_path, by_id):
    # The real dataset has exactly 11 rows with amt < 0; a fixture with a
    # different count must surface as the documented-anomaly should result.
    root = make_gaa_tree(tmp_path, neg_count=2)
    v = GAAValidator(raw_dir=root, schema_dir=SCHEMAS_DIR)
    ids = by_id(v.validate())
    assert ids["gaa.negative_amounts"][0].passed is False
    assert ids["gaa.negative_amounts"][0].actual == 2