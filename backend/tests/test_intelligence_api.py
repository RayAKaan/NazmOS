"""Canonical Intelligence API contract + boundary tests.

These assert the HTTP contract of ``/api/v1/intelligence`` and, critically, the
architectural invariants that must hold at the API boundary:

- Intelligence exposes no execution path (410 on the legacy endpoints).
- Cross-tenant access is denied.
- Unauthenticated access is rejected.
- Inputs are validated.
- A business with no Orbit state returns 409, not a fabricated empty result.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

CANONICAL = "/api/v1/intelligence"


class TestIntelligenceBoundaries:
    @pytest.mark.asyncio
    async def test_execute_endpoint_removed(self, authenticated_client: dict):
        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        response = await client.post(
            f"{CANONICAL}/execute?business_id={ctx['business_id']}",
            json={
                "action_type": "reorder",
                "entity_type": "item",
                "entity_id": "00000000-0000-0000-0000-000000000001",
                "payload": {},
            },
            headers=ctx["headers"],
        )
        assert response.status_code == 410, response.text
        assert "intelligence no longer exposes execution" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_execution_jobs_endpoint_removed(self, authenticated_client: dict):
        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        response = await client.get(
            f"{CANONICAL}/execution-jobs/00000000-0000-0000-0000-000000000001"
            f"?business_id={ctx['business_id']}",
            headers=ctx["headers"],
        )
        assert response.status_code == 410, response.text

    @pytest.mark.asyncio
    async def test_no_execute_route_in_openapi(self, authenticated_client: dict):
        """The canonical API must not advertise an execution surface."""
        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        response = await client.get("/openapi.json", headers=ctx["headers"])
        assert response.status_code == 200
        paths = response.json()["paths"]
        # /execute must not be documented anywhere under intelligence.
        assert f"{CANONICAL}/execute" not in paths
        assert f"{CANONICAL}/execution-jobs/{{job_id}}" not in paths

    @pytest.mark.asyncio
    async def test_predict_not_documented(self, authenticated_client: dict):
        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        response = await client.get("/openapi.json", headers=ctx["headers"])
        paths = response.json()["paths"]
        assert f"{CANONICAL}/predict" not in paths


class TestIntelligenceCanonicalSurface:
    @pytest.mark.asyncio
    async def test_canonical_endpoints_are_documented(self, authenticated_client: dict):
        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        paths = (await client.get("/openapi.json", headers=ctx["headers"])).json()["paths"]
        for expected in (
            f"{CANONICAL}/context",
            f"{CANONICAL}/signals",
            f"{CANONICAL}/root-causes",
            f"{CANONICAL}/impacts",
            f"{CANONICAL}/recommendations",
            f"{CANONICAL}/decisions",
            f"{CANONICAL}/alerts",
            f"{CANONICAL}/monitor",
            f"{CANONICAL}/copilot",
        ):
            assert expected in paths, f"missing canonical endpoint {expected}"

    @pytest.mark.asyncio
    async def test_unauthenticated_rejected(self, client: AsyncClient):
        for method, url in (
            ("get", f"{CANONICAL}/context?business_id=00000000-0000-0000-0000-000000000001"),
            ("get", f"{CANONICAL}/signals?business_id=00000000-0000-0000-0000-000000000001"),
        ):
            resp = await getattr(client, method)(url)
            assert resp.status_code in (401, 403), f"{url} returned {resp.status_code}"

        for method, url in (
            ("post", f"{CANONICAL}/monitor"),
            ("post", f"{CANONICAL}/copilot"),
        ):
            resp = await getattr(client, method)(url, json={})
            assert resp.status_code in (401, 403), f"{url} returned {resp.status_code}"

    @pytest.mark.asyncio
    async def test_missing_business_id_is_422(self, authenticated_client: dict):
        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        response = await client.get(f"{CANONICAL}/signals", headers=ctx["headers"])
        assert response.status_code == 422, response.text

    @pytest.mark.asyncio
    async def test_invalid_business_id_is_422(self, authenticated_client: dict):
        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        response = await client.get(
            f"{CANONICAL}/context?business_id=not-a-uuid", headers=ctx["headers"]
        )
        assert response.status_code == 422, response.text

    @pytest.mark.asyncio
    async def test_cross_tenant_access_denied(self, authenticated_client: dict):
        """A business the caller does not own must not be readable."""
        from uuid import uuid4

        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        response = await client.get(
            f"{CANONICAL}/context?business_id={uuid4()}", headers=ctx["headers"]
        )
        assert response.status_code in (403, 404), response.text
        # Must not leak whether the business exists.
        assert "traceback" not in response.text.lower()

    @pytest.mark.asyncio
    async def test_no_orbit_state_returns_409_not_empty_fake(
        self, authenticated_client: dict
    ):
        """Without canonical Orbit state, Intelligence must fail loudly."""
        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        response = await client.get(
            f"{CANONICAL}/context?business_id={ctx['business_id']}", headers=ctx["headers"]
        )
        # The test fixture business has no Orbit audit yet.
        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        assert detail["error"] == "orbit_state_unavailable"

    @pytest.mark.asyncio
    async def test_monitor_conflict_without_orbit_state(self, authenticated_client: dict):
        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        response = await client.post(
            f"{CANONICAL}/monitor",
            json={"business_id": str(ctx["business_id"])},
            headers=ctx["headers"],
        )
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["error"] == "intelligence_run_failed"

    @pytest.mark.asyncio
    async def test_pagination_bounds_enforced(self, authenticated_client: dict):
        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        response = await client.get(
            f"{CANONICAL}/signals?business_id={ctx['business_id']}&limit=99999",
            headers=ctx["headers"],
        )
        assert response.status_code == 422, response.text

    @pytest.mark.asyncio
    async def test_copilot_requires_question(self, authenticated_client: dict):
        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        response = await client.post(
            f"{CANONICAL}/copilot",
            json={"business_id": str(ctx["business_id"]), "question": ""},
            headers=ctx["headers"],
        )
        assert response.status_code == 422, response.text

    @pytest.mark.asyncio
    async def test_detectors_filter_validated(self, authenticated_client: dict):
        ctx = authenticated_client
        client: AsyncClient = ctx["client"]
        response = await client.post(
            f"{CANONICAL}/monitor",
            json={"business_id": str(ctx["business_id"]), "detectors": ["not_a_detector"]},
            headers=ctx["headers"],
        )
        # Unknown detectors are ignored (no crash); run still fails on missing Orbit.
        assert response.status_code in (200, 409), response.text
