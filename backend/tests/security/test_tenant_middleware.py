"""Phase B: RLS tenant scoping must come from the token-validated tenant.

Regression test for the ordering bug where ``_extract_business_id`` (client-
controlled) was used to scope RLS before any ownership check. After the fix,
RLS is set exclusively from ``_set_tenant_context``'s authorized result.
"""
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.middleware.rls_tenant import TenantContextMiddleware


def _make_request(path: str) -> Mock:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(b"authorization", b"Bearer test-token")],
        "query_string": b"",
    }
    request = Mock()
    request.url.path = path
    request.method = "POST"
    request.headers.get = Mock(side_effect=lambda name, default=None: {"authorization": "Bearer test-token"}.get(name, default))
    request.path_params = {}
    request.query_params = {}
    request.state = Mock()
    return request


class _Capture:
    def __init__(self):
        self.rls_set = []

    async def call_next(self, request):
        return "response"


@pytest.mark.asyncio
async def test_rls_scope_never_uses_unverified_business_id(monkeypatch):
    attacker_id = uuid4()
    authorized_id = uuid4()

    middleware = TenantContextMiddleware.__new__(TenantContextMiddleware)
    middleware.logger = Mock()

    set_called = []
    fake_cv = Mock()

    async def fake_set_context(request, raw_business_id):
        # The caller's token ONLY authorizes the real business, never the
        # attacker-chosen id from the query/body.
        assert raw_business_id == attacker_id
        request.state.tenant_context = "ctx"
        return authorized_id

    monkeypatch.setattr("app.middleware.rls_tenant.set_rls_tenant_id", lambda tid: (set_called.append(tid), Mock())[1])
    monkeypatch.setattr("app.middleware.rls_tenant._rls_tenant_id", fake_cv)
    monkeypatch.setattr(TenantContextMiddleware, "_extract_business_id", AsyncMock(return_value=attacker_id))
    monkeypatch.setattr(middleware, "_set_tenant_context", fake_set_context)

    request = _make_request("/api/v1/inventory")
    response = await middleware.dispatch(request, _Capture().call_next)

    assert response == "response"
    # RLS was scoped to the AUTHORIZED business (token-derived), never the raw id.
    assert set_called == [str(authorized_id)]
    assert fake_cv.reset.call_count == 1


@pytest.mark.asyncio
async def test_rls_not_set_without_authorized_tenant(monkeypatch):
    attacker_id = uuid4()

    middleware = TenantContextMiddleware.__new__(TenantContextMiddleware)
    middleware.logger = Mock()

    set_called = []
    fake_cv = Mock()

    async def fake_set_context(request, raw_business_id):
        return None  # unauthenticated / no accessible business

    monkeypatch.setattr("app.middleware.rls_tenant.set_rls_tenant_id", lambda tid: (set_called.append(tid), Mock())[1])
    monkeypatch.setattr("app.middleware.rls_tenant._rls_tenant_id", fake_cv)
    monkeypatch.setattr(TenantContextMiddleware, "_extract_business_id", AsyncMock(return_value=attacker_id))
    monkeypatch.setattr(middleware, "_set_tenant_context", fake_set_context)

    request = _make_request("/api/v1/inventory")
    response = await middleware.dispatch(request, _Capture().call_next)

    assert response == "response"
    assert set_called == []
    assert fake_cv.reset.call_count == 0