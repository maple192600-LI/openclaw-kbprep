"""Quality package public compatibility surface."""

from .runner import run_quality_check
from .retention import _detail_categories, _detail_retention_stats, _is_known_pollution_without_detail
from .thresholds import (
    CLEANING_THRESHOLDS,
    CONVERSION_THRESHOLDS,
    COVERAGE_THRESHOLDS,
    SPLITTING_THRESHOLDS,
)

__all__ = [
    "run_quality_check",
    "_detail_categories",
    "_detail_retention_stats",
    "_is_known_pollution_without_detail",
    "CLEANING_THRESHOLDS",
    "CONVERSION_THRESHOLDS",
    "COVERAGE_THRESHOLDS",
    "SPLITTING_THRESHOLDS",
]
