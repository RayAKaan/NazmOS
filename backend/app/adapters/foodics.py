"""Foodics transport adapter.

The adapter only translates the provider payload into canonical source records.
Business truth is produced by Orbit; product tables are populated by the canonical
projector, never directly here.
"""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orbit.ingestion.service import ingest_pos_records, provider_order_rows


async def handle_foodics_order_created(
    payload: Dict[str, Any], business_id: UUID, db: AsyncSession
) -> Dict[str, Any]:
    reference, rows = provider_order_rows("foodics", payload)
    canonical, projection = await ingest_pos_records(
        db,
        rows,
        business_id=business_id,
        source_name="foodics-order-" + (reference or "unknown") + ".json",
        provider="foodics",
        external_reference=reference or None,
    )
    return {
        "status": "PROCESSED",
        "pos_reference": reference,
        "items_received": len(rows),
        "transactions_recorded": projection.transactions_inserted,
        "inventory_deducted": 0,
        "unresolved_items": list(canonical.warnings)[:10],
        "canonical_state_version": canonical.state_version_after,
        "conflicts": len(canonical.conflicts),
        "note": "Foodics payload normalized through the canonical Orbit ingestion pipeline.",
    }
