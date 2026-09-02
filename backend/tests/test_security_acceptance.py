"""Phase F: security-hardening acceptance — a single stack verifying the
Phase A–E guarantees still hold from the AI isolation core outward.
"""
import asyncio

import pytest

# Full-app tests that need a migrated Postgres are gated; the capsule/firewall
# and policy-kill-switch tests are DB-free and always run.
try:
    from app.database.connection import engine

    async def _pg() -> bool:
        try:
            async with engine.connect() as conn:
                await conn.exec_driver_sql("SELECT 1")
            return True
        except Exception:
            return False

    POSTGRES = asyncio.run(_pg())
except Exception:
    POSTGRES = False

from app.security.ai_adapter import LLMTransport
from app.security.ai_policy import AiPolicy
from app.security.capsule import CapsuleSigner, ReasoningCapsule
from app.security.dlp import DLPViolationError
from app.security.privacy_firewall import (
    build_capsule_for_payload,
    build_challenge_capsule,
    build_reasoning_capsule,
)
from app.services.ai_reasoning import _build_reasoning_prompt

# Reuse the canonical isolation fixtures so this acceptance file exercises the
# SAME payloads as the Phase A suite (single source of truth).
from tests.security.test_ai_isolation import (
    FORBIDDEN,
    _business,
    _context,
    _item,
)

FAKE_KEY = "GHWDK" * 10


def test_capsules_still_minimize_end_to_end():
    for capsule in (
        build_reasoning_capsule(_item(), _business(), capability="counterfactual_audit", purpose="_internal"),
        build_challenge_capsule(_context(), capability="challenge", purpose="_internal"),
    ):
        text = str(capsule.blob())
        for token in FORBIDDEN:
            assert token not in text, f"leak: {token}"


def test_ai_reasoning_prompt_never_leaks():
    prompt = _build_reasoning_prompt(_item(), _business())
    for token in FORBIDDEN:
        assert token not in prompt, f"leak in prompt: {token}"


def test_capsule_for_prompt_drops_trusted_zone_bookkeeping():
    capsule = build_reasoning_capsule(_item(), _business(), capability="counterfactual_audit", purpose="_internal")
    prompt = capsule.for_prompt()
    text = str(prompt)
    # Nonce/hash/signature/timestamps are trusted-zone only — never sent.
    for key in ("signature", "capsule_hash", "request_id", "nonce", "issued_at", "expires_at"):
        assert key not in text, f"bookkeeping leak: {key}"


def test_tamper_fails_closed():
    capsule = build_reasoning_capsule(_item(), _business(), capability="counterfactual_audit", purpose="_internal")
    capsule.items[0].candidate_decisions.append("REORDER")
    assert CapsuleSigner().verify(capsule) is False


def test_dlp_blocks_secret_outbound():
    async def caller(system, user):
        raise AssertionError("caller must not run when DLP blocks")

    async def run():
        transport = LLMTransport(caller)
        try:
            await transport.complete("safe system", f"user prompt with {FAKE_KEY} in it")
        except DLPViolationError:
            return "blocked"
        return "not_blocked"

    assert asyncio.run(run()) == "blocked"


def test_kill_switch_disables_ai():
    from types import SimpleNamespace
    disabled = AiPolicy(SimpleNamespace(AI_ENABLED=False))
    assert disabled.enabled("opencode_brain") is False


# ---- DB-gated full-app (fresh migrated Postgres) -----------------------------


@pytest.mark.skipif(not POSTGRES, reason="needs Postgres")
def test_unknown_webhook_business_rejected():
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async def run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post(
                "/api/v1/pos/foodics/webhook",
                json={
                    "event": "order_created",
                    "provider": "foodics",
                    "business_id": "00000000-0000-0000-0000-000000000099",
                    "data": {},
                },
            )
            return res.status_code

    assert asyncio.run(run()) in (401, 403, 404)


@pytest.mark.skipif(not POSTGRES, reason="needs Postgres")
def test_auth_me_never_exposes_two_factor_secret():
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async def run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/auth/me")
            body = res.text
            assert "JBSWY3DPEHPK3PXP" not in body
            if "two_factor_secret" in body:
                assert "[REDACTED]" in body
            return True

    assert asyncio.run(run()) is True


def test_security_tooling_config_files_present():
    import os
    here = os.path.dirname(__file__)
    repo = os.path.abspath(os.path.join(here, "..", ".."))
    assert os.path.exists(os.path.join(repo, ".gitleaks.toml"))
    assert os.path.exists(os.path.join(repo, ".pre-commit-config.yaml"))
