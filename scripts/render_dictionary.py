"""
TaxTracePH — Rendered Data Dictionaries

Reads each committed expected-schema artifact (``data/reference/schemas/<slug>.json``)
and writes a human-readable data dictionary to
``data/data-dictionary/<slug>.md`` (the user-approved location). The JSON stays
the single source of truth; the markdown is a derived artifact and is committed
alongside it. Nothing is hand-maintained in the markdown.

Rendering is deterministic — sorted keys, sorted columns, sorted rows — so a
re-run is byte-identical (AC2). The renderer walks the whole document key by
key (only the identity header block and the fixed columns-table format are
curated), so every caveat / ``to-verify`` annotation in the JSON (e.g.
``literal_anchors.published_total_literals``, stale-README notes,
``format_note``) is reproduced verbatim with no per-caveat handling (AC3),
and future artifact keys render automatically.

Usage:
  python scripts/render_dictionary.py                      # render all three
  python scripts/render_dictionary.py --source gaa         # render one
  python scripts/render_dictionary.py --source gaa,saaodb  # render several
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Mapping, Optional, Sequence

# Ensure src/ is on path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import CONFIG as cfg

# Schema filename slugs. Note ``bir_tax`` (not ``tax``): it matches
# ``schema_name="bir_tax"`` on the tax validator, while the artifact's ``source``
# field remains ``"tax"`` — so the renderer must not assume ``source == slug``.
RENDER_SOURCES = ("gaa", "bir_tax", "saaodb")

# Identity keys rendered as the opening header block, in a fixed readable order.
_META_ORDER = ("source", "source_url", "format", "format_note", "grain")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="TaxTracePH Rendered Data Dictionaries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/render_dictionary.py                     # render all three
  python scripts/render_dictionary.py --source gaa        # render one
  python scripts/render_dictionary.py --source gaa,saaodb # render several
        """,
    )
    parser.add_argument(
        "--source",
        type=str,
        default="all",
        help=("Comma-separated schema slugs to render (default: all). Choices: "
              "%s. Example: --source bir_tax" % ", ".join(RENDER_SOURCES)),
    )
    return parser.parse_args(argv)


# ---- deterministic value formatting ----------------------------------------

def _scalar(value) -> str:
    """String form of a scalar for rendering (null/bool get plain words)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _plain(value) -> str:
    """Plain deterministic text for a scalar or scalar list (no escaping)."""
    if isinstance(value, list):
        return ", ".join(_scalar(v) for v in _sort_scalars(value))
    return _scalar(value)


def _escape_cell(value) -> str:
    """Pipe-escaped text for a markdown table cell (scalars and lists)."""
    return _plain(value).replace("|", "\\|")


def _sort_scalars(values: Sequence) -> List:
    """Sort a scalar list deterministically; mixed int/str stays safe via repr."""
    try:
        return sorted(values)
    except TypeError:
        return sorted(values, key=repr)


def _row_key(row: Mapping) -> tuple:
    """Stable sort key for a row of a list-of-dicts table."""
    if "name" in row:
        return ("name", str(row["name"]))
    if "relative_path" in row:
        return ("relative_path", str(row["relative_path"]))
    return ("generic", repr(sorted((str(k), str(v)) for k, v in row.items())))


def _render_table(rows: Sequence[Mapping]) -> str:
    """Render a list of row dicts as a markdown table (rows sorted)."""
    rows = sorted(rows, key=_row_key)
    if rows and all({"name", "type", "nullable", "description"} <= set(r)
                    for r in rows):
        headers = ["name", "type", "nullable", "description"]
    else:
        headers = sorted({key for r in rows for key in r})
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        cells = [_escape_cell(row.get(h, "")) for h in headers]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ---- generic key-by-key markdown renderer ----------------------------------

def _value_lines(value, indent: int) -> List[str]:
    """Render a JSON value as markdown lines at the given bullet indent."""
    pad = "  " * indent
    if isinstance(value, Mapping):
        lines = []
        for key, sub in sorted(value.items(), key=lambda kv: kv[0]):
            if isinstance(sub, (Mapping, list)):
                lines.append(f"{pad}- **{key}:**")
                lines.extend(_value_lines(sub, indent + 1))
            else:
                lines.append(f"{pad}- **{key}:** {_plain(sub)}")
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{pad}- (empty)"]
        if all(isinstance(item, Mapping) for item in value):
            return [_render_table(value)]
        return [f"{pad}- {_plain(v)}" for v in _sort_scalars(value)]
    return [f"{pad}{_plain(value)}"]


def render_dictionary(schema: Mapping) -> str:
    """Render one expected-schema JSON object as deterministic markdown."""
    if not isinstance(schema, Mapping):
        raise ValueError("expected-schema artifact must be a JSON object")

    title = _scalar(schema.get("source_name", "Data Dictionary"))
    lines = [f"# Data Dictionary — {title}", ""]

    # header block: identity keys in the fixed readable order above
    for key in _META_ORDER:
        if key in schema:
            lines.append(f"- **{key}:** {_plain(schema[key])}")
    lines.append("")

    # every remaining top-level key, sorted, becomes a section
    # (``source_name`` is already the H1 title, not a separate section)
    for key in sorted(k for k in schema
                      if k not in _META_ORDER and k != "source_name"):
        lines.append(f"## {key}")
        lines.append("")
        lines.extend(_value_lines(schema[key], 0))
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def render_all(schema_dir: Path, output_dir: Path,
               slugs: Optional[Sequence[str]] = None) -> List[Path]:
    """Render ``<slug>.json`` -> ``<slug>.md`` for each requested slug.

    Returns the written output paths (in slug order). ``output_dir`` is
    created if missing; overwriting existing markdown is intentional.
    """
    schema_dir = Path(schema_dir)
    output_dir = Path(output_dir)
    slugs = tuple(slugs) if slugs is not None else RENDER_SOURCES
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for slug in sorted(slugs):
        schema_path = schema_dir / f"{slug}.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        out_path = output_dir / f"{slug}.md"
        out_path.write_text(render_dictionary(schema), encoding="utf-8")
        written.append(out_path)
    return written


def main(argv: Optional[List[str]] = None) -> int:
    """Renderer CLI entrypoint."""
    args = parse_args(argv)

    if args.source == "all":
        slugs = list(RENDER_SOURCES)
    else:
        requested = {s.strip().lower() for s in args.source.split(",")
                     if s.strip()}
        invalid = sorted(requested - set(RENDER_SOURCES))
        if invalid:
            names = ", ".join(invalid)
            print(f"Error: Invalid source(s): {names}. Valid: "
                  f"{', '.join(RENDER_SOURCES)}", file=sys.stderr)
            return 1
        slugs = [s for s in RENDER_SOURCES if s in requested]

    try:
        written = render_all(cfg["SCHEMAS_DIR"], cfg["DICTIONARY_DIR"], slugs)
    except (OSError, ValueError) as exc:
        print(f"Error: cannot render data dictionaries: {exc}", file=sys.stderr)
        return 1

    for path in written:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())