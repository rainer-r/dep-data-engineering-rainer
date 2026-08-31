"""Global validator tests - mini manifest fixtures exercise pass/fail paths."""

from src.validation.global_checks import GlobalValidator
from tests.conftest import GLOBAL_FILES, GLOBAL_UNREGISTERED, make_manifest_tree

_MISSING_TARGET = "saaodb/2026_Q2_2nd_Quarter.pdf"
_CORRUPT_TARGET = "gaa/gaa.parquet"
_UNREGISTERED = GLOBAL_UNREGISTERED[0]


def _validator(root):
    return GlobalValidator(raw_dir=root, manifest_file=root / "manifest.json")


def test_validator_source_is_global(tmp_path):
    v = _validator(tmp_path)
    assert v.source == "global"


def test_manifest_checks_pass_when_entries_on_disk(global_validator, by_id):
    rep = global_validator.validate()
    ids = by_id(rep)
    assert ids["global.manifest_exists"][0].passed
    assert ids["global.manifest_parseable"][0].passed
    assert ids["global.manifest_files_on_disk"][0].passed
    assert ids["global.manifest_files_on_disk"][0].expected == len(GLOBAL_FILES)
    # one checksum result per registered file, each passing
    checksum_ids = sorted(k for k in ids if k.startswith("global.checksum."))
    assert checksum_ids == [
        "global.checksum.%s" % rel for rel in sorted(GLOBAL_FILES)
    ]
    for cid in checksum_ids:
        assert ids[cid][0].passed
        assert ids[cid][0].severity == "must"


def test_manifest_checks_are_must_and_no_schema_check(global_validator, by_id):
    ids = by_id(global_validator.validate())
    assert ids["global.manifest_exists"][0].severity == "must"
    assert ids["global.manifest_parseable"][0].severity == "must"
    assert ids["global.manifest_files_on_disk"][0].severity == "must"
    assert "global.expected_schema" not in ids


def test_removed_registered_file_fails_checksum_with_path_named(tmp_path, by_id):
    root = make_manifest_tree(tmp_path, GLOBAL_FILES)
    (root / _MISSING_TARGET).unlink()
    ids = by_id(_validator(root).validate())
    r = ids["global.checksum.%s" % _MISSING_TARGET][0]
    assert not r.passed
    assert r.severity == "must"
    assert r.actual == "missing"
    assert _MISSING_TARGET in r.detail
    d = ids["global.manifest_files_on_disk"][0]
    assert not d.passed
    assert _MISSING_TARGET in d.detail


def test_corrupted_byte_fails_checksum_for_named_file(tmp_path, by_id):
    root = make_manifest_tree(tmp_path, GLOBAL_FILES, corrupt_rel=_CORRUPT_TARGET)
    ids = by_id(_validator(root).validate())
    r = ids["global.checksum.%s" % _CORRUPT_TARGET][0]
    assert not r.passed
    assert _CORRUPT_TARGET in r.detail
    assert r.actual != r.expected
    # every other registered file still matches its manifest checksum
    for rel in sorted(GLOBAL_FILES):
        if rel != _CORRUPT_TARGET:
            assert ids["global.checksum.%s" % rel][0].passed


def test_manifest_key_resolving_to_directory_fails_cleanly(tmp_path, by_id):
    root = make_manifest_tree(tmp_path, GLOBAL_FILES)
    d = root / _CORRUPT_TARGET
    d.unlink()      # registered key is a file on disk...
    d.mkdir()       # ...now a directory at the same manifest key
    rep = _validator(root).validate()
    ids = by_id(rep)
    od = ids["global.manifest_files_on_disk"][0]
    assert not od.passed
    assert _CORRUPT_TARGET in od.detail
    c = ids["global.checksum.%s" % _CORRUPT_TARGET][0]
    assert not c.passed
    assert c.actual == "missing"
    assert _CORRUPT_TARGET in c.detail
    assert rep.errors == []


def test_unreadable_registered_file_fails_without_raising(tmp_path, by_id, monkeypatch):
    root = make_manifest_tree(tmp_path, GLOBAL_FILES)
    target = str(root / _CORRUPT_TARGET)
    real_open = open

    def deny_target(path, *args, **kwargs):
        if str(path) == target:
            raise PermissionError("permission denied (fixture)")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", deny_target)
    rep = _validator(root).validate()
    ids = by_id(rep)
    c = ids["global.checksum.%s" % _CORRUPT_TARGET][0]
    assert not c.passed
    assert c.actual == "unreadable"
    assert _CORRUPT_TARGET in c.detail
    assert rep.errors == []


def test_unregistered_file_warns_hidden_never_reported(global_raw_dir, by_id):
    rep = _validator(global_raw_dir).validate()
    ids = by_id(rep)
    r = ids["global.unregistered_files"][0]
    assert not r.passed
    assert r.severity == "should"
    assert _UNREGISTERED in r.actual
    # hidden entries + dotfiles never surface anywhere in the report
    blob = " ".join("%s | %s | %s" % (x.check, x.actual, x.detail)
                     for x in rep.results)
    assert ".cache" not in blob
    assert ".gitkeep" not in blob
    assert "stale.parquet" not in blob


def test_missing_manifest_fails_three_checks_without_raising(tmp_path, by_id):
    root = make_manifest_tree(tmp_path, GLOBAL_FILES)
    (root / "manifest.json").unlink()
    rep = _validator(root).validate()
    ids = by_id(rep)
    assert not ids["global.manifest_exists"][0].passed
    assert not ids["global.manifest_parseable"][0].passed
    assert not ids["global.manifest_files_on_disk"][0].passed
    assert not any(k.startswith("global.checksum.") for k in ids)
    u = ids["global.unregistered_files"][0]
    assert u.passed
    assert u.actual == "skipped"
    assert rep.to_dict()["source"] == "global"
    assert rep.errors == []


def test_unparseable_manifest_fails_parseable_and_on_disk(tmp_path, by_id):
    root = make_manifest_tree(tmp_path, GLOBAL_FILES)
    (root / "manifest.json").write_text("{not json", encoding="utf-8")
    rep = _validator(root).validate()
    ids = by_id(rep)
    assert ids["global.manifest_exists"][0].passed  # the file exists
    assert not ids["global.manifest_parseable"][0].passed
    assert not ids["global.manifest_files_on_disk"][0].passed
    assert rep.errors == []


def test_inherited_load_manifest_degrades_to_empty_dict(tmp_path):
    root = make_manifest_tree(tmp_path, GLOBAL_FILES)
    v = _validator(root)
    assert set(v.load_manifest()) == set(GLOBAL_FILES)
    (root / "manifest.json").unlink()
    assert _validator(root).load_manifest() == {}
    (root / "manifest.json").write_text("{not json", encoding="utf-8")
    assert _validator(root).load_manifest() == {}
