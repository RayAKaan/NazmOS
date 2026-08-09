"""
Universal AI Agentic Orchestrator Router
Exposes inter-branch stock rebalancing and proactive profit optimization endpoints.
Applicable across every sector: Supermarkets, Cafes, Date Traders, Pharmacies, Hardware.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, User
from app.middleware.auth_middleware import get_current_user
from app.middleware.rbac import require_capability
from app.middleware.business_access import assert_business_access
from app.middleware.feature_gate import require_feature
from app.services.inventory_orchestrator import analyze_inter_branch_rebalancing
from app.services.profit_optimizer import scan_profit_margin_compression

router = APIRouter(prefix="/api/v1/orchestrator", tags=["Universal Agentic Orchestration"])


@router.get("/rebalance", dependencies=[Depends(require_capability("can_run_orchestrator", "business_id"))])
async def get_inter_branch_rebalancing(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns location-aware stock rebalancing suggestions across store branches.
    Transfers stock internally to eliminate unnecessary external supplier orders.
    """
    await assert_business_access(db, business_id, current_user)
    await require_feature(db, business_id, "multi_branch_rebalancing", required_plan="Growing Retail")
    return await analyze_inter_branch_rebalancing(db, business_id)


@router.get("/profit-scan", dependencies=[Depends(require_capability("can_run_orchestrator", "business_id"))])
async def get_profit_optimization_scan(
    business_id: UUID = Query(...),
    target_min_margin_pct: float = Query(20.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Proactively scans product lines for wholesale cost inflation and net margin compression.
    Generates Shariah Anti-Ihtikar compliant shelf price adjustments.
    """
    await assert_business_access(db, business_id, current_user)
    await require_feature(db, business_id, "pricing_optimization", required_plan="Free Money Audit")
    return await scan_profit_margin_compression(db, business_id, target_min_margin_pct)
