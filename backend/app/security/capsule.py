"""ReasoningCapsule: the ONLY data an AI may observe.

A capsule is created in the trusted zone by ``privacy_firewall`` and signed
with ``CapsuleSigner``. It contains banded, derived signals only -- no SKUs,
product or supplier names, no exact SAR amounts, no customer/tenant identifiers,
no credentials, no database URLs, no encryption keys.

The output gate binds any AI response to the capsule it was issued for:
the decision must be a candidate the deterministic engine already proposed,
``evidence_ids`` must be capsule signal names, and the response must not
contain exact financial values or injection attempts.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field

SIGNAL_VERSION = "1"


class CapsuleBusiness(BaseModel):
    business_type: str | None = None
    branch_count: int | None = None
    capital_at_risk_band: str | None = None      # LOW | MEDIUM | HIGH
    cash_available: str | None = None           # LOW | MEDIUM | HIGH


class CapsuleItem(BaseModel):
    ref: str                                    # opaque ref: "item_A"
    classification: str | None = None
    stock_band: str | None = None               # "0-9","10-49","50-199","200-499","500+"
    velocity_band: str | None = None            # NONE | LOW | MEDIUM | HIGH
    days_of_supply_band: str | None = None      # CRITICAL | LOW | ADEQUATE | OVER
    is_overstock: bool = False
    is_stockout_risk: bool = False
    inventory_age_band: str | None = None       # FRESH | AGING | OLD
    last_sale_band: str | None = None           # RECENT | WEEK | MONTH | NONE
    is_seasonal: bool = False
    seasonal_type: str | None = None
    days_until_season: int | None = None
    trend: str | None = None                    # declining | stable | growing | flat
    sales_frequency_band: str | None = None     # daily | weekly | monthly | rare | never
    demand_volatility_band: str | None = None   # LOW | MEDIUM | HIGH
    margin_band: str | None = None              # LOW | MEDIUM | HIGH
    supplier_reliability_band: str | None = None  # LOW | MEDIUM | HIGH
    supplier_lead_time_band: str | None = None  # SHORT | MEDIUM | LONG
    inbound_band: str | None = None             # NONE | LOW | MEDIUM | HIGH
    is_strategic: bool = False
    is_promotional: bool = False
    promotion_type: str | None = None
    monthly_concentration_band: str | None = None  # LOW | MEDIUM | HIGH
    candidate_decisions: list[str] = Field(default_factory=list)
    evidence_fields: list[str] = Field(default_factory=list)


class CapsuleConstraints(BaseModel):
    max_discount_band: str | None = None    # conservative | moderate | aggressive
    min_margin_band: str | None = None      # LOW | MEDIUM | HIGH
    blocked_refs: list[str] = Field(default_factory=list)
    transfer_allowed: bool = True


class ReasoningCapsule(BaseModel):
    capsule_id: str
    request_id: str
    nonce: str
    capability: str
    purpose: str
    signal_version: str = SIGNAL_VERSION
    issued_at: datetime
    expires_at: datetime
    business: CapsuleBusiness = Field(default_factory=CapsuleBusiness)
    items: list[CapsuleItem] = Field(default_factory=list)
    constraints: CapsuleConstraints = Field(default_factory=CapsuleConstraints)
    forecast_signals: dict[str, dict[str, Any]] = Field(default_factory=dict)
    capsule_hash: str = ""
    signature: str = ""

    # NOTE: this model deliberately has NO tenant id, business id, user id,
    # SKU, name, or explicit financial field. See classification.py.

    @classmethod
    def new(
        cls,
        *,
        capability: str,
        purpose: str,
        items: list[CapsuleItem],
        business: CapsuleBusiness | None = None,
        constraints: CapsuleConstraints | None = None,
        forecast_signals: dict[str, dict[str, Any]] | None = None,
        ttl_seconds: int = 90,
    ) -> "ReasoningCapsule":
        now = datetime.now(timezone.utc)
        return cls(
            capsule_id=str(uuid.uuid4()),
            request_id=str(uuid.uuid4()),
            nonce=secrets.token_hex(16),
            capability=capability,
            purpose=purpose,
            issued_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            business=business or CapsuleBusiness(),
            items=items,
            constraints=constraints or CapsuleConstraints(),
            forecast_signals=forecast_signals or {},
        )

    # --- serialization -----------------------------------------------------

    def canonical_bytes(self) -> bytes:
        """Byte-stable canonical JSON without the hash/signature fields."""
        payload = self.model_dump(mode="json")
        payload.pop("capsule_hash", None)
        payload.pop("signature", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return canonical.encode("utf-8")

    def blob(self) -> dict[str, Any]:
        """Prompt-ready view of the capsule (everything the AI is allowed to see)."""
        return self.model_dump(mode="json")

    def for_prompt(self) -> dict[str, Any]:
        """Decision view for AI prompts: drops trusted-zone bookkeeping.

        UUIDs, nonce, capsule hash, signature and timestamps are process
        internal; they are not sent to the LLM or OpenCode. This also keeps the
        outbound DLP clean (the DLP blocks raw UUIDs on the wire).
        """
        return self.model_dump(
            mode="json",
            exclude={
                "capsule_id",
                "request_id",
                "nonce",
                "capsule_hash",
                "signature",
                "issued_at",
                "expires_at",
                "signal_version",
            },
        )

    def allowed_decisions(self) -> frozenset[str]:
        allowed: set[str] = {"DO_NOTHING", "MANUAL_REVIEW"}
        for item in self.items:
            for d in item.candidate_decisions or []:
                allowed.add(str(d).upper())
        return frozenset(allowed)

    def allowed_evidence(self) -> frozenset[str]:
        allowed: set[str] = set()
        for item in self.items:
            allowed.add(item.ref)
            for f in item.evidence_fields or []:
                allowed.add(f"{item.ref}.{f}")
        allowed.update({"deterministic_decision", "deterministic_confidence"})
        allowed.update(f"{k}" for k in (self.forecast_signals or {}).keys())
        for ref in self.forecast_signals or {}:
            allowed.update(f"{ref}.{k}" for k in (self.forecast_signals[ref] or {}).keys())
        return frozenset(allowed)

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if self.expires_at is None:
            return True
        if self.expires_at.tzinfo is None:
            return now > self.expires_at.replace(tzinfo=timezone.utc)
        return now > self.expires_at

    def is_fresh(self, now: datetime | None = None) -> bool:
        return not self.is_expired(now)


class CapsuleSigner:
    """HMAC-SHA256 signature over the capsule's canonical JSON.

    Signing key precedence:
      1. settings.NAZMOS_CAPSULE_SIGNING_KEY (production: required >= 32 chars)
      2. derived from SECRET_KEY (dev only, so local runs need no new env var)
    """

    def __init__(self, key: bytes | str | None = None, *, secret_key: str | None = None):
        if key is None:
            base = (secret_key or os.getenv("SECRET_KEY", "") or "")
            if base:
                key = hashlib.sha256(base.encode("utf-8")).digest()
            else:
                key = hashlib.sha256(b"nazmos-dev-no-secret").digest()
        if isinstance(key, str):
            key = key.encode("utf-8")
        self._key = key

    def sign(self, capsule: ReasoningCapsule) -> ReasoningCapsule:
        capsule.capsule_hash = hashlib.sha256(capsule.canonical_bytes()).hexdigest()
        capsule.signature = hmac.new(self._key, capsule.canonical_bytes(), hashlib.sha256).hexdigest()
        return capsule

    def verify(self, capsule: ReasoningCapsule) -> bool:
        if not capsule.signature:
            return bool(capsule.capsule_hash)
        try:
            expected = hmac.new(self._key, capsule.canonical_bytes(), hashlib.sha256).hexdigest()
        except Exception:
            return False
        return hmac.compare_digest(expected, capsule.signature)