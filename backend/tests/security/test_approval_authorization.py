"""Approval / execution authorization tests.

Owner and admin may approve/execute. Staff/viewer must be rejected with 403.

The capability model (capabilities_service.py) grants `can_approve_actions`
only to role in ("owner", "admin"). This test proves:

1. Viewer cannot approve an agent action (403).
2. Viewer cannot set the autonomy dial (403).
3. Owner can approve their own pending action (200).
4. Cross-business: a member of business B cannot approve A's pending actions.

All tests use the live HTTP client against the real Postgres test DB.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text


async def _register_login_bootstrap(client, email, name):
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
    return headers, boot.json()["id"], token


async def _seed_agent_action(db, business_id, action_id, *, status="pending_approval"):
    await db.execute(
        text(
            "INSERT INTO agent_actions "
            "(id, business_id, action_type, status, payload, title, summary, "
            "confidence, priority, autonomy_dial_at_creation, created_at, updated_at) "
            "VALUES (:id, :b, 'reorder', :status, CAST(:payload AS JSON), "
            "'Test Restock', 'Test summary', 0.9, 1, 50, NOW(), NOW())"
        ),
        {
            "id": str(action_id),
            "b": str(business_id),
            "status": status,
            "payload": '{"item_id":"00000000-0000-0000-0000-000000000001","quantity":10}',
        },
    )


async def _seed_team_member(db, user_id, business_id, role="staff"):
    """Insert a team member with the given role into the test DB."""
    await db.execute(
        text(
            "INSERT INTO team_members (id, user_id, business_id, role, is_active, created_at) "
            "VALUES (gen_random_uuid(), :u, :b, :role, true, NOW())"
        ),
        {"u": str(user_id), "b": str(business_id), "role": role},
    )


async def _get_user_id_by_email(db, email):
    res = await db.execute(
        text("SELECT id FROM users WHERE email = :e"), {"e": email}
    )
    row = res.fetchone()
    return row.id if row else None


@pytest_asyncio.fixture
async def auth_context(client, db_session):
    """Register an owner, create an agent action, return ids/tokens."""
    owner_headers, owner_biz, owner_token = await _register_login_bootstrap(
        client, "owner_rbac@example.com", "Owner RBAC"
    )
    action_id = uuid.uuid4()
    await _seed_agent_action(db_session, owner_biz, action_id)
    await db_session.commit()
    return {
        "owner_headers": owner_headers,
        "owner_biz": owner_biz,
        "owner_token": owner_token,
        "action_id": action_id,
        "db": db_session,
    }


@pytest.mark.asyncio
async def test_viewer_cannot_approve_agent_action(client, auth_context, db_session):
    """A staff/viewer user must get 403 when trying to approve an action."""
    owner_biz = auth_context["owner_biz"]
    # Register a viewer and add them as staff
    viewer_headers, viewer_biz, _ = await _register_login_bootstrap(
        client, "viewer_approve@example.com", "Viewer"
    )
    # viewer_biz is the viewer's OWN business. Instead we need a staff user
    # in the OWNER's business. Register separately and add via TeamMember.
    # We need the viewer user id and add as staff to owner's business.
    viewer_email = "viewer_approve@example.com"
    viewer_id = await _get_user_id_by_email(db_session, viewer_email)
    await _seed_team_member(db_session, viewer_id, owner_biz, role="staff")
    await db_session.commit()

    action_id = auth_context["action_id"]
    res = await client.post(
        f"/api/v1/agent/actions/{action_id}/approve",
        params={"business_id": str(owner_biz)},
        headers=viewer_headers,
    )
    assert res.status_code == 403, (
        f"Viewer should not approve: {res.status_code} {res.text[:200]}"
    )


@pytest.mark.asyncio
async def test_owner_can_approve_agent_action(client, auth_context):
    """The business owner can approve their own pending actions (200)."""
    action_id = auth_context["action_id"]
    res = await client.post(
        f"/api/v1/agent/actions/{action_id}/approve",
        params={"business_id": str(auth_context["owner_biz"])},
        headers=auth_context["owner_headers"],
    )
    assert res.status_code == 200, (
        f"Owner approval failed: {res.status_code} {res.text[:200]}"
    )
    body = res.json()
    assert body.get("ok") is True or body.get("status") == "approved"


@pytest.mark.asyncio
async def test_viewer_cannot_set_autonomy(client, auth_context, db_session):
    """A staff/viewer must get 403 when trying to change the autonomy dial."""
    owner_biz = auth_context["owner_biz"]
    viewer_email = "viewer_autonomy@example.com"
    viewer_headers, _, _ = await _register_login_bootstrap(
        client, viewer_email, "Viewer Autonomy"
    )
    viewer_id = await _get_user_id_by_email(db_session, viewer_email)
    await _seed_team_member(db_session, viewer_id, owner_biz, role="staff")
    await db_session.commit()

    res = await client.put(
        "/api/v1/agent/autonomy",
        params={"business_id": str(owner_biz)},
        json={"policies": [{"action_type": "restock", "dial": 100}]},
        headers=viewer_headers,
    )
    assert res.status_code == 403, (
        f"Viewer should not set autonomy: {res.status_code} {res.text[:200]}"
    )


@pytest.mark.asyncio
async def test_owner_can_set_autonomy(client, auth_context):
    """The business owner can update the autonomy dial (200)."""
    res = await client.put(
        "/api/v1/agent/autonomy",
        params={"business_id": str(auth_context["owner_biz"])},
        json={"policies": [{"action_type": "restock", "dial": 50}]},
        headers=auth_context["owner_headers"],
    )
    assert res.status_code == 200, (
        f"Owner autonomy update failed: {res.status_code} {res.text[:200]}"
    )


@pytest.mark.asyncio
async def test_cross_business_member_cannot_approve(
    client, auth_context, db_session
):
    """A member of business B cannot approve business A's actions."""
    owner_biz = auth_context["owner_biz"]
    other_headers, other_biz, _ = await _register_login_bootstrap(
        client, "other_biz_approver@example.com", "Other Biz"
    )
    # This user is the OWNER of other_biz (has can_approve_actions on other_biz).
    # But they have NO relationship to owner_biz → assert_business_access blocks.
    action_id = auth_context["action_id"]
    res = await client.post(
        f"/api/v1/agent/actions/{action_id}/approve",
        params={"business_id": str(owner_biz)},
        headers=other_headers,
    )
    assert res.status_code in (403, 404), (
        f"Cross-business member should not approve: {res.status_code} {res.text[:200]}"
    )
