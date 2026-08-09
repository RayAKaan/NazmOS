"""Cross-tenant IDOR test suite.

Authenticate as merchant A and attempt to read/write business B's data by
substituting B's id (the classic multi-tenant IDOR). Every request must be
rejected with 403/404 and must never return business B's data with a 200.

This is the priority-1 deliverable of the access-control hardening track.
Run against a real Postgres test DB:
    python -m pytest tests/security/test_idor_cross_tenant.py -v
"""
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

# Cases: (name, method, path_template, param_name or None for path segment)
READ_CASES = [
    ("ops_pilot_console", "GET", "/api/v1/ops/pilot-console", "business_id"),
    ("pharmacy_lots", "GET", "/api/v1/pharmacy/lots", "business_id"),
    ("decisions_recommend", "GET", "/api/v1/decisions/recommend", "business_id"),
    ("dashboard_summary", "GET", "/api/v1/dashboard/summary", "business_id"),
    ("inventory_list", "GET", "/api/v1/inventory", "business_id"),
    ("money_audit_current", "GET", "/api/v1/money-audit/current", "business_id"),
    ("recovery_settings", "GET", "/api/v1/recovery-match/settings", "business_id"),
    ("events_list", "GET", "/api/v1/events", "business_id"),
    ("intelligence_memory", "GET", "/api/v1/intelligence/memory/current_state", "business_id"),
    ("intelligence_context", "GET", "/api/v1/intelligence/context", "business_id"),
    ("forecast_all_path", "GET", "/api/v1/forecast/all/{business_id}", "path"),
]

# Positive controls: attacker's own business_id must still work (200, not 403).
POSITIVE_CONTROL_CASES = [
    ("dashboard_summary", "GET", "/api/v1/dashboard/summary", "business_id"),
    ("inventory_list", "GET", "/api/v1/inventory", "business_id"),
    ("decisions_recommend", "GET", "/api/v1/decisions/recommend", "business_id"),
    ("events_list", "GET", "/api/v1/events", "business_id"),
]


async def _register_login_bootstrap(client: AsyncClient, email: str, name: str):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestPass123!", "full_name": name},
    )
    assert reg.status_code in (200, 201), f"register failed: {reg.text}"

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "TestPass123!"},
    )
    assert login.status_code == 200, f"login failed: {login.text}"
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    boot = await client.post(
        "/api/v1/businesses/bootstrap",
        json={"name": name, "type": "baqala", "city": "Riyadh"},
        headers=headers,
    )
    assert boot.status_code == 200, f"bootstrap failed: {boot.text}"
    return headers, boot.json()["id"]


@pytest_asyncio.fixture
async def two_tenants(client: AsyncClient) -> dict:
    """Two unrelated merchants: attacker A (attacker) and victim B (victim)."""
    headers_a, biz_a = await _register_login_bootstrap(
        client, "attacker_a@example.com", "Attacker A"
    )
    headers_b, biz_b = await _register_login_bootstrap(
        client, "victim_b@example.com", "Victim B"
    )
    return {
        "attacker_headers": headers_a,
        "victim_business_id": biz_b,
        "attacker_business_id": biz_a,
    }


def _url(path_template: str, business_id: str, param: str) -> str:
    if param == "path":
        return path_template.format(business_id=business_id)
    return f"{path_template}?{param}={business_id}"


@pytest.mark.parametrize(
    "name,method,path_template,param",
    READ_CASES,
    ids=[c[0] for c in READ_CASES],
)
@pytest.mark.asyncio
async def test_attacker_cannot_read_victim_data(
    client: AsyncClient,
    two_tenants: dict,
    name: str,
    method: str,
    path_template: str,
    param: str,
):
    url = _url(path_template, two_tenants["victim_business_id"], param)
    response = await client.request(
        method,
        url,
        headers=two_tenants["attacker_headers"],
    )
    assert (
        response.status_code in (403, 404)
    ), f"[{name}] cross-tenant request leaked: {response.status_code} {response.text[:200]}"


@pytest.mark.parametrize(
    "name,method,path_template,param",
    POSITIVE_CONTROL_CASES,
    ids=[c[0] for c in POSITIVE_CONTROL_CASES],
)
@pytest.mark.asyncio
async def test_owner_can_read_own_business(
    client: AsyncClient,
    two_tenants: dict,
    name: str,
    method: str,
    path_template: str,
    param: str,
):
    """Control: the same token against its OWN business must succeed."""
    url = _url(path_template, two_tenants["attacker_business_id"], param)
    response = await client.request(
        method,
        url,
        headers=two_tenants["attacker_headers"],
    )
    assert response.status_code == 200, (
        f"[{name}] legitimate owner request blocked: {response.status_code} {response.text[:200]}"
    )


@pytest.mark.asyncio
async def test_attacker_cannot_chat_into_victim_tenant(client, two_tenants):
    """POST /chat with a victim business_id must be rejected before any write."""
    response = await client.post(
        "/api/v1/chat/",
        params={
            "message": "hello",
            "business_id": two_tenants["victim_business_id"],
        },
        headers=two_tenants["attacker_headers"],
    )
    assert response.status_code in (403, 404), (
        f"cross-tenant chat write leaked: {response.status_code} {response.text[:200]}"
    )


@pytest.mark.asyncio
async def test_ops_console_requires_platform_operator(client, two_tenants):
    """A merchant owner (even for their own business) must not reach /ops."""
    for biz in (
        two_tenants["attacker_business_id"],
        two_tenants["victim_business_id"],
    ):
        response = await client.get(
            f"/api/v1/ops/pilot-console?business_id={biz}",
            headers=two_tenants["attacker_headers"],
        )
        assert response.status_code == 403, (
            f"merchant reached ops console: {response.status_code} {response.text[:200]}"
        )


@pytest.mark.asyncio
async def test_attacker_unknown_business_returns_404_not_data(client, two_tenants):
    """A random business id must 404 for an authenticated caller, never 200."""
    random_biz = str(uuid.uuid4())
    response = await client.get(
        f"/api/v1/money-audit/current?business_id={random_biz}",
        headers=two_tenants["attacker_headers"],
    )
    assert response.status_code == 404, (
        f"unknown business leaked: {response.status_code} {response.text[:200]}"
    )


@pytest.mark.asyncio
async def test_admin_backup_requires_platform_operator(client, two_tenants):
    """Admin backups must not be reachable by a merchant owner."""
    response = await client.get(
        "/api/v1/admin/backups",
        headers=two_tenants["attacker_headers"],
    )
    assert response.status_code == 403, (
        f"merchant reached admin backups: {response.status_code} {response.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Phase 4 — denial-logging proof: every denied access must leave an audit row
# ---------------------------------------------------------------------------

async def _latest_denial_row(client, attacker_email: str, victim_business_id: str, action_type: str):
    """Read the most recent denial row for the attacker via the app's real DB.

    ``record_access_denial`` writes through its own AsyncSessionLocal scoped to
    the subject tenant, so we read with the same tenant context.
    """
    from app.database.connection import AsyncSessionLocal, _rls_tenant_id, set_rls_tenant_id
    from sqlalchemy import text

    token = set_rls_tenant_id(victim_business_id)
    try:
        async with AsyncSessionLocal() as s:
            row = (
                await s.execute(
                    text(
                        """
                        SELECT action_type, action_category, user_email,
                               business_id, entity_name, new_value, created_at
                        FROM audit_log
                        WHERE user_email = :email
                          AND action_category = 'authorization'
                          AND action_type = :action_type
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"email": attacker_email, "action_type": action_type},
                )
            ).fetchone()
            return dict(row._mapping) if row else None
    finally:
        _rls_tenant_id.reset(token)


@pytest.mark.asyncio
async def test_cross_tenant_denial_written_to_audit_log(client, two_tenants):
    """Merchant A's attempt to read merchant B's money-audit is logged."""
    victim = two_tenants["victim_business_id"]
    attacker_email = "attacker_a@example.com"

    response = await client.get(
        f"/api/v1/money-audit/current?business_id={victim}",
        headers=two_tenants["attacker_headers"],
    )
    assert response.status_code in (403, 404)

    row = await _latest_denial_row(
        client, attacker_email, victim, "access_denied_tenant_access"
    )
    assert row is not None, "no tenant_access denial row written to audit_log"
    assert row["action_category"] == "authorization"
    assert str(row["business_id"]) == victim
    assert row["new_value"]["reason"] in ("not_owner_or_team_member", "business_not_found")


@pytest.mark.asyncio
async def test_ops_denial_written_to_audit_log(client, two_tenants):
    """Merchant A hitting the founder-only ops console is logged as well."""
    victim = two_tenants["victim_business_id"]
    attacker_email = "attacker_a@example.com"

    response = await client.get(
        f"/api/v1/ops/pilot-console?business_id={victim}",
        headers=two_tenants["attacker_headers"],
    )
    assert response.status_code == 403

    row = await _latest_denial_row(
        client, attacker_email, victim, "access_denied_is_platform_operator"
    )
    assert row is not None, "no is_platform_operator denial row written to audit_log"
    assert row["action_category"] == "authorization"
    assert str(row["business_id"]) == victim
    assert row["new_value"]["reason"] == "not_platform_operator"
