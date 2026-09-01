"""Tests for the rendered data dictionaries (``scripts/render_dictionary.py``).

Renders the *committed* expected-schema artifacts
(``tests.conftest.SCHEMAS_DIR``) into temp dirs — fully offline — and then
asserts the ticket's acceptance criteria:

- AC1: the three markdown files exist and cover schema, coverage and
  known-good literals from the JSON.
- AC2: re-rendering is deterministic — output matches byte-for-byte.
- AC3: every caveat / ``to-verify`` annotation appears verbatim.

Anti-tautology rule: the literals asserted below are written out as constants,
never read back from the artifact being rendered.
"""

from __future__ import annotations

from scripts.render_dictionary import render_all
from tests.conftest import SCHEMAS_DIR


def _render_twice(tmp_path):
    first = render_all(SCHEMAS_DIR, tmp_path / "first")
    second = render_all(SCHEMAS_DIR, tmp_path / "second")
    return first, second


# ---- AC2: deterministic, byte-identical re-render --------------------------

def test_render_all_writes_the_three_expected_markdown_files(tmp_path):
    first, _ = _render_twice(tmp_path)

    # the three outputs named in the ticket (anti-tautology: literal constant)
    assert {p.name for p in first} == {"gaa.md", "bir_tax.md", "saaodb.md"}
    for path in first:
        assert path.read_text(encoding="utf-8")  # non-empty


def test_rerender_is_byte_identical(tmp_path):
    first, second = _render_twice(tmp_path)

    by_name = {p.name: p for p in first}
    for path in second:
        assert path.read_bytes() == by_name[path.name].read_bytes()


# ---- AC1: schema, coverage and known-good literals from the JSON -----------

def test_gaa_markdown_contains_columns_table_coverage_and_literals(tmp_path):
    render_all(SCHEMAS_DIR, tmp_path)

    text = (tmp_path / "gaa.md").read_text(encoding="utf-8")
    assert "| name | type | nullable | description |" in text
    assert "## coverage" in text
    # known-good literal curated in the GAA artifact (row count, 2026-08-30)
    assert "4538396" in text


# ---- AC3: caveats / to-verify annotations reproduced verbatim --------------

def test_caveat_annotations_rendered_verbatim(tmp_path):
    render_all(SCHEMAS_DIR, tmp_path)

    bir = (tmp_path / "bir_tax.md").read_text(encoding="utf-8")
    assert "not yet anchored" in bir               # literal_anchors caveat

    gaa = (tmp_path / "gaa.md").read_text(encoding="utf-8")
    assert "stale upstream metadata" in gaa        # coverage_anchors note

    saaodb = (tmp_path / "saaodb.md").read_text(encoding="utf-8")
    assert "HTML tables" in saaodb                 # format_note
    # filename_pattern reproduced verbatim: the committed artifact's value is
    # over-escaped (``\\\\s`` in JSON -> ``\\s`` decoded), and the markdown
    # must carry those two-backslash sequences untouched.
    assert "20\\\\d{2}" in saaodb                   # ^...20\d{2}...