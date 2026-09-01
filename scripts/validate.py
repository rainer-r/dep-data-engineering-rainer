"""
TaxTracePH — Raw Data Validation Runner

Unified entrypoint for the validation layer (the pre-M3 raw-data gate):
- Runs the global validator plus any selected source validators
  (gaa, tax, saaodb) via ``src/validation.orchestrator.run_validation()``
- Always writes the combined report document to ``data/validation_report.json``
- Prints a compact human summary, or the report document as JSON (``--json``)
- Exits 0 on a clear run, 1 on any ``must`` failure or validator error,
  and 1 under ``--strict`` when any ``should`` also fails

Usage:
  python scripts/validate.py                    # validate all sources + global
  python scripts/validate.py --source gaa       # gaa + global only
  python scripts/validate.py --source gaa,tax   # gaa, tax + global
  python scripts/validate.py --strict           # escalate should failures to 1
  python scripts/validate.py --skip-live        # stay offline (no live fetch)
  python scripts/validate.py --json             # print report document as JSON
  python scripts/validate.py --quiet            # reduce log verbosity
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

# Ensure src/ is on path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import CONFIG as cfg
from src.orchestration.runner import setup_root_logger
from src.validation import run_validation

VALID_SOURCES = ("gaa", "tax", "saaodb")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="TaxTracePH Raw Data Validation Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/validate.py                         # validate all sources + global
  python scripts/validate.py --source gaa            # gaa + global only
  python scripts/validate.py --source gaa,tax        # gaa, tax + global
  python scripts/validate.py --strict                # escalate should failures
  python scripts/validate.py --skip-live             # stay fully offline
  python scripts/validate.py --json                  # print the report as JSON
  python scripts/validate.py --quiet                 # reduce log verbosity
        """,
    )
    parser.add_argument(
        "--source",
        type=str,
        default="all",
        help=("Comma-separated source names to validate (default: all). Choices: "
              "%s. Example: --source gaa,tax" % ", ".join(VALID_SOURCES)),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Escalate any should failure to a failing exit code",
    )
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="Stay offline: skip live source-drift network checks",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the combined report document as JSON to stdout (the report file is still always written)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Reduce log output to WARNING level only (root logger -> WARNING)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Validation CLI entrypoint; returns the orchestrator exit code.

    ``--source`` handling mirrors ``scripts/ingest.py``: ``"all"`` selects
    every source, anything else is split on commas, lowercased, and validated
    against ``VALID_SOURCES``; unknown names print the ingest-style error line
    to stderr and exit 1 without a traceback.
    """
    args = parse_args(argv)

    selected: Optional[List[str]] = None
    if args.source != "all":
        requested = {s.strip().lower() for s in args.source.split(",") if s.strip()}
        invalid = sorted(requested - set(VALID_SOURCES))
        if invalid:
            names = ", ".join(invalid)
            print(f"Error: Invalid source(s): {names}. Valid: "
                  f"{', '.join(VALID_SOURCES)}", file=sys.stderr)
            return 1
        selected = [s for s in VALID_SOURCES if s in requested]

    setup_root_logger(quiet=args.quiet)

    exit_code = run_validation(
        selected=selected,
        strict=args.strict,
        skip_live=args.skip_live,
        print_summary=not args.json,
    )

    if args.json:
        # The orchestrator always writes the report document to
        # cfg["VALIDATION_REPORT_FILE"]; under --json we print that document
        # to stdout, so a CI consumer gets exactly what was written.
        report_path = cfg["VALIDATION_REPORT_FILE"]
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                document = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error: cannot read validation report {report_path} for "
                  f"--json: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(document, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
