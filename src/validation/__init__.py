"""Public exports for the validation layer.

The package exposes the names other modules import: the report/result types,
the severity constants, the four validator classes, and the orchestrator
entry point ``run_validation()``.
"""

from src.validation.base import (
    SEVERITY_MUST,
    SEVERITY_SHOULD,
    ValidationReport,
    ValidationResult,
)
from src.validation.global_checks import GlobalValidator
from src.validation.orchestrator import run_validation
from src.validation.ph_gaa import GAAValidator
from src.validation.ph_saaodb import SAAODBValidator
from src.validation.ph_tax_collection import TaxCollectionValidator

__all__ = [
    "SEVERITY_MUST",
    "SEVERITY_SHOULD",
    "ValidationResult",
    "ValidationReport",
    "GlobalValidator",
    "GAAValidator",
    "TaxCollectionValidator",
    "SAAODBValidator",
    "run_validation",
]