"""Privacy-safe telemetry for the free guest audit.

Only whitelisted, shape-level metadata is ever logged. Product names, customer
names, row values, credentials and tokens are never accepted or written.
"""
from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger("nazmos.guest_audit")

# Every key that may ever be logged. Anything else is dropped.
ALLOWED_KEYS = frozenset(
    {
        "event",
        "status",
        "file_type",
        "sheet_count",
        "selected_sheet",
        "header_row_index",
        "encoding",
        "delimiter",
        "row_count",
        "detected_columns",
        "column_confidence",
        "is_arabic_headers",
        "is_arabic_data",
        "file_classification",
        "pairing_attempted",
        "paired_products",
        "pairing_success_rate",
        "pairing_truncated",
        "unmatched_sales",
        "unmatched_inventory",
        "products_with_risk",
        "parse_failure_reason",
        "error_type",
        "processing_time_ms",
        "source",
    }
)


def record_guest_audit(event: str, **metadata: Any) -> None:
    """Log only the whitelisted metadata for one guest audit request."""
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in ALLOWED_KEYS:
            safe[key] = value
    if "processing_time_ms" in safe:
        safe["processing_time_ms"] = round(float(safe["processing_time_ms"]), 1)
    log.info(event, **safe)