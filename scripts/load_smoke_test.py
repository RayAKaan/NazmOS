"""Lightweight concurrency smoke test for the NazmOS backend.

Runs without Locust. It registers a user, bootstraps a business, then fires
concurrent requests at the health, dashboard, and agent feed endpoints while
recording latencies. Use it in CI after the server has started.

Usage:
    export API_BASE_URL=http://localhost:8000
    python scripts/load_smoke_test.py
"""
from __future__ import annotations

import asyncio
import os
import statistics
import time
import uuid
from dataclasses import dataclass, field

import httpx


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
CONCURRENCY = int(os.getenv("LOAD_CONCURRENCY", "10"))
REQUESTS_PER_ENDPOINT = int(os.getenv("LOAD_REQUESTS_PER_ENDPOINT", "30"))
P95_THRESHOLD_MS = float(os.getenv("LOAD_P95_THRESHOLD_MS", "2000"))


@dataclass
class Timing:
    endpoint: str
    latencies_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        if not self.latencies_ms:
            return {"endpoint": self.endpoint, "count": 0, "errors": len(self.errors)}
        return {
            "endpoint": self.endpoint,
            "count": len(self.latencies_ms),
            "min_ms": round(min(self.latencies_ms), 2),
            "max_ms": round(max(self.latencies_ms), 2),
            "mean_ms": round(statistics.mean(self.latencies_ms), 2),
            "p95_ms": round(
                sorted(self.latencies_ms)[max(0, int(len(self.latencies_ms) * 0.95) - 1)], 2
            ),
            "errors": len(self.errors),
        }


async def measure(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict | None = None,
    json_body: dict | None = None,
) -> tuple[float, int, str]:
    start = time.perf_counter()
    response = await client.request(method, url, headers=headers, json=json_body)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return elapsed_ms, response.status_code, response.text


async def run() -> None:
    run_id = uuid.uuid4().hex[:8]
    email = f"load_{run_id}@example.com"
    password = "LoadTest123!"

    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0) as client:
        # Health check (no auth).
        health_timing = Timing("GET /health")
        for _ in range(REQUESTS_PER_ENDPOINT):
            elapsed, status, body = await measure(client, "GET", "/health")
            if status == 200:
                health_timing.latencies_ms.append(elapsed)
            else:
                health_timing.errors.append(f"status={status} body={body[:200]}")

        # Register and bootstrap a business.
        register_resp = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "Load Test"},
        )
        if register_resp.status_code not in (200, 201):
            raise RuntimeError(f"Registration failed: {register_resp.text}")

        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        if login_resp.status_code != 200:
            raise RuntimeError(f"Login failed: {login_resp.text}")

        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        bootstrap_resp = await client.post(
            "/api/v1/businesses/bootstrap",
            json={"name": "Load Test Baqala", "type": "baqala", "city": "Riyadh"},
            headers=headers,
        )
        if bootstrap_resp.status_code != 200:
            raise RuntimeError(f"Business bootstrap failed: {bootstrap_resp.text}")

        business_id = bootstrap_resp.json()["id"]

        # Concurrent authenticated requests.
        dashboard_timing = Timing("GET /api/v1/dashboard/summary")
        agent_timing = Timing("GET /api/v1/agent/feed")

        async def fire_dashboard():
            url = f"/api/v1/dashboard/summary?business_id={business_id}"
            elapsed, status, body = await measure(client, "GET", url, headers=headers)
            if status == 200:
                dashboard_timing.latencies_ms.append(elapsed)
            else:
                dashboard_timing.errors.append(f"status={status} body={body[:200]}")

        async def fire_agent_feed():
            url = f"/api/v1/agent/feed?business_id={business_id}"
            elapsed, status, body = await measure(client, "GET", url, headers=headers)
            if status == 200:
                agent_timing.latencies_ms.append(elapsed)
            else:
                agent_timing.errors.append(f"status={status} body={body[:200]}")

        async def worker():
            for _ in range(REQUESTS_PER_ENDPOINT // CONCURRENCY):
                await fire_dashboard()
                await fire_agent_feed()

        await asyncio.gather(*[worker() for _ in range(CONCURRENCY)])

    summaries = [health_timing.summary(), dashboard_timing.summary(), agent_timing.summary()]
    print("Load smoke test complete")
    print("-" * 80)
    for s in summaries:
        print(s)
    print("-" * 80)

    failures = [s for s in summaries if s.get("errors", 0) > 0]
    slow = [s for s in summaries if s.get("p95_ms", 0) > P95_THRESHOLD_MS]

    if failures:
        print(f"FAILED: {len(failures)} endpoint(s) returned errors.")
        raise SystemExit(1)
    if slow:
        print(f"FAILED: {len(slow)} endpoint(s) exceeded p95 threshold of {P95_THRESHOLD_MS}ms.")
        raise SystemExit(1)

    print("PASSED: all endpoints healthy and within latency threshold.")


if __name__ == "__main__":
    asyncio.run(run())
