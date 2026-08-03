"""Tests for Recovery Match nightly liquidity scanner."""
import uuid

import pytest
from sqlalchemy import text

from app.services.recovery_match_matcher import run_nightly_recovery_match_scan


@pytest.mark.asyncio
async def test_nightly_scan_creates_matches_and_logs(db_session):
    seller_bus = str(uuid.uuid4())
    buyer_bus = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    buyer_item_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())

    # Seller business and owner with phone
    await db_session.execute(
        text("""
            INSERT INTO users (id, email, password_hash, full_name, role, is_active, phone)
            VALUES (:id, :email, 'hash', 'Owner', 'owner', true, '+966501111111')
        """),
        {"id": owner_id, "email": f"seller_{uuid.uuid4().hex[:8]}@example.com"},
    )
    await db_session.execute(
        text("""
            INSERT INTO businesses (id, name, type, currency, city, latitude, longitude, owner_id)
            VALUES (:id, 'Seller', 'retail', 'SAR', 'Riyadh', 24.7136, 46.6753, :owner_id)
        """),
        {"id": seller_bus, "owner_id": owner_id},
    )

    # Buyer business and owner with phone
    buyer_owner_id = str(uuid.uuid4())
    await db_session.execute(
        text("""
            INSERT INTO users (id, email, password_hash, full_name, role, is_active, phone)
            VALUES (:id, :email, 'hash', 'Owner', 'owner', true, '+966502222222')
        """),
        {"id": buyer_owner_id, "email": f"buyer_{uuid.uuid4().hex[:8]}@example.com"},
    )
    await db_session.execute(
        text("""
            INSERT INTO businesses (id, name, type, currency, city, latitude, longitude, owner_id)
            VALUES (:id, 'Buyer', 'retail', 'SAR', 'Riyadh', 24.7200, 46.6800, :owner_id)
        """),
        {"id": buyer_bus, "owner_id": buyer_owner_id},
    )

    # Enable recovery match for both
    await db_session.execute(
        text("""
            INSERT INTO recovery_match_settings (id, business_id, is_enabled, allow_contact_reveal, max_distance_km)
            VALUES (gen_random_uuid(), :b, true, false, 10)
        """),
        {"b": seller_bus},
    )
    await db_session.execute(
        text("""
            INSERT INTO recovery_match_settings (id, business_id, is_enabled, allow_contact_reveal, max_distance_km)
            VALUES (gen_random_uuid(), :b, true, false, 10)
        """),
        {"b": buyer_bus},
    )

    # Seller item and inventory
    await db_session.execute(
        text("""
            INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active, barcode)
            VALUES (:id, :business_id, 'Matchable Item', 'SKU-001', 'piece', 10, 20, true, '123456')
        """),
        {"id": item_id, "business_id": seller_bus},
    )
    await db_session.execute(
        text("""
            INSERT INTO inventory (id, business_id, item_id, current_stock, reorder_level, max_stock)
            VALUES (gen_random_uuid(), :business_id, :item_id, 100, 10, 200)
        """),
        {"business_id": seller_bus, "item_id": item_id},
    )

    # Buyer item with same barcode and low stock
    await db_session.execute(
        text("""
            INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active, barcode)
            VALUES (:id, :business_id, 'Matchable Item', 'SKU-001', 'piece', 10, 20, true, '123456')
        """),
        {"id": buyer_item_id, "business_id": buyer_bus},
    )
    await db_session.execute(
        text("""
            INSERT INTO inventory (id, business_id, item_id, current_stock, reorder_level, max_stock)
            VALUES (gen_random_uuid(), :business_id, :item_id, 2, 10, 200)
        """),
        {"business_id": buyer_bus, "item_id": buyer_item_id},
    )

    # Buyer has recent sales to create demand
    for _ in range(30):
        await db_session.execute(
            text("""
                INSERT INTO transactions
                    (id, business_id, item_id, quantity, unit_price, cost_price, total_amount, profit, transaction_at, transaction_type)
                VALUES (gen_random_uuid(), :business_id, :item_id, 5, 20, 10, 100, 50, NOW() - INTERVAL '1 day', 'sale')
            """),
            {"business_id": buyer_bus, "item_id": buyer_item_id},
        )

    # Active listing from seller
    await db_session.execute(
        text("""
            INSERT INTO stock_recovery_listings
                (id, seller_business_id, item_id, sku, barcode, item_name, category,
                 quantity_available, unit_cost_sar, asking_price_sar, discount_pct,
                 expiry_date, storage_type, status, created_at, updated_at, expires_at)
            VALUES
                (gen_random_uuid(), :seller_bus, :item_id, 'SKU-001', '123456', 'Matchable Item', 'retail',
                 50, 10, 8, 20, '2026-12-31', 'ambient', 'seller_approved', NOW(), NOW(), NOW() + INTERVAL '7 days')
        """),
        {"seller_bus": seller_bus, "item_id": item_id},
    )
    await db_session.commit()

    summary = await run_nightly_recovery_match_scan(db_session)

    assert summary["listings_scanned"] >= 1
    assert summary["matches_created"] >= 1
    assert summary["notifications_sent"] >= 2

    matches = await db_session.execute(
        text("SELECT COUNT(*) FROM stock_recovery_matches WHERE buyer_business_id = :buyer_bus"),
        {"buyer_bus": buyer_bus},
    )
    assert matches.scalar() >= 1
