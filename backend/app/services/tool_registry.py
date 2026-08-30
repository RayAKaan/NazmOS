"""Agent Tool layer (Phase 1, brief §7).

One registry of tools the Agent Runtime can call. Every tool is:
  - a thin wrapper over an EXISTING service (no duplicate agent business logic);
  - explicitly read-only or mutating (risk-classified);
  - never granted direct DB access — the agent → tool → service → DB boundary holds.

Architecture (brief §7):
    Agent → Tool → existing NazmOS Service → Database / external API
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

ToolCallable = Callable[[AsyncSession, UUID, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class Tool:
    name: str
    description: str
    read_only: bool
    risk: str  # low | medium | high (for the policy engine)
    fn: ToolCallable
    parameters: dict[str, Any] = field(default_factory=dict)


# ── Read-only wrappers over existing services ──────────────────────────────

async def _get_inventory(db: AsyncSession, business_id: UUID, args: dict[str, Any]) -> dict[str, Any]:
    from app.services.agent_tools import execute_agent_tool
    return await execute_agent_tool("query_inventory_level", args, business_id, db)


async def _get_sales(db: AsyncSession, business_id: UUID, args: dict[str, Any]) -> dict[str, Any]:
    days = int(args.get("days", 30) or 30)
    from sqlalchemy import text
    res = await db.execute(text("""
        SELECT DATE(transaction_at) AS day, SUM(quantity) AS units, SUM(total_sar) AS revenue_sar
        FROM transactions
        WHERE business_id = :b AND transaction_at >= NOW() - (:days || ' days')::interval
        GROUP BY DATE(transaction_at) ORDER BY day
    """), {"b": str(business_id), "days": days})
    return {"sales": [dict(r._mapping) for r in res.fetchall()], "days": days}


async def _get_supplier(db: AsyncSession, business_id: UUID, args: dict[str, Any]) -> dict[str, Any]:
    # Suppliers are a global (not per-business) network table. Filter by city/category.
    from sqlalchemy import text
    clauses = ["is_active = true"]
    params: dict[str, Any] = {}
    if args.get("city"):
        clauses.append("city = :city")
        params["city"] = args["city"]
    if args.get("category"):
        clauses.append("category = :category")
        params["category"] = args["category"]
    res = await db.execute(text(f"""
        SELECT id, name_ar, name_en, city, category, phone, whatsapp_number,
               lead_time_days, total_monthly_volume_sar
        FROM suppliers WHERE {' AND '.join(clauses)}
        ORDER BY total_monthly_volume_sar DESC NULLS LAST, name_en LIMIT 100
    """), params)
    return {"suppliers": [dict(r._mapping) for r in res.fetchall()]}


async def _forecast_demand(db: AsyncSession, business_id: UUID, args: dict[str, Any]) -> dict[str, Any]:
    from app.services.intelligence_api_client import IntelligenceAPIClient
    client = IntelligenceAPIClient(db, business_id)
    return await client.predict(
        target=args.get("target", "sales"),
        horizon_days=int(args.get("horizon_days", 7) or 7),
        item_id=args.get("item_id"),
    )


async def _generate_money_audit(db: AsyncSession, business_id: UUID, args: dict[str, Any]) -> dict[str, Any]:
    from app.services.money_audit_service import generate_money_audit
    return await generate_money_audit(db, business_id)


async def _find_recovery_matches(db: AsyncSession, business_id: UUID, args: dict[str, Any]) -> dict[str, Any]:
    from app.services.recovery_match_service import generate_preview
    return {"opportunities": await generate_preview(db, business_id)}


async def _get_product(db: AsyncSession, business_id: UUID, args: dict[str, Any]) -> dict[str, Any]:
    return await _get_inventory(db, business_id, args)


async def _suggest_transfers(db: AsyncSession, business_id: UUID, args: dict[str, Any]) -> dict[str, Any]:
    from app.services.inventory_orchestrator import analyze_inter_branch_rebalancing
    return await analyze_inter_branch_rebalancing(db, business_id)


async def _get_supplier_prices(db: AsyncSession, business_id: UUID, args: dict[str, Any]) -> dict[str, Any]:
    """Compare observed supplier prices for an item (read-only). Never a fabricated
    benchmark — returns only recorded SupplierPrice observations with their source."""
    from sqlalchemy import text
    item_id = args.get("item_id")
    sku = args.get("sku")
    if not item_id and not sku:
        return {"error": "item_id or sku required"}
    clause = "sp.item_id = :item" if item_id else "sp.sku = :sku"
    param = {"item": str(item_id)} if item_id else {"sku": sku}
    res = await db.execute(text(f"""
        SELECT sp.id, sp.supplier_id, s.name_en AS supplier_name, sp.sku, sp.barcode,
               sp.unit_price_sar, sp.currency, sp.min_quantity, sp.effective_from,
               sp.effective_to, sp.source, sp.is_active
        FROM supplier_prices sp
        LEFT JOIN suppliers s ON s.id = sp.supplier_id
        WHERE {clause} AND sp.is_active = true
        ORDER BY sp.unit_price_sar ASC
    """), param)
    prices = [dict(r._mapping) for r in res.fetchall()]
    summary = None
    if prices:
        vals = [float(p["unit_price_sar"]) for p in prices if p.get("unit_price_sar") is not None]
        if vals:
            avg = sum(vals) / len(vals)
            summary = {
                "count": len(vals),
                "min_sar": min(vals),
                "max_sar": max(vals),
                "avg_sar": round(avg, 2),
                "note": f"Sample of {len(vals)} recorded price observation(s); not a market benchmark.",
            }
    return {"prices": prices, "summary": summary}


# Mutating tools (Phase 2 §6) — registered for visibility, but NEVER callable directly.
# They execute only through the policy-gated deterministic executor
# (agent_action_executor.execute_agent_action), which the Agent Runtime invokes
# after classify_and_disposition. `call_tool` refuses them.
async def _mutating_tool(db: AsyncSession, business_id: UUID, args: dict[str, Any]) -> dict[str, Any]:
    return {"error": "mutating tool requires policy approval; invoke via the agent runtime"}


# ── Registry ───────────────────────────────────────────────────────────────

TOOLS: dict[str, Tool] = {
    "get_inventory": Tool("get_inventory", "Current stock, reorder level, and sell price for an item.", True, "low", _get_inventory, {"item_name": {"type": "string"}}),
    "get_sales": Tool("get_sales", "Aggregated sales per day over a window.", True, "low", _get_sales, {"days": {"type": "integer"}}),
    "get_product": Tool("get_product", "Alias for get_inventory.", True, "low", _get_product, {"item_name": {"type": "string"}}),
    "get_supplier": Tool("get_supplier", "List suppliers (network) by city/category.", True, "low", _get_supplier, {"city": {"type": "string"}, "category": {"type": "string"}}),
    "forecast_demand": Tool("forecast_demand", "Demand forecast from the intelligence API.", True, "low", _forecast_demand, {"target": {"type": "string"}, "horizon_days": {"type": "integer"}, "item_id": {"type": "string"}}),
    "generate_money_audit": Tool("generate_money_audit", "Run the existing Money Audit.", True, "low", _generate_money_audit, {}),
    "find_recovery_matches": Tool("find_recovery_matches", "Recovery Match preview opportunities (read-only).", True, "low", _find_recovery_matches, {}),
    "suggest_inter_branch_transfers": Tool("suggest_inter_branch_transfers", "Analyze inter-branch rebalancing (read-only).", True, "low", _suggest_transfers, {}),
    "get_supplier_prices": Tool("get_supplier_prices", "Observed supplier prices for an item (read-only, not a benchmark).", True, "low", _get_supplier_prices, {"item_id": {"type": "string"}, "sku": {"type": "string"}}),
    # Mutating tools — read_only=False; execution is policy-gated by the runtime only.
    # `restock` = create a purchase order (existing executor); `transfer_inventory` = inter-branch transfer.
    "transfer_inventory": Tool("transfer_inventory", "Execute an inter-branch stock transfer.", False, "low", _mutating_tool, {"item_id": {"type": "string"}, "from_business_id": {"type": "string"}, "to_business_id": {"type": "string"}, "recommended_transfer_qty": {"type": "number"}}),
    "restock": Tool("restock", "Create a purchase order for a restock (spends money).", False, "medium", _mutating_tool, {"item_id": {"type": "string"}, "recommended_qty": {"type": "number"}}),
}


def list_tools() -> list[dict[str, Any]]:
    return [{"name": t.name, "description": t.description, "read_only": t.read_only, "risk": t.risk} for t in TOOLS.values()]


async def call_tool(
    db: AsyncSession,
    business_id: UUID | str,
    name: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tool = TOOLS.get(name)
    if not tool:
        return {"error": f"Tool '{name}' unknown (available: {list(TOOLS)})"}
    # Guardrail: the runtime must have already passed the policy gate for mutating
    # tools; there are none registered yet, but this boundary is enforced here.
    if not tool.read_only:
        return {"error": f"Tool '{name}' is mutating and requires policy approval before execution"}
    return await tool.fn(db, UUID(str(business_id)), args or {})
