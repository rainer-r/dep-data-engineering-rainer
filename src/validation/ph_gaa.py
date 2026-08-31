"""Validator for the GAA source (bettergovph/gaa, Parquet on disk).

Contract: ``data/reference/schemas/gaa.json`` (data dictionary + expected
values anchored to the live Hugging Face card fetched 2026-08-30).
"""

from __future__ import annotations

import duckdb
import pyarrow.parquet as pq

from src.core.config import CONFIG as cfg
from src.validation.base import (
    SEVERITY_MUST,
    SEVERITY_SHOULD,
    BaseValidator,
    ValidationReport,
    ValidationResult,
)

_GAAPARQUET_REL = "gaa/gaa.parquet"
_GAAREADME_REL = "gaa/README.md"


class GAAValidator(BaseValidator):
    """Validates data/raw/gaa/ against the GAA expected-schema artifact."""

    source = "gaa"
    source_label = "GAA (bettergovph/gaa via Hugging Face)"

    # -- helpers ------------------------------------------------------------

    def _read_summary(self, parquet_path):
        """Cheap DuckDB aggregates over the parquet (avoids loading 350MB)."""
        con = duckdb.connect()
        sql = """
            SELECT
                count(*) AS n,
                list(DISTINCT year) AS years,
                list(DISTINCT uacs_exp_cd) AS exp_cd,
                list(DISTINCT uacs_reg_id) AS reg_id,
                sum(CASE WHEN amt < 0 THEN 1 ELSE 0 END) AS neg,
                sum(CASE WHEN prexc_level IS NULL THEN 1 ELSE 0 END) AS nul_prexc,
                sum(CASE WHEN sorder IS NULL THEN 1 ELSE 0 END) AS nul_sorder,
                sum(CASE WHEN uacs_operdiv_id IS NULL THEN 1 ELSE 0 END) AS nul_operdiv,
                sum(CASE WHEN uacs_div_dsc IS NULL THEN 1 ELSE 0 END) AS nul_div,
                sum(CASE WHEN uacs_oper_dsc IS NULL THEN 1 ELSE 0 END) AS nul_oper
            FROM read_parquet(?)
        """
        row = con.execute(sql, [str(parquet_path)]).fetchone()
        con.close()
        keys = [
            "row_count", "years", "exp_cd", "reg_id", "neg", "nul_prexc",
            "nul_sorder", "nul_operdiv", "nul_div", "nul_oper",
        ]
        return dict(zip(keys, row))

    # -- main ---------------------------------------------------------------

    def validate(self) -> ValidationReport:
        schema = self.load_schema()
        rep = self.report()
        rep.add(self.register_schema_check())

        parquet_path = self.raw_dir / _GAAPARQUET_REL
        readme_path = self.raw_dir / _GAAREADME_REL

        # files present -----------------------------------------------------
        present = [p.name for p in (parquet_path, readme_path) if p.exists()]
        missing = [p.name for p in (parquet_path, readme_path) if not p.exists()]
        rep.add(
            ValidationResult(
                "gaa.files_present",
                SEVERITY_MUST,
                not missing,
                detail="missing files: %s" % (missing or "none"),
                actual=len(present),
                expected=2,
            )
        )

        if not parquet_path.exists():
            for check_id in (
                "gaa.parquet_magic", "gaa.parquet_size", "gaa.row_count",
                "gaa.column_set", "gaa.column_types", "gaa.year_coverage",
                "gaa.exp_class_codes", "gaa.region_codes", "gaa.negative_amounts",
                "gaa.null_layout",
            ):
                rep.add(
                    ValidationResult(check_id, SEVERITY_MUST, False,
                                     detail="gaa.parquet missing; check skipped")
                )
            return rep

        # magic + size ------------------------------------------------------
        with open(parquet_path, "rb") as f:
            magic = f.read(4)
        size = parquet_path.stat().st_size
        expected_size = schema["coverage"]["size_bytes"]
        size_ok = abs(size - expected_size) <= expected_size * 0.01
        rep.add(
            ValidationResult(
                "gaa.parquet_magic", SEVERITY_MUST, magic == b"PAR1",
                detail="magic bytes %r" % magic, actual=magic, expected=b"PAR1",
            )
        )
        rep.add(
            ValidationResult(
                "gaa.parquet_size", SEVERITY_SHOULD, size_ok,
                detail="size %d vs expected %d (1%% tolerance)"
                % (size, expected_size), actual=size, expected=expected_size,
            )
        )

        # metadata (schema + row count) via pyarrow (cheap) -----------------
        pf = pq.ParquetFile(str(parquet_path))
        arrow = pf.schema_arrow
        actual_cols = [arrow.field(i).name for i in range(len(arrow))]
        actual_types = {arrow.field(i).name: str(arrow.field(i).type) for i in range(len(arrow))}

        expected_cols = [c["name"] for c in schema["columns"]]
        expected_types = {c["name"]: c["type"] for c in schema["columns"]}
        type_mismatch = {
            c: (actual_types.get(c), expected_types.get(c))
            for c in expected_types
            if actual_types.get(c) != expected_types.get(c)
        }

        rep.add(
            ValidationResult(
                "gaa.column_set", SEVERITY_MUST, set(actual_cols) == set(expected_cols),
                detail="column count %d" % len(actual_cols),
                actual=len(actual_cols), expected=len(expected_cols),
            )
        )
        rep.add(
            ValidationResult(
                "gaa.column_types", SEVERITY_SHOULD, not type_mismatch,
                detail="mismatches: %s" % (type_mismatch or "none"),
                actual=type_mismatch or None, expected=None,
            )
        )

        summary = self._read_summary(parquet_path)

        # row count (known-good literal anchored to live HF card) -----------
        expected_rows = schema["coverage"]["row_count"]
        rep.add(
            ValidationResult(
                "gaa.row_count", SEVERITY_MUST, summary["row_count"] == expected_rows,
                detail="on-disk row count vs live HF card", actual=summary["row_count"],
                expected=expected_rows,
            )
        )

        # year coverage ------------------------------------------------------
        expected_years = schema["coverage"]["fiscal_years"]
        rep.add(
            ValidationResult(
                "gaa.year_coverage", SEVERITY_MUST, set(summary["years"]) == set(expected_years),
                detail="years on disk: %s" % summary["years"], actual=summary["years"],
                expected=expected_years,
            )
        )

        # expense class + region codes ---------------------------------------
        allowed_exp = set(schema["reference_values"]["uacs_exp_cd_allowed"])
        bad_exp = sorted(set(summary["exp_cd"]) - allowed_exp)
        rep.add(
            ValidationResult(
                "gaa.exp_class_codes", SEVERITY_MUST, not bad_exp,
                detail="unexpected expense codes: %s" % (bad_exp or "none"),
                actual=sorted(set(summary["exp_cd"])), expected=sorted(allowed_exp),
            )
        )
        allowed_reg = set(schema["reference_values"]["uacs_reg_id_allowed"])
        bad_reg = sorted(set(summary["reg_id"]) - allowed_reg)
        rep.add(
            ValidationResult(
                "gaa.region_codes", SEVERITY_SHOULD, not bad_reg,
                detail="unexpected region codes: %s (note '00'/'nan'/'15'/'18' are expected domain values)"
                % (bad_reg or "none"),
                actual=sorted(set(summary["reg_id"])), expected=sorted(allowed_reg),
            )
        )

        # documented anomaly: negative amounts -------------------------------
        known_neg = schema["reference_values"]["known_anomalies"]["negative_amt_count"]
        rep.add(
            ValidationResult(
                "gaa.negative_amounts", SEVERITY_SHOULD, summary["neg"] == known_neg,
                detail="%d rows with amt<0 (documented anomaly set is %d); appropriations should not be negative"
                % (summary["neg"], known_neg), actual=summary["neg"], expected=known_neg,
            )
        )

        # null layout --------------------------------------------------------
        nullable = {c["name"] for c in schema["columns"] if c["nullable"]}
        non_nullable = {c["name"] for c in schema["columns"] if not c["nullable"]}
        null_counts = {
            "prexc_level": summary["nul_prexc"], "sorder": summary["nul_sorder"],
            "uacs_operdiv_id": summary["nul_operdiv"], "uacs_div_dsc": summary["nul_div"],
            "uacs_oper_dsc": summary["nul_oper"],
        }
        bad_nonnul = [c for c, n in null_counts.items() if c in non_nullable and n]
        bad_nul = [c for c, n in null_counts.items() if c in nullable and not n]
        layout_ok = not bad_nonnul and not bad_nul
        rep.add(
            ValidationResult(
                "gaa.null_layout", SEVERITY_SHOULD, layout_ok,
                detail="unexpected nulls: %s; nullable-but-empty: %s"
                % (bad_nonnul or "none", bad_nul or "none"),
                actual=null_counts, expected={"nullable-only columns have nulls"},
            )
        )

        # source README metadata drift ----------------------------------------
        readme_text = readme_path.read_text(encoding="utf-8", errors="replace") if readme_path.exists() else ""
        stale_claimed = ("3,776,789" in readme_text or "3.7+ million" in readme_text
                         or "3.7 million" in readme_text)
        rep.add(
            ValidationResult(
                "gaa.readme_metadata_consistency", SEVERITY_SHOULD, not stale_claimed,
                detail=("in-repo README claims 3,776,789 records/FY2020-2025 but data has %d records"
                        "/FY2020-2026 (README appears to be stale upstream metadata)"
                        % summary["row_count"]) if stale_claimed else "README metadata consistent with data",
                actual=summary["row_count"], expected="no stale published count in README",
            )
        )

        return rep