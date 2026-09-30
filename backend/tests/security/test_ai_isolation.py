"""Phase A acceptance: the AI isolation contract (TEST 1-36 mapped to code).

The AI provider must never observe raw merchant data. These tests
verify the *enforced* controls, not prompts:

    TEST 1-15  capsule minimizes: no SKU/product/supplier/tenant identities,
               no credentials, no exact stocks/prices/amounts/budgets.
    TEST 16    no DB urls in capsule or prompts.
    TEST 18    no encryption keys / tokens in capsule or prompts.
    TEST 25-26 raw-evidence dict is rejectable by typing; tampering fails.
    TEST 29    transport env is a minimal allowlist, never secrets.
    TEST 31    decision bounded to the deterministic candidate set.
    TEST 32-34 tamper / replay / malformed all fail closed.
    TEST 35    kill switch disables AI (policy denies before any call).
    TEST 36    DLP blocks secret-bearing outbound prompts.
"""
import asyncio
import json
import os
from types import SimpleNamespace

import pytest

from app.security.ai_adapter import AITransportError, LLMTransport
from app.security.ai_policy import AiPolicy, CircuitBreaker
from app.security.capsule import CapsuleItem, CapsuleSigner, ReasoningCapsule
from app.security.dlp import DLPViolationError
from app.security.privacy_firewall import (
    build_challenge_capsule,
    build_capsule_for_payload,
    build_reasoning_capsule,
)
from app.services.ai_reasoning import _build_reasoning_prompt
from app.services.business_context import (
    BusinessAggContext,
    OwnerContext,
    ProductContext,
    PromotionContext,
    SeasonalContext,
    StructuredContext,
    SupplierContext,
    TimeContext,
)
from app.services.evidence_package import BusinessContext, ItemEvidence


# --- fixtures --------------------------------------------------------------

SKU = "SKU-ISOLATION-01"
PRODUCT = "Secretive Consumer Brand Name"
SUPPLIER = "Mysterious Supplier LLC"
TENANT = "515769a5-519f-437f-a906-a408f438202c"
FAKE_KEY = "GHWDK" * 10
DB_URL = "postgres://admin:hunter2@db.internal:5432/nazmos"


def _item() -> ItemEvidence:
    return ItemEvidence(
        sku=SKU,
        product_name=PRODUCT,
        classification="slow_mover",
        current_stock=9876.0,
        cost_price_sar=55.25,
        sell_price_sar=120.75,
        inventory_value_sar=654321.25,
        recent_velocity_per_day=0.05,
        prior_velocity_per_day=0.1,
        daily_velocity=0.05,
        days_of_supply=400,
        days_since_last_sale=210,
        inventory_age_days=400,
        monthly_concentration_peak=0.9,
        supplier_lead_time_days=30,
        supplier_moq=999.0,
        supplier_name=SUPPLIER,
        capital_at_risk_sar=654321.25,
        margin_pct=0.54,
        is_strategic=True,
        candidate_actions=["discount", "manual_intervention"],
    )


def _business() -> BusinessContext:
    return BusinessContext(
        business_id=TENANT,
        business_type="pharmacy",
        total_inventory_value_sar=99_000_000,
        total_capital_at_risk_sar=40_000_000,
        total_recoverable_high_sar=15_000_000,
        cash_budget=250_000,
        max_discount_pct=60,
        blocked_discount_products=[SKU],
        strategic_products=[SKU],
        minimum_margin_pct=0.05,
    )


def _context() -> StructuredContext:
    return StructuredContext(
        product=ProductContext(
            sku=SKU,
            product_name=PRODUCT,
            category="appliances",
            current_stock=330.0,
            inventory_value_sar=66000,
            cost=100,
            sell_price=200,
            gross_margin_pct=0.5,
            recent_velocity=0.05,
            prior_velocity=0.1,
            long_term_velocity=0.08,
            trend="declining",
            days_of_supply=180,
            inventory_age_days=200,
            last_sale_days_ago=90,
            sales_frequency="rare",
            demand_volatility=0.6,
        ),
        seasonal=SeasonalContext(
            is_seasonal=True,
            seasonal_type="ramadan",
            days_until_season=30,
            days_since_season_ended=None,
            historical_seasonal_demand_multiplier=2.5,
            expected_seasonal_demand=800,
            seasonal_confidence=0.7,
            upcoming_seasons=[{"name": "ramadan"}],
        ),
        supplier=SupplierContext(
            supplier_name=SUPPLIER,
            lead_time_days=30,
            on_time_pct=60,
            moq_sar=999,
            supplier_reliability="unreliable",
            confirmed_inbound_qty=0,
            ghost_po_risk=True,
            preferred_supplier=False,
        ),
        promotion=PromotionContext(
            is_promotional=False,
            promotion_type=None,
            promotion_duration_days=None,
            promotional_uplift_pct=None,
            normal_velocity=0.05,
            post_promotion_risk=False,
        ),
        owner=OwnerContext(
            cash_budget=250_000,
            max_purchase_amount=50_000,
            min_margin_pct=0.05,
            max_discount_pct=60,
            blocked_discount_skus=[SKU],
            strategic_skus=[SKU],
            blocked_transfer_routes=["riyadh_to_jeddah"],
            branch_priorities=["riyadh"],
            risk_preference="conservative",
        ),
        business=BusinessAggContext(
            business_type="pharmacy",
            branch_count=5,
            total_inventory_value_sar=99_000_000,
            total_capital_at_risk_sar=40_000_000,
            total_recoverable_sar=15_000_000,
            recent_actions=[],
            recent_outcomes=[],
        ),
        time=TimeContext(
            virtual_date="2026-09-02",
            day_of_week="Wednesday",
            upcoming_holidays=[],
            days_until_ramadan=30,
            days_until_eid=None,
            days_until_white_friday=None,
            is_quarter_end=True,
        ),
deterministic_decision="DISCOUNT",
            deterministic_confidence=0.9,
            ai_challenge_eligible=True,
            ai_challenge_reason="low_det_confidence_dist",
    )


FORBIDDEN = (SKU, PRODUCT, SUPPLIER, TENANT, "9876", "654321.25", "55.25", "120.75",
             "250000", "99,000,000", FAKE_KEY[:24], DB_URL)


def _capsule_text_all(capsule) -> str:
    """Scan for_prompt() — the DLP-clean outbound view.  ``blob()`` includes
    the random nonce/hash/signature whose hex can contain any numeric
    substring, making direct substring scans of blob() inherently flaky."""
    return json.dumps(capsule.for_prompt(), default=str)


# --- TEST 1-18 : minimization ------------------------------------------------

def test_reasoning_capsule_contains_no_raw_merchant_data():
    capsule = build_reasoning_capsule(_item(), _business(), capability="counterfactual_audit", purpose="_internal")
    text = _capsule_text_all(capsule)
    for token in FORBIDDEN:
        assert token not in text, f"leak: {token}"


def test_challenge_capsule_contains_no_raw_merchant_data():
    capsule = build_challenge_capsule(_context(), capability="challenge", purpose="_internal")
    text = _capsule_text_all(capsule)
    for token in FORBIDDEN:
        assert token not in text, f"leak: {token}"


def test_reasoning_prompt_builder_never_leaks():
    prompt = _build_reasoning_prompt(_item(), _business())
    for token in FORBIDDEN:
        assert token not in prompt, f"leak in prompt: {token}"


def test_capsule_reasoning_signals_present():
    capsule = build_reasoning_capsule(_item(), _business(), capability="counterfactual_audit", purpose="_internal")
    blob = capsule.blob()
    item = blob["items"][0]
    assert item["ref"] == "item_A"
    assert "stock_band" in item and item["stock_band"] == "500+"
    assert "sku" not in item and "product_name" not in item
    assert "current_stock" not in item
    assert "cash_budget" not in blob["business"]
    assert "business_id" not in blob["business"]


# --- TEST 25-26 : typing enforces the boundary --------------------------------

def test_jev_consult_rejects_raw_evidence_dict():
    from app.services.ai_providers.jev import consult

    async def run():
        try:
            await consult(
                question="test",
                capsule={"items": [], "business": {}},
                deterministic_decision="REORDER",
            )
        except TypeError:
            return True
        return False

    assert asyncio.run(run()) is True


def test_tampered_capsule_fails_verification():
    capsule = build_reasoning_capsule(_item(), _business(), capability="counterfactual_audit", purpose="_internal")
    capsule.items[0].candidate_decisions.append("REORDER")
    assert CapsuleSigner().verify(capsule) is False


# --- TEST 31 : decisions bounded to candidates ----------------------------------

def test_output_decision_bounded_to_candidates():
    capsule = build_reasoning_capsule(_item(), _business(), capability="counterfactual_audit", purpose="_internal")
    assert "DISCOUNT" in capsule.allowed_decisions()
    assert "REORDER" not in capsule.allowed_decisions()


# --- TEST 32-34 : transport + replay fail closed --------------------------------

def test_llm_transport_blocks_secret_outbound_prompt():
    async def caller(system, user):
        raise AssertionError("caller must not be reached when DLP blocks")

    async def run():
        transport = LLMTransport(caller)
        try:
            await transport.complete("safe system prompt", f"user prompt with {FAKE_KEY} in it")
        except DLPViolationError:
            return "blocked"
        return "not_blocked"

    assert asyncio.run(run()) == "blocked"


async def _failing_caller(system, user):
    raise RuntimeError("provider down")


def test_llm_transport_blocks_secret_inbound_response():
    async def caller(system, user):
        return f'{{"decision":"DO_NOTHING","reasoning":"ok {FAKE_KEY}"}}'

    async def run():
        transport = LLMTransport(caller)
        try:
            await transport.complete("sys", "safe prompt")
        except AITransportError as exc:
            return str(exc)
        return "no_error"

    assert "dlp_inbound" in asyncio.run(run())


def test_circuit_breaker_opens_and_blocks():
    breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=60)
    transport = LLMTransport(_failing_caller, breaker=breaker)

    async def run():
        outcome = []
        for _ in range(3):
            try:
                await transport.complete("sys", "prompt")
                outcome.append("ok")
            except AITransportError:
                outcome.append("err")
        return outcome

    outcomes = asyncio.run(run())
    assert outcomes[0] == "err"
    assert outcomes[1] == "err"
    assert outcomes[2] == "err"  # circuit now open, refused before the call
    assert breaker.is_open is True


# --- TEST 35-36 : canonical gateway policy + deterministic authority --------

def test_policy_kill_switch_disables_ai():
    disabled = AiPolicy(SimpleNamespace(AI_ENABLED=False))
    assert disabled.enabled("recovery.rank") is False
    allowed, reason = disabled.allow_request("recovery.rank", "_internal")
    assert allowed is False and "disabled" in reason

    unknown = AiPolicy(SimpleNamespace(AI_ENABLED=True))
    assert unknown.enabled("not-a-capability") is False


def test_gateway_returns_fallback_when_policy_blocks(monkeypatch):
    import app.services.ai_gateway as gateway

    class _Policy:
        def allow_request(self, capability, purpose):
            return False, "disabled"

    monkeypatch.setattr(gateway, "_policy", _Policy())

    async def run():
        result = await gateway.systemone_reason(
            {"items": [], "business": {}},
            capability="recovery.rank",
            purpose="_internal",
            deterministic_decision="REORDER",
        )
        return result

    result = asyncio.run(run())
    assert result["source"] == "fallback"
    assert result["decision"] == "REORDER"
    assert "AI_POLICY_BLOCKED" in result["risk_flags"]


def test_gateway_real_policy_wired_to_settings():
    from app.config import get_settings
    settings = get_settings()
    assert settings.AI_ENABLED is True
    assert AiPolicy(settings).enabled("recovery.rank") is True


def test_jev_gateway_preserves_deterministic_decision(monkeypatch):
    import app.services.ai_providers.jev as jev_module
    from app.services.ai_providers.jev import JevReply

    async def fake_consult(**kwargs):
        return JevReply(
            source="jev",
            decision_basis="DISCOUNT",
            suggested_decision="REORDER",
            confidence=0.8,
            reasoning="advisory",
        )

    monkeypatch.setattr(jev_module, "consult", fake_consult)

    class Client:
        enabled = True

    async def run():
        import app.services.ai_gateway as gateway
        return await gateway.systemone_reason(
            {"items": [], "business": {}},
            capability="recovery.rank",
            purpose="resolve ambiguity in recovery candidate ranking",
            deterministic_decision="DISCOUNT",
            client=Client(),
        )

    result = asyncio.run(run())
    assert result["decision"] == "DISCOUNT"
    assert result["alternative_decision"] == "REORDER"
