"""Salla transport adapter.

Provider parsing stays isolated to transport translation. It never writes
items, inventory, or transactions directly; Orbit owns those facts.
"""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orbit.ingestion.service import ingest_pos_records, provider_order_rows


async def handle_salla_order_created(
    payload: Dict[str, Any], business_id: UUID, db: AsyncSession
) -> Dict[str, Any]:
    reference, rows = provider_order_rows("salla", payload)
    canonical, projection = await ingest_pos_records(
        db,
        rows,
        business_id=business_id,
        source_name="salla-order-" + (reference or "unknown") + ".json",
        provider="salla",
        external_reference=reference or None,
    )
    return {
        "status": "PROCESSED",
        "salla_order_id": reference,
        "items_received": len(rows),
        "transactions_recorded": projection.transactions_inserted,
        "inventory_deducted": 0,
        "unresolved_items": list(canonical.warnings)[:10],
        "canonical_state_version": canonical.state_version_after,
        "conflicts": len(canonical.conflicts),
        "note": "Salla payload normalized through the canonical Orbit ingestion pipeline.",
    }
