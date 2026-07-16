"""
Demo data seeder – realistic Saudi retail for $0-cost trial.
Creates a full working demo: 15 Saudi items, 30 days of transactions,
inventory snapshot, agent actions, and pre-computed Money Audit signals.
"""
import os
import uuid
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

R_RIYADH = timezone(timedelta(hours=3))


async def seed_demo_data(session: AsyncSession):
    """Seed a complete demo business with realistic Saudi retail data."""
    allow_demo = os.getenv("ALLOW_DEMO_SEED", "false").lower() == "true"
    env = os.getenv("ENVIRONMENT", "development")

    if not (allow_demo and env == "development"):
        return None

    from app.utils.security import hash_password

    # ── User ──────────────────────────────────────────────────────
    user_id = str(uuid.uuid4())
    await session.execute(
        text("""
            INSERT INTO users (id, email, password_hash, full_name, role, is_active, created_at)
            VALUES (:id, :email, :pw, :name, 'owner', true, NOW())
            ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash
            RETURNING id
        """),
        {"id": user_id, "email": "admin@nazmos.sa", "pw": hash_password("Demo2026!"),
         "name": "Demo Merchant"},
    )

    # ── Business ──────────────────────────────────────────────────
    biz_id = str(uuid.uuid4())
    await session.execute(
        text("""
            INSERT INTO businesses (id, name, business_type, currency, timezone,
                                    owner_id, is_demo, created_at)
            VALUES (:id, :name, 'retail', 'SAR', 'Asia/Riyadh',
                    :owner, true, NOW())
            ON CONFLICT DO NOTHING
        """),
        {"id": biz_id, "name": "Demo Supermarket – Riyadh", "owner": user_id},
    )

    # ── Categories ────────────────────────────────────────────────
    categories = {
        "dairy": "ألبان ومنتجات ألبان",
        "beverages": "مشروبات",
        "dates": "تمور وحلويات",
        "household": "مواد منزلية",
        "bakery": "مخبوزات",
        "snacks": "وجبات خفيفة",
    }
    cat_ids = {}
    for key, name in categories.items():
        cid = str(uuid.uuid4())
        await session.execute(
            text("""
                INSERT INTO categories (id, business_id, name, sort_order, is_active)
                VALUES (:id, :bid, :name, 0, true)
                ON CONFLICT (business_id, name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
            """),
            {"id": cid, "bid": biz_id, "name": name},
        )
        cat_ids[key] = cid

    # ── Items ─────────────────────────────────────────────────────
    items_data = [
        # (name, sku, category, cost, sell, brand, pack_size)
        ("Almarai Full Cream Milk 2L", "ALM-MILK-2L", "dairy", 5.25, 8.50, "Almarai", "2L"),
        ("Almarai Fresh Yoghurt 170g×6", "ALM-YOGH-170", "dairy", 6.80, 11.95, "Almarai", "6×170g"),
        ("Nada Cheddar Cheese 400g", "NAD-CHED-400", "dairy", 12.50, 19.95, "Nada", "400g"),
        ("Nova Pure Water 600ml×12", "NOV-WAT-600", "beverages", 4.80, 9.00, "Nova", "12×600ml"),
        ("Rani Orange Juice 330ml×12", "RAN-JUICE-330", "beverages", 9.50, 15.95, "Rani", "12×330ml"),
        ("Almarai Apple Juice 1L", "ALM-JUICE-1L", "beverages", 3.90, 6.50, "Almarai", "1L"),
        ("Saudia Long Grain Rice 5kg", "SAU-RICE-5KG", "dates", 18.00, 28.95, "Saudia", "5kg"),
        ("Al-Wadi Pitted Dates 900g", "ALW-DATE-900", "dates", 15.00, 26.00, "Al-Wadi", "900g"),
        ("Halwani Turkey Luncheon 340g", "HAL-LUNC-340", "snacks", 5.50, 9.50, "Halwani", "340g"),
        ("Lusine White Bread 600g", "LUS-BREAD-600", "bakery", 1.80, 3.50, "Lusine", "600g"),
        ("Saudia Butter 200g", "SAU-BUTTER-200", "dairy", 5.25, 8.95, "Saudia", "200g"),
        ("Fine White Sugar 5kg", "FIN-SUGAR-5KG", "household", 12.00, 18.50, "Fine", "5kg"),
        ("Afia Sunflower Oil 1.5L", "AFI-OIL-1.5L", "household", 13.50, 21.95, "Afia", "1.5L"),
        ("Persil Detergent 3kg", "PER-DETER-3KG", "household", 22.00, 34.95, "Persil", "3kg"),
        ("Lu Hyper Cheese Crackers 34g×6", "LU-CRAKE-34", "snacks", 6.00, 10.50, "LU", "6×34g"),
    ]

    item_ids = []
    for name, sku, cat_key, cost, sell, brand, pack in items_data:
        item_id = str(uuid.uuid4())
        item_ids.append(item_id)
        await session.execute(
            text("""
                INSERT INTO items
                    (id, business_id, name, sku, category_id, unit, cost_price, sell_price,
                     barcode, brand, pack_size, shariah_status, shariah_flags, shariah_checked_at)
                VALUES
                    (:id, :bid, :name, :sku, :cat, 'piece', :cost, :sell,
                     :barcode, :brand, :pack, 'halal_guard_passed', '[]'::json, NOW())
                ON CONFLICT (business_id, LOWER(name)) DO UPDATE SET sku = EXCLUDED.sku
            """),
            {"id": item_id, "bid": biz_id, "name": name, "sku": sku,
             "cat": cat_ids[cat_key], "cost": cost, "sell": sell,
             "barcode": f"5{str(hash(sku))[-11:]}",
             "brand": brand, "pack": pack},
        )

    # ── Inventory snapshot ────────────────────────────────────────
    import random
    random.seed(42)
    for item_id in item_ids:
        stock = random.randint(5, 120)
        reorder = random.randint(10, 30)
        max_s = reorder * 5
        await session.execute(
            text("""
                INSERT INTO inventory (business_id, item_id, current_stock, reorder_level, max_stock, last_restocked, updated_at)
                VALUES (:bid, :iid, :stock, :reorder, :max_s, NOW(), NOW())
                ON CONFLICT (business_id, item_id) DO UPDATE SET
                    current_stock = EXCLUDED.current_stock,
                    reorder_level = EXCLUDED.reorder_level
            """),
            {"bid": biz_id, "iid": item_id, "stock": stock, "reorder": reorder, "max_s": max_s},
        )

    # ── 30 days of transactions ───────────────────────────────────
    now = datetime.now(R_RIYADH)
    ksa_weekly = {0: 0.88, 1: 0.85, 2: 0.90, 3: 1.15, 4: 1.42, 5: 1.35, 6: 0.95}
    tx_rows = []
    for day_offset in range(30, 0, -1):
        dt = now - timedelta(days=day_offset)
        dow = dt.weekday()
        multiplier = ksa_weekly.get(dow, 1.0)
        n_items_today = random.randint(4, 10)
        sampled = random.sample(range(len(item_ids)), min(n_items_today, len(item_ids)))
        for idx in sampled:
            qty = max(1, int(random.gauss(3 * multiplier, 1.5)))
            cost = float(items_data[idx][3])
            sell = float(items_data[idx][4])
            total = round(qty * sell, 2)
            profit = round(qty * (sell - cost), 2)
            tx_rows.append({
                "id": str(uuid.uuid4()),
                "bid": biz_id,
                "iid": item_ids[idx],
                "qty": qty,
                "unit_price": sell,
                "cost_price": cost,
                "total": total,
                "profit": profit,
                "ts": dt.isoformat(),
            })

    for tx in tx_rows:
        await session.execute(
            text("""
                INSERT INTO transactions
                    (id, business_id, item_id, quantity, unit_price, cost_price,
                     total_amount, profit, transaction_type, transaction_at)
                VALUES
                    (:id, :bid, :iid, :qty, :unit_price, :cost_price,
                     :total, :profit, 'sale', :ts)
            """),
            tx,
        )

    # ── Daily summaries ───────────────────────────────────────────
    await session.execute(
        text("""
            INSERT INTO daily_summaries (business_id, date, total_sales, total_profit, total_transactions)
            SELECT
                t.business_id,
                DATE(t.transaction_at) as date,
                COALESCE(SUM(t.total_amount), 0) as total_sales,
                COALESCE(SUM(t.profit), 0) as total_profit,
                COUNT(*) as total_transactions
            FROM transactions t
            WHERE t.business_id = :bid
            GROUP BY t.business_id, DATE(t.transaction_at)
            ON CONFLICT (business_id, date) DO UPDATE SET
                total_sales = EXCLUDED.total_sales,
                total_profit = EXCLUDED.total_profit
        """),
        {"bid": biz_id},
    )

    # ── Agent actions (pending) ───────────────────────────────────
    action_templates = [
        {"type": "RESTOCK", "item_idx": 0, "title": "Almarai Milk – restock 48 units",
         "summary": "Current stock 12 units, avg daily sale 4.2 units. Stockout in 3 days at current rate.",
         "priority": 1, "value": 252.00},
        {"type": "DISCOUNT", "item_idx": 7, "title": "Al-Wadi Dates – apply 15% Recovery Match",
         "summary": "42 units in stock, no sales in 18 days. Estimated SAR 26.00/unit trapped cash.",
         "priority": 2, "value": 1092.00},
        {"type": "PRICE_ADJUST", "item_idx": 13, "title": "Persil Detergent – price review",
         "summary": "Competitor price SAR 29.95 vs your SAR 34.95. Reduce to SAR 32.95 to recover volume.",
         "priority": 3, "value": 480.00},
    ]
    for act in action_templates:
        await session.execute(
            text("""
                INSERT INTO agent_actions
                    (id, business_id, action_type, item_id, title, summary,
                     priority, estimated_value_sar, status, payload, created_at)
                VALUES
                    (:id, :bid, :type, :iid, :title, :summary,
                     :priority, :value, 'pending', '{}'::json, NOW())
            """),
            {"id": str(uuid.uuid4()), "bid": biz_id, "type": act["type"],
             "iid": item_ids[act["item_idx"]],
             "title": act["title"], "summary": act["summary"],
             "priority": act["priority"], "value": act["value"]},
        )

    await session.commit()

    return {
        "user_id": user_id,
        "business_id": biz_id,
        "email": "admin@nazmos.sa",
        "password": "Demo2026!",
        "items_created": len(item_ids),
        "transactions_created": len(tx_rows),
        "agent_actions": len(action_templates),
    }
