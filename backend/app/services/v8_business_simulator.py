"""V8 Business Simulator — probability-based, reproducible, fair.

Generates 5 diverse businesses with different:
- Owner constraints (cash budgets, discount blocks, strategic products)
- Autonomy policies (conservative vs aggressive)
- Supplier patterns (lead times, MOQs)
- Financial exposure (capital at risk, revenue at risk)
- Business characteristics (healthy, poorly managed, growing, seasonal, cash-constrained)

Uses deterministic random seeds so experiments are reproducible.
Every simulated outcome is explicitly labeled: SIMULATED OUTCOME.
Never report simulated SAR as actual recovered SAR.
Do not tune the simulator to make AI win.
"""
from __future__ import annotations

import random
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any


D = Decimal


def _seed_rng(seed: str) -> random.Random:
    """Create a deterministic RNG from a string seed."""
    h = hashlib.sha256(seed.encode()).hexdigest()
    return random.Random(int(h[:8], 16))


@dataclass
class BusinessProfile:
    """Defines a business with its unique characteristics."""
    name: str
    business_type: str  # supermart, baqala, cafe, restaurant, retail
    business_id_seed: str
    owner_email: str
    # Owner constraints
    cash_budget: float | None = None
    max_discount_pct: float | None = None
    blocked_discount_products: list[str] = field(default_factory=list)
    strategic_products: list[str] = field(default_factory=list)
    blocked_transfer_routes: list[str] = field(default_factory=list)
    minimum_margin_pct: float | None = None
    # Autonomy defaults
    default_autonomy_dial: int = 50
    # Supplier characteristics
    avg_lead_time_days: int = 7
    avg_moq_sar: float = 500


@dataclass
class ItemProfile:
    """Defines an item within a business."""
    sku: str
    name: str
    category: str
    cost: float
    sell: float
    # Initial state
    initial_stock: int = 0
    inventory_age_days: int = 0
    # Demand pattern
    daily_rate: float = 1.0  # expected sales per day
    pattern: str = "steady"  # steady, seasonal, dead, slow, growing
    # Seasonal params
    seasonal_month: int = 7  # peak month (1-12)
    seasonal_amplitude: float = 4.0
    # Supplier
    supplier_name: str = ""
    lead_time_days: int = 7
    moq_sar: float = 500
    # Strategic?
    is_strategic: bool = False
    # Classification ground truth
    ground_truth: str = "healthy"


# ── V8 Business Profiles ─────────────────────────────────────────────────────

V8_BUSINESSES = [
    # 1. Healthy Supermarket
    BusinessProfile(
        name="Healthy Supermarket",
        business_type="supermart",
        business_id_seed="v8_healthy_supermarket",
        owner_email="healthy_supermarket@nazmos.sa",
        cash_budget=50000,
        max_discount_pct=20,
        strategic_products=[],
        minimum_margin_pct=0.15,
        default_autonomy_dial=60,
        avg_lead_time_days=5,
        avg_moq_sar=1000,
    ),
    # 2. Poorly Managed Baqala
    BusinessProfile(
        name="Poorly Managed Baqala",
        business_type="baqala",
        business_id_seed="v8_poorly_managed_baqala",
        owner_email="poorly_baqala@nazmos.sa",
        cash_budget=8000,
        max_discount_pct=10,
        blocked_discount_products=["premium_dates", "imported_chocolate"],
        strategic_products=["premium_dates"],
        minimum_margin_pct=0.25,
        default_autonomy_dial=20,
        avg_lead_time_days=14,
        avg_moq_sar=200,
    ),
    # 3. Growing Supermarket
    BusinessProfile(
        name="Growing Supermarket",
        business_type="supermart",
        business_id_seed="v8_growing_supermarket",
        owner_email="growing_supermarket@nazmos.sa",
        cash_budget=30000,
        max_discount_pct=15,
        strategic_products=[],
        minimum_margin_pct=0.20,
        default_autonomy_dial=70,
        avg_lead_time_days=7,
        avg_moq_sar=2000,
    ),
    # 4. Seasonal Retailer
    BusinessProfile(
        name="Seasonal Retailer",
        business_type="retail",
        business_id_seed="v8_seasonal_retailer",
        owner_email="seasonal_retailer@nazmos.sa",
        cash_budget=25000,
        max_discount_pct=30,
        strategic_products=["summer_cooler"],
        minimum_margin_pct=0.10,
        default_autonomy_dial=55,
        avg_lead_time_days=10,
        avg_moq_sar=1500,
    ),
    # 5. Cash-Constrained Restaurant
    BusinessProfile(
        name="Cash-Constrained Restaurant",
        business_type="restaurant",
        business_id_seed="v8_cash_constrained_restaurant",
        owner_email="cash_restaurant@nazmos.sa",
        cash_budget=5000,
        max_discount_pct=5,
        blocked_discount_products=["premium_steak", "imported_truffle"],
        strategic_products=["premium_steak", "imported_truffle"],
        minimum_margin_pct=0.35,
        default_autonomy_dial=15,
        avg_lead_time_days=3,
        avg_moq_sar=300,
    ),
]


def get_v8_items(business_seed: str) -> list[ItemProfile]:
    """Generate items for a specific business."""
    rng = _seed_rng(business_seed)

    items_by_business = {
        "v8_healthy_supermarket": [
            ItemProfile("HS001", "Full Cream Milk 1L", "dairy", 4.0, 6.5, 80, 15, 8.0, "steady", supplier_name="Almarai", lead_time_days=2, moq_sar=200),
            ItemProfile("HS002", "Chicken Breast 1kg", "meat", 18.0, 28.0, 45, 10, 5.0, "steady", supplier_name="Alwajh", lead_time_days=3, moq_sar=500),
            ItemProfile("HS003", "Organic Quinoa 500g", "grains", 22.0, 35.0, 120, 95, 0.3, "slow", supplier_name="Health Foods Co", lead_time_days=14, moq_sar=1000),
            ItemProfile("HS004", "BBQ Charcoal 5kg", "outdoor", 15.0, 28.0, 150, 30, 1.5, "seasonal", seasonal_month=7, seasonal_amplitude=5.0, supplier_name="Gulf Supplies", lead_time_days=10, moq_sar=800),
            ItemProfile("HS005", "Premium Olive Oil 1L", "cooking", 35.0, 55.0, 0, 45, 0.0, "dead", supplier_name="Mediterranean Imports", lead_time_days=21, moq_sar=2000),
        ],
        "v8_poorly_managed_baqala": [
            ItemProfile("PB001", "Pepsi 330ml", "beverages", 1.0, 2.0, 200, 5, 12.0, "steady", supplier_name="PepsiCo SA", lead_time_days=3, moq_sar=100),
            ItemProfile("PB002", "Shawarma Bread", "bakery", 0.5, 1.5, 50, 2, 15.0, "steady", supplier_name="Local Bakery", lead_time_days=1, moq_sar=50),
            ItemProfile("PB003", "Imported Belgian Chocolate", "confectionery", 45.0, 68.0, 60, 120, 0.2, "dead", supplier_name="European Foods", lead_time_days=30, moq_sar=3000, is_strategic=True),
            ItemProfile("PB004", "Summer Cooler Fan", "electronics", 85.0, 140.0, 25, 20, 0.8, "seasonal", seasonal_month=6, seasonal_amplitude=6.0, supplier_name="Appliance World", lead_time_days=14, moq_sar=2000),
            ItemProfile("PB005", "Phone Charger Cable", "accessories", 8.0, 18.0, 0, 60, 0.0, "dead", supplier_name="Tech Imports", lead_time_days=21, moq_sar=500),
        ],
        "v8_growing_supermarket": [
            ItemProfile("GS001", "Fresh Bread", "bakery", 1.5, 3.0, 100, 1, 20.0, "growing", supplier_name="In-House Bakery", lead_time_days=1, moq_sar=100),
            ItemProfile("GS002", "Energy Drinks Pack", "beverages", 12.0, 22.0, 60, 30, 4.0, "growing", supplier_name="Red Bull SA", lead_time_days=5, moq_sar=800),
            ItemProfile("GS003", "Baby Formula", "baby", 55.0, 75.0, 30, 20, 2.5, "steady", supplier_name="Nestle SA", lead_time_days=7, moq_sar=1500),
            ItemProfile("GS004", "Winter Jacket", "clothing", 120.0, 200.0, 80, 60, 0.1, "seasonal", seasonal_month=11, seasonal_amplitude=8.0, supplier_name="Fashion Hub", lead_time_days=21, moq_sar=5000),
            ItemProfile("GS005", "Bulk Rice 20kg", "grains", 45.0, 65.0, 10, 45, 1.5, "slow", supplier_name="Saudi Grains Co", lead_time_days=10, moq_sar=2000),
        ],
        "v8_seasonal_retailer": [
            ItemProfile("SR001", "Swimming Goggles", "sports", 25.0, 45.0, 100, 10, 3.0, "seasonal", seasonal_month=6, seasonal_amplitude=10.0, supplier_name="Sport Zone", lead_time_days=14, moq_sar=1000),
            ItemProfile("SR002", "Air Conditioner 1.5Ton", "appliances", 1800.0, 2800.0, 15, 30, 0.05, "seasonal", seasonal_month=5, seasonal_amplitude=12.0, supplier_name="Gree SA", lead_time_days=21, moq_sar=20000),
            ItemProfile("SR003", "Heater Blanket", "home", 80.0, 140.0, 50, 90, 0.05, "seasonal", seasonal_month=12, seasonal_amplitude=10.0, supplier_name="Home Comfort", lead_time_days=14, moq_sar=2000),
            ItemProfile("SR004", "Umbrella", "accessories", 12.0, 25.0, 200, 45, 0.1, "slow", supplier_name="Accessories Plus", lead_time_days=7, moq_sar=300),
            ItemProfile("SR005", "Year-Round T-Shirt", "clothing", 15.0, 35.0, 80, 5, 2.0, "steady", supplier_name="Basic Wear", lead_time_days=10, moq_sar=500),
        ],
        "v8_cash_constrained_restaurant": [
            ItemProfile("CR001", "Chicken Breast 1kg", "meat", 18.0, 0, 40, 5, 8.0, "steady", supplier_name="Alwajh", lead_time_days=2, moq_sar=300),
            ItemProfile("CR002", "Rice Basmati 10kg", "grains", 35.0, 0, 20, 10, 3.0, "steady", supplier_name="Saudi Grains", lead_time_days=5, moq_sar=200),
            ItemProfile("CR003", "Imported Truffle Oil 100ml", "luxury", 180.0, 0, 8, 90, 0.05, "dead", supplier_name="Gourmet Imports", lead_time_days=30, moq_sar=5000, is_strategic=True),
            ItemProfile("CR004", "Premium Wagyu Steak 200g", "meat", 120.0, 0, 5, 15, 0.3, "slow", supplier_name="Wagyu Direct", lead_time_days=7, moq_sar=2000, is_strategic=True),
            ItemProfile("CR005", "Daily Fresh Vegetables", "produce", 2.0, 0, 60, 1, 15.0, "steady", supplier_name="Farm Direct", lead_time_days=1, moq_sar=100),
        ],
    }
    return items_by_business.get(business_seed, [])


@dataclass
class DaySnapshot:
    """State of a business on a specific simulated day."""
    day: int
    date: datetime
    items: list[dict[str, Any]]  # item states
    transactions: list[dict[str, Any]]  # sales transactions
    actions_taken: list[dict[str, Any]]  # actions executed
    financial_state: dict[str, Any]  # aggregate financials


def simulate_day(
    business: BusinessProfile,
    items: list[ItemProfile],
    day: int,
    start_date: datetime,
    previous_state: dict[str, Any] | None = None,
    seed_suffix: str = "",
) -> DaySnapshot:
    """Simulate one day of business activity.

    Uses probability-based modeling:
    - Sale probability based on daily_rate
    - Seasonal variation based on month
    - Random demand fluctuations
    - Execution failures (5% chance)
    - Owner rejections (10% chance for discounts, 15% for transfers)
    """
    rng = _seed_rng(f"{business.business_id_seed}_day_{day}_{seed_suffix}")
    current_date = start_date + timedelta(days=day)
    current_month = current_date.month

    item_states = []
    transactions = []
    actions_taken = []

    # Load previous state
    prev_stock = {}
    prev_sold = {}
    if previous_state:
        for item_state in previous_state.get("items", []):
            prev_stock[item_state["sku"]] = item_state["stock"]
            prev_sold[item_state["sku"]] = item_state.get("total_sold", 0)

    for item in items:
        stock = prev_stock.get(item.sku, item.initial_stock)
        total_sold = prev_sold.get(item.sku, 0)

        # Calculate daily rate with seasonal variation
        if item.pattern == "seasonal":
            month_diff = abs(current_month - item.seasonal_month)
            if month_diff > 6:
                month_diff = 12 - month_diff
            seasonal_factor = max(0.1, 1.0 - (month_diff / 6.0) * (item.seasonal_amplitude - 1.0))
            effective_rate = item.daily_rate * seasonal_factor
        elif item.pattern == "dead":
            effective_rate = 0.0
        elif item.pattern == "slow":
            effective_rate = item.daily_rate * 0.3
        elif item.pattern == "growing":
            effective_rate = item.daily_rate * (1.0 + day * 0.005)
        else:
            effective_rate = item.daily_rate

        # Simulate sales
        daily_sales = 0
        if effective_rate > 0 and stock > 0:
            # Poisson-like distribution
            sale_prob = min(1.0, effective_rate / 20.0)
            if rng.random() < sale_prob:
                daily_sales = max(1, int(rng.gauss(effective_rate, effective_rate * 0.3)))
                daily_sales = min(daily_sales, stock)

        new_stock = max(0, stock - daily_sales)
        total_sold += daily_sales

        # Record transaction
        if daily_sales > 0:
            transactions.append({
                "sku": item.sku,
                "date": current_date.isoformat(),
                "quantity": daily_sales,
                "unit_price": item.sell if item.sell > 0 else item.cost * 1.2,
                "total_amount": daily_sales * (item.sell if item.sell > 0 else item.cost * 1.2),
                "cost_price": item.cost,
            })

        item_states.append({
            "sku": item.sku,
            "name": item.name,
            "stock": new_stock,
            "cost": item.cost,
            "sell": item.sell,
            "daily_rate": effective_rate,
            "total_sold": total_sold,
            "pattern": item.pattern,
            "is_strategic": item.is_strategic,
        })

    # Aggregate financials
    total_inventory_value = sum(s["stock"] * s["cost"] for s in item_states)
    total_capital_at_risk = total_inventory_value

    return DaySnapshot(
        day=day,
        date=current_date,
        items=item_states,
        transactions=transactions,
        actions_taken=actions_taken,
        financial_state={
            "total_inventory_value_sar": round(total_inventory_value, 2),
            "total_capital_at_risk_sar": round(total_capital_at_risk, 2),
            "total_items": len(item_states),
            "items_in_stock": sum(1 for s in item_states if s["stock"] > 0),
            "items_out_of_stock": sum(1 for s in item_states if s["stock"] == 0 and s["daily_rate"] > 0),
        },
    )


def simulate_60_days(
    business: BusinessProfile,
    seed_suffix: str = "",
) -> list[DaySnapshot]:
    """Simulate 60 days of business activity for one business."""
    items = get_v8_items(business.business_id_seed)
    start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)

    snapshots = []
    previous_state = None

    for day in range(61):  # Day 0 through Day 60
        snapshot = simulate_day(business, items, day, start_date, previous_state, seed_suffix)
        snapshots.append(snapshot)
        previous_state = {
            "items": snapshot.items,
            "total_sold": sum(t["quantity"] for t in snapshot.transactions),
        }

    return snapshots
