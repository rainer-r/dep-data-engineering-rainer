"""
TaxTracePH — Extraction Runner

Shared orchestration logic used by scripts/ingest.py:
- Root logger setup (single console + file handler on root logger)
- Selenium availability check
- Error-isolated extractor execution with source-dependent failure thresholds
- Post-extraction validation (file counts, manifest consistency, Parquet integrity)
- Human-readable / JSON summary output
- Dry-run environment validation
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl

from src.core.config import CONFIG as cfg


def setup_root_logger(quiet: bool = False) -> logging.Logger:
    """Configure a single root logger with console + file handler.

    Child loggers (ingest.ph_gaa, ingest.ph_tax_collection, etc.) will
    propagate to this root — no need for per-extractor handlers.
    """
    log_level = logging.WARNING if quiet else logging.INFO
    root = logging.getLogger()
    root.setLevel(log_level)

    # Avoid adding duplicate handlers on re-entry
    if not root.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

        # File handler
        cfg["LOG_FILE"].parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(cfg["LOG_FILE"])
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    return root


def check_selenium_available() -> bool:
    """Check if Chrome/ChromeDriver is available for Selenium."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=chrome_options)
        driver.quit()
        return True
    except Exception:
        return False


def run_extractor(name: str, extractor, logger: logging.Logger) -> dict:
    """Run a single extractor with error isolation and logging.

    Parameters
    ----------
    name : str
        Human-readable label (e.g. "GAA (Hugging Face)").
    extractor :
        Object with an ``extract() -> bool`` method.
    logger : logging.Logger
        Logger for orchestration messages.

    Returns
    -------
    dict
        Result summary with keys: name, success, files_downloaded,
        files_skipped, error, duration_seconds.
    """
    logger.info("=== Starting %s extraction ===", name)
    start_time = time.time()
    result: dict = {
        "name": name,
        "success": False,
        "files_downloaded": 0,
        "files_skipped": 0,
        "error": None,
        "duration_seconds": 0.0,
    }
    try:
        success = extractor.extract()
        result["success"] = success

        # Source-dependent failure treatment
        # GAA is a stable Hugging Face dataset — 0 files likely means something broke.
        # BIR is a government website scrape — 0 files could be transient.
        if success:
            logger.info("=== %s extraction completed successfully ===", name)
        else:
            if "GAA" in name or "gaa" in name.lower():
                logger.error(
                    "=== %s extraction returned no data — this is likely a "
                    "pipeline issue (repo missing / API change) ===",
                    name,
                )
            else:
                logger.warning(
                    "=== %s extraction returned no data (non-fatal — "
                    "scraping may be transient) ===",
                    name,
                )
    except Exception as e:
        result["error"] = str(e)
        logger.error(
            "=== %s extraction failed with exception: %s ===", name, e,
            exc_info=True,
        )
    finally:
        result["duration_seconds"] = round(time.time() - start_time, 2)
    return result


def validate_raw_data(logger: logging.Logger) -> dict:
    """Validate that raw data directories have expected content.

    Checks:
    1. File counts in GAA and Tax directories
    2. Manifest existence and entry count
    3. Manifest-file consistency (every manifest path exists on disk)
    4. Parquet magic-byte integrity check (catches truncated files)

    Returns
    -------
    dict
        Validation results: gaa_files, tax_files, manifest_exists,
        manifest_entries, manifest_orphans (paths in manifest but
        missing from disk), parquet_errors (corrupt files).
    """
    results: dict = {
        "gaa_files": 0,
        "tax_files": 0,
        "saaodb_files": 0,
        "saaodb_xlsx_total": 0,
        "saaodb_xlsx_valid": 0,
        "saaodb_xlsx_corrupt": 0,
        "saaodb_xlsx_errors": [],
        "manifest_exists": False,
        "manifest_entries": 0,
        "manifest_orphans": [],
        "parquet_errors": [],
    }

    # ---- directory file counts ----
    gaa_dir: Path = cfg["GAA_RAW_DIR"]
    if gaa_dir.exists():
        results["gaa_files"] = len(
            [f for f in gaa_dir.rglob("*") if f.is_file() and not f.name.startswith(".git")]
        )
        logger.info("GAA raw directory: %d files in %s", results["gaa_files"], gaa_dir)

    tax_dir: Path = cfg["BIR_RAW_DIR"]
    if tax_dir.exists():
        results["tax_files"] = len(
            [f for f in tax_dir.rglob("*") if f.is_file() and not f.name.startswith(".git")]
        )
        logger.info("Tax raw directory: %d files in %s", results["tax_files"], tax_dir)

    saaodb_dir: Path = cfg["SAAODB_RAW_DIR"]
    if saaodb_dir.exists():
        results["saaodb_files"] = len(
            [f for f in saaodb_dir.rglob("*") if f.is_file() and not f.name.startswith(".git")]
        )
        logger.info("SAAODB raw directory: %d files in %s", results["saaodb_files"], saaodb_dir)

        # ---- SAAODB file integrity verification ----
        # The extractor primarily downloads .htm and .pdf files.
        # If any .xlsx files are present, verify them (expected sheets: SUMMARY, AGENCY, SUCs).
        # Missing .xlsx files is NOT an error — the extractor prioritises PDF/HTM.
        xlsx_files = [f for f in saaodb_dir.rglob("*.xlsx") if f.is_file()]

        for xlsx_file in xlsx_files:
            results["saaodb_xlsx_total"] += 1
            try:
                wb = openpyxl.load_workbook(xlsx_file, read_only=True)
                wb.close()
                results["saaodb_xlsx_valid"] += 1
            except Exception as e:
                results["saaodb_xlsx_corrupt"] += 1
                err_entry = {
                    "file": str(xlsx_file.relative_to(cfg["RAW_DATA_DIR"])),
                    "error": "corrupt",
                    "detail": str(e),
                }
                results["saaodb_xlsx_errors"].append(err_entry)
                logger.error("SAAODB workbook %s is corrupt: %s", xlsx_file.name, e)

        if results["saaodb_xlsx_total"] > 0:
            logger.info(
                "SAAODB xlsx verification: %d total, %d valid, %d corrupt",
                results["saaodb_xlsx_total"],
                results["saaodb_xlsx_valid"],
                results["saaodb_xlsx_corrupt"],
            )
        else:
            logger.info("SAAODB xlsx verification: no .xlsx files present")

    # ---- manifest checks ----
    manifest_file: Path = cfg["MANIFEST_FILE"]
    manifest: dict = {}

    if manifest_file.exists():
        try:
            with open(manifest_file, "r") as f:
                manifest = json.load(f)
            results["manifest_exists"] = True
            results["manifest_entries"] = len(manifest)
            logger.info(
                "Manifest: %d entries in %s", results["manifest_entries"], manifest_file
            )
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Manifest exists but could not be read: %s", e)
    else:
        logger.warning("Manifest not found at %s", manifest_file)

    # ---- manifest-file consistency ----
    for rel_path in manifest:
        disk_path = cfg["RAW_DATA_DIR"] / rel_path
        if not disk_path.exists():
            results["manifest_orphans"].append(rel_path)
            logger.warning(
                "Manifest entry missing from disk: %s (path: %s)", rel_path, disk_path
            )

    if not results["manifest_orphans"] and manifest:
        logger.info("Manifest-file consistency: all %d entries verified on disk", len(manifest))

    # ---- Parquet magic-byte check ----
    raw_dir: Path = cfg["RAW_DATA_DIR"]
    if raw_dir.exists():
        for parquet_file in raw_dir.rglob("*.parquet"):
            if parquet_file.is_file():
                try:
                    with open(parquet_file, "rb") as f:
                        magic = f.read(4)
                    if magic != b"PAR1":
                        results["parquet_errors"].append(str(parquet_file))
                        logger.warning("Corrupt Parquet header (missing PAR1 magic): %s", parquet_file)
                except IOError as e:
                    results["parquet_errors"].append(str(parquet_file))
                    logger.warning("Cannot read Parquet file %s: %s", parquet_file, e)

        if not results["parquet_errors"]:
            # Only log if we actually checked some files
            parquet_count = len(list(raw_dir.rglob("*.parquet")))
            if parquet_count > 0:
                logger.info("Parquet integrity: %d files passed magic-byte check", parquet_count)

    return results


def print_summary(results: dict, validation: dict, json_output: bool = False) -> None:
    """Print ingestion summary as human-readable table or JSON."""
    if json_output:
        output: dict = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "extractors": {},
            "validation": validation,
            "overall_success": results.get("overall_success", False),
        }
        for name, res in results.get("extractors", {}).items():
            output["extractors"][name] = {
                "success": res.get("success", False),
                "files_downloaded": res.get("files_downloaded", 0),
                "files_skipped": res.get("files_skipped", 0),
                "duration_seconds": res.get("duration_seconds", 0.0),
                "error": res.get("error"),
            }
        print(json.dumps(output, indent=2))
        return

    # Human-readable table
    print("=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)
    for name, res in results.get("extractors", {}).items():
        status = "PASS" if res.get("success") else "FAIL"
        print(f"{name:<25} {status}")
    print(f"\nValidation:")
    print(f"  GAA Files:          {validation['gaa_files']}")
    print(f"  Tax Files:          {validation['tax_files']}")
    print(f"  SAAODB Files:       {validation['saaodb_files']}")
    print(f"  Manifest Entries:   {validation['manifest_entries']}")
    print(f"  SAAODB XLSX Total:  {validation.get('saaodb_xlsx_total', 0)}")
    print(f"  SAAODB XLSX Valid:  {validation.get('saaodb_xlsx_valid', 0)}")
    print(f"  SAAODB XLSX Corrupt:{validation.get('saaodb_xlsx_corrupt', 0)}")
    if validation.get("manifest_orphans"):
        print(f"  Manifest Orphans:   {len(validation['manifest_orphans'])}")
    if validation.get("parquet_errors"):
        print(f"  Parquet Errors:     {len(validation['parquet_errors'])}")
    if validation.get("saaodb_xlsx_errors"):
        print(f"  SAAODB XLSX Errors: {len(validation['saaodb_xlsx_errors'])}")
    print("=" * 60)
    overall = "SUCCESS" if results.get("overall_success") else "FAILURE"
    print(f"Overall: {overall}")


def run_dry_run(
    logger: logging.Logger,
    no_selenium: bool,
    only_gaa: bool = False,
    only_tax: bool = False,
    only_saaodb: bool = False,
) -> int:
    """Validate configuration and environment without downloading.

    Checks: config values, directory writability, Selenium availability,
    extractor initialisation.

    Returns
    -------
    int
        0 if all checks pass, 1 otherwise.
    """
    from src.extraction.ph_gaa import GAAExtractor
    from src.extraction.ph_saaodb import DBMSAAODBExtractor
    from src.extraction.ph_tax_collection import TaxCollectionExtractor

    logger.info("=" * 60)
    logger.info("TaxTracePH — Extraction Runner (DRY RUN)")
    logger.info("=" * 60)

    checks: dict = {
        "config_loaded": True,
        "gaa_repo_id": bool(cfg.get("GAA_REPO_ID")),
        "bir_target_url": bool(cfg.get("BIR_TARGET_URL")),
        "dbm_saaodb_url": bool(cfg.get("DBM_SAAODB_URL")),
        "raw_data_dir_writable": False,
        "gaa_dir_writable": False,
        "tax_dir_writable": False,
        "saaodb_dir_writable": False,
        "manifest_writable": False,
        "selenium_available": False,
        "gaa_extractor_init": False,
        "tax_extractor_init": False,
        "saaodb_extractor_init": False,
    }

    # Check directory writability
    for dir_key, label in [
        ("RAW_DATA_DIR", "raw_data_dir"),
        ("GAA_RAW_DIR", "gaa_dir"),
        ("BIR_RAW_DIR", "tax_dir"),
        ("SAAODB_RAW_DIR", "saaodb_dir"),
    ]:
        d: Path = cfg[dir_key]
        try:
            d.mkdir(parents=True, exist_ok=True)
            test_file = d / ".write_test"
            test_file.touch()
            test_file.unlink()
            checks[f"{label}_writable"] = True
        except Exception as e:
            logger.error("%s not writable: %s", dir_key, e)

    # Manifest directory
    try:
        cfg["MANIFEST_FILE"].parent.mkdir(parents=True, exist_ok=True)
        test_file = cfg["MANIFEST_FILE"].parent / ".write_test"
        test_file.touch()
        test_file.unlink()
        checks["manifest_writable"] = True
    except Exception as e:
        logger.error("Manifest directory not writable: %s", e)

    # Selenium
    if not no_selenium:
        checks["selenium_available"] = check_selenium_available()
        if checks["selenium_available"]:
            logger.info("Selenium: Chrome/ChromeDriver available")
        else:
            logger.warning("Selenium: Chrome/ChromeDriver NOT available (fallback will be skipped)")
    else:
        logger.info("Selenium: Disabled via --no-selenium flag")

    # Extractor init (conditionally skipped if source not selected)
    if only_gaa or only_tax or only_saaodb:
        # When individual sources are selected, only init those
        if only_gaa:
            try:
                GAAExtractor()
                checks["gaa_extractor_init"] = True
                logger.info("GAAExtractor: Initialised successfully")
            except Exception as e:
                logger.error("GAAExtractor init failed: %s", e)
        if only_tax:
            try:
                TaxCollectionExtractor(use_selenium=not no_selenium)
                checks["tax_extractor_init"] = True
                logger.info("TaxCollectionExtractor: Initialised successfully")
            except Exception as e:
                logger.error("TaxCollectionExtractor init failed: %s", e)
        if only_saaodb:
            try:
                DBMSAAODBExtractor()
                checks["saaodb_extractor_init"] = True
                logger.info("DBMSAAODBExtractor: Initialised successfully")
            except Exception as e:
                logger.error("DBMSAAODBExtractor init failed: %s", e)
    else:
        # Default (--source all or no --source flag): init all extractors
        try:
            GAAExtractor()
            checks["gaa_extractor_init"] = True
            logger.info("GAAExtractor: Initialised successfully")
        except Exception as e:
            logger.error("GAAExtractor init failed: %s", e)

        try:
            TaxCollectionExtractor(use_selenium=not no_selenium)
            checks["tax_extractor_init"] = True
            logger.info("TaxCollectionExtractor: Initialised successfully")
        except Exception as e:
            logger.error("TaxCollectionExtractor init failed: %s", e)

        try:
            DBMSAAODBExtractor()
            checks["saaodb_extractor_init"] = True
            logger.info("DBMSAAODBExtractor: Initialised successfully")
        except Exception as e:
            logger.error("DBMSAAODBExtractor init failed: %s", e)

    # Summary
    logger.info("=" * 60)
    logger.info("DRY RUN RESULTS")
    logger.info("=" * 60)
    all_passed = True
    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        logger.info("%-30s %s", check, status)
    logger.info("=" * 60)

    return 0 if all_passed else 1