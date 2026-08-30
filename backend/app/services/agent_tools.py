"""
NazmOS Agent Tools for Retail Recovery.
Read-only tools expose inventory, dead-stock, transfer, and margin-recovery context.
Compliance/tax/payroll/finance tools are intentionally not part of the core product surface.
"""
import logging
from typing import Dict, Any
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("agent_tools")

AGENT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_inventory_level",
            "description": "Get current stock quantity, reorder level, and sell price for a retail item by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "Name or partial name of the item, e.g. Milk or Coffee"}
                },
                "required": ["item_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dead_stock_summary",
            "description": "Find stock with poor recent sales and estimate stuck capital.",
            "parameters": {
                "type": "object",
                "properties": {"days_no_sale": {"type": "integer", "description": "Minimum days without sale, default 30"}},
                "required": ["days_no_sale"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_inter_branch_transfers",
            "description": "Find overstocked and understocked branches and recommend internal stock transfers.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_profit_compression",
            "description": "Scan items where supplier costs or low margin suggest a price shield opportunity.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


async def execute_agent_tool(tool_name: str, tool_args: Dict[str, Any], business_id: UUID, db: AsyncSession) -> Dict[str, Any]:
    logger.info(f"Executing agent tool '{tool_name}' with args {tool_args} for business {business_id}")

    if tool_name == "suggest_inter_branch_transfers":
        from app.services.inventory_orchestrator import analyze_inter_branch_rebalancing
        return await analyze_inter_branch_rebalancing(db, business_id)

    if tool_name == "scan_profit_compression":
        from app.services.profit_optimizer import scan_profit_margin_compression
        return await scan_profit_margin_compression(db, business_id)

    if tool_name == "query_inventory_level":
        item_name = tool_args.get("item_name", "")
        res = await db.execute(text("""
            SELECT i.name, c.name AS category, i.unit, inv.current_stock, inv.reorder_level, i.sell_price
            FROM items i
            JOIN inventory inv ON i.id = inv.item_id
            LEFT JOIN categories c ON c.id = i.category_id
            WHERE i.business_id = :b AND i.name ILIKE :name
            LIMIT 5
        """), {"b": str(business_id), "name": f"%{item_name}%"})
        rows = [dict(r._mapping) for r in res.fetchall()]
        return {"items": rows, "count": len(rows)}

    if tool_name == "get_dead_stock_summary":
        # Dialect-safe (Phase 12): Python cutoff instead of NOW() - interval, so SQLite
        # development/integration and Postgres both work.
        from datetime import datetime, timedelta, timezone
        days = int(tool_args.get("days_no_sale", 30) or 30)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        res = await db.execute(text("""
            WITH recent_sales AS (
                SELECT item_id, MAX(transaction_at) AS last_sold_at, COALESCE(SUM(quantity), 0) AS qty_30d
                FROM transactions
                WHERE business_id = :b AND transaction_at >= :cutoff
                GROUP BY item_id
            )
            SELECT i.name, inv.current_stock, i.cost_price,
                   COALESCE(rs.last_sold_at, NULL) AS last_sold_at,
                   (inv.current_stock * i.cost_price) AS stuck_sar
            FROM items i
            JOIN inventory inv ON i.id = inv.item_id
            LEFT JOIN recent_sales rs ON rs.item_id = i.id
            WHERE i.business_id = :b
              AND inv.business_id = :b
              AND inv.current_stock > 0
              AND COALESCE(rs.qty_30d, 0) < 1
            ORDER BY stuck_sar DESC NULLS LAST
            LIMIT 10
        """), {"b": str(business_id), "cutoff": cutoff})
        rows = [dict(r._mapping) for r in res.fetchall()]
        total_stuck = sum(float(r.get("stuck_sar") or 0) for r in rows)
        return {"dead_stock_items": rows, "total_stuck_sar": round(total_stuck, 2), "days_no_sale": days}

    return {"error": f"Tool '{tool_name}' unknown"}
