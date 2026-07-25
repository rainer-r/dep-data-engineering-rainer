"""
Phase 2 — Data Extraction Runner

Unified entrypoint for Milestone M2 extraction:
- Triggers BIR Tax Collection scraping (ph_tax_collection)
- Triggers Hugging Face GAA dataset extraction (ph_gaa)
- Validates outputs in data/raw/
- Logs full execution details via a single root logger

Usage:
  python scripts/ingest.py                         # Run both extractors
  python scripts/ingest.py --source gaa            # Run only GAA extractor
  python scripts/ingest.py --source tax            # Run only Tax extractor
  python scripts/ingest.py --source gaa,tax        # Run specific sources
  python scripts/ingest.py --source saaodb         # Run only SAAODB extractor
  python scripts/ingest.py --source gaa,tax,saaodb # Run all extractors
  python scripts/ingest.py --dry-run               # Validate setup without downloading
  python scripts/ingest.py --json                  # Output JSON summary
  python scripts/ingest.py --quiet                 # Reduce log verbosity
  python scripts/ingest.py --no-selenium           # Disable Selenium fallback
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure src/ is on path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.orchestration.runner import (
    check_selenium_available,
    print_summary,
    run_dry_run,
    run_extractor,
    setup_root_logger,
    validate_raw_data,
)
from src.extraction.ph_gaa import GAAExtractor
from src.extraction.ph_saaodb import DBMSAAODBExtractor
from src.extraction.ph_tax_collection import TaxCollectionExtractor


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="TaxTracePH Phase 2 Data Extraction Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/ingest.py                         # Run both extractors
  python scripts/ingest.py --source gaa            # Run only GAA extractor
  python scripts/ingest.py --source tax            # Run only Tax extractor
  python scripts/ingest.py --source gaa,tax        # Run specific sources
  python scripts/ingest.py --dry-run               # Validate setup without downloading
  python scripts/ingest.py --json                  # Output JSON summary
  python scripts/ingest.py --quiet                 # Reduce log verbosity
  python scripts/ingest.py --no-selenium           # Disable Selenium fallback
        """,
    )
    parser.add_argument(
        "--source",
        type=str,
        default="all",
        help='Comma-separated source names to run (default: all). Choices: gaa, tax, saaodb. Example: --source gaa,tax',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and environment without downloading data",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Reduce log output to WARNING level only",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output summary as JSON to stdout (for CI/CD parsing)",
    )
    parser.add_argument(
        "--no-selenium",
        action="store_true",
        help="Disable Selenium fallback in Tax extractor (useful for CI/headless)",
    )
    return parser.parse_args()


def main() -> int:
    """Main extraction entrypoint."""
    args = parse_args()

    # Parse --source flag (comma-separated, default = all)
    if args.source == "all":
        selected_sources = {"gaa", "tax", "saaodb"}
    else:
        selected_sources = set(s.strip().lower() for s in args.source.split(","))
        valid_sources = {"gaa", "tax", "saaodb"}
        invalid = selected_sources - valid_sources
        if invalid:
            print(f"Error: Invalid source(s): {', '.join(sorted(invalid))}. Valid: gaa, tax, saaodb", file=sys.stderr)
            return 1

    logger: logging.Logger = setup_root_logger(quiet=args.quiet)

    # Dry-run mode
    if args.dry_run:
        return run_dry_run(
            logger,
            args.no_selenium,
            "gaa" in selected_sources,
            "tax" in selected_sources,
            "saaodb" in selected_sources,
        )

    logger.info("=" * 60)
    logger.info("TaxTracePH — Phase 2 Data Extraction Runner Starting")
    logger.info("=" * 60)

    # Check Selenium availability upfront
    selenium_available = False
    if not args.no_selenium:
        selenium_available = check_selenium_available()
        if selenium_available:
            logger.info("Selenium: Chrome/ChromeDriver available")
        else:
            logger.warning("Selenium: Chrome/ChromeDriver NOT available (fallback will be skipped)")
    else:
        logger.info("Selenium: Disabled via --no-selenium flag")

    # Build list of extractors to run based on --source selection
    extractors_to_run = []

    if "gaa" in selected_sources:
        gaa_extractor = GAAExtractor()
        extractors_to_run.append(("GAA (Hugging Face)", gaa_extractor))

    if "tax" in selected_sources:
        tax_extractor = TaxCollectionExtractor(use_selenium=not args.no_selenium)
        extractors_to_run.append(("BIR Tax Collection", tax_extractor))

    if "saaodb" in selected_sources:
        saaodb_extractor = DBMSAAODBExtractor()
        extractors_to_run.append(("DBM SAAODB", saaodb_extractor))

    # Track results
    results = {
        "extractors": {},
        "overall_success": False,
    }

    # Run extractors sequentially with error isolation
    for name, extractor in extractors_to_run:
        result = run_extractor(name, extractor, logger)
        results["extractors"][name] = result

    # Validate outputs
    logger.info("=== Validating raw data outputs ===")
    validation = validate_raw_data(logger)

    # Determine overall success
    results["overall_success"] = any(
        r.get("success", False) for r in results["extractors"].values()
    )

    # Print summary
    print_summary(results, validation, json_output=args.json)

    if results["overall_success"]:
        logger.info("Overall: SUCCESS (at least one extractor produced data)")
        return 0
    else:
        logger.error("Overall: FAILURE (no extractor produced data)")
        return 1


if __name__ == "__main__":
    sys.exit(main())