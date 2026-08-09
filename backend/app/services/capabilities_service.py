"""Capability resolution for NazmOS.

This is the single source of truth for what an authenticated user may do.
Capabilities are computed server-side from real role/flag data (never from
client-supplied claims) and returned in the auth/session response. The
frontend renders from this object, and the backend re-checks the SAME
capabilities on every request via ``require_capability`` /
``assert_platform_operator`` / ``assert_business_access``.

Capability names are a stable contract between backend and frontend; add new
ones here, mirror the key in the frontend ``capabilities`` type, and gate with
``require_capability``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import Business, TeamMember, User
from app.services.multi_tenant import MultiTenantService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Capability registry (single source of truth)
# ---------------------------------------------------------------------------

# Platform capabilities: true only for the NazmOS operator (founder).
PLATFORM_CAPABILITIES = frozenset(
    {
        "is_platform_operator",   # raw operator flag/allowlist membership
        "can_view_ops_console",   # /ops pilot console
        "can_run_admin_tools",    # admin backups, partner approvals, POS webhook replay, nightly scans
    }
)

# Business capabilities: resolved per active business context.
BUSINESS_CAPABILITIES = frozenset(
    {
        "can_manage_team",        # invite/update/remove team members
        "can_run_orchestrator",   # orchestrator rebalance / profit-scan
        "can_approve_actions",    # approve/reject agent + money-audit actions
    }
)

ALL_CAPABILITIES = PLATFORM_CAPABILITIES | BUSINESS_CAPABILITIES


@dataclass
class Capabilities:
    is_platform_operator: bool = False
    can_view_ops_console: bool = False
    can_run_admin_tools: bool = False
    can_manage_team: bool = False
    can_run_orchestrator: bool = False
    can_approve_actions: bool = False
    # Business-context role: "owner" | "admin" | "manager" | "staff" | None.
    role: str | None = "owner"
    business_id: UUID | None = None
    # Internal; never serialized.
    _all: frozenset = field(default_factory=lambda: ALL_CAPABILITIES, repr=False)

    def has(self, capability: str) -> bool:
        return bool(getattr(self, capability, False))

    def to_dict(self) -> dict:
        return {cap: bool(getattr(self, cap, False)) for cap in self._all}


def _founder_emails() -> set[str]:
    raw = get_settings().FOUNDER_EMAILS or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_platform_operator(user: User) -> bool:
    """True when the user is the NazmOS operator (DB flag OR env allowlist)."""
    if getattr(user, "is_platform_operator", False):
        return True
    return (user.email or "").strip().lower() in _founder_emails()


async def _resolve_business_role(
    db: AsyncSession,
    user: User,
    business_id: UUID | str | None,
) -> tuple[str | None, UUID | None]:
    """Resolve the caller's role within the given (or default) business.

    The business is only used as a *context* for capability evaluation; the
    caller still needs real access, so a user with no relationship to the
    business resolves to role=None and every business capability is false.
    """
    if business_id is None:
        mts = MultiTenantService(db)
        accessible = await mts.get_business_ids_for_user(user.id)
        if not accessible:
            return None, None
        business_id = accessible[0]

    try:
        resolved = UUID(str(business_id))
    except (ValueError, TypeError):
        return None, None

    business = await db.get(Business, resolved)
    if business is None:
        return None, resolved

    if business.owner_id == user.id:
        return "owner", resolved

    member = (
        await db.execute(
            select(TeamMember).where(
                TeamMember.user_id == user.id,
                TeamMember.business_id == resolved,
                TeamMember.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if member is not None:
        return member.role, resolved

    return None, resolved


async def build_capabilities(
    db: AsyncSession,
    user: User,
    business_id: UUID | str | None = None,
) -> Capabilities:
    """Compute the full capabilities object for a user."""
    operator = is_platform_operator(user)
    role, resolved_business_id = await _resolve_business_role(db, user, business_id)

    return Capabilities(
        is_platform_operator=operator,
        can_view_ops_console=operator,
        can_run_admin_tools=operator,
        can_manage_team=role in ("owner", "admin"),
        can_run_orchestrator=role in ("owner", "admin", "manager"),
        can_approve_actions=role in ("owner", "admin"),
        role=role,
        business_id=resolved_business_id,
    )
