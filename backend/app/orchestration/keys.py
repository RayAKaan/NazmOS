"""Deterministic execution-key derivation for idempotent execution.

Each execution attempt carries a stable key derived from the intent fields.
Activities check the key before applying side effects: if a terminal outcome
already exists for the key the activity returns it without re-applying.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID


def derive_execution_key(
    business_id: UUID | str,
    action_type: str,
    entity_type: str,
    entity_id: UUID | str,
    payload: dict[str, Any],
    source: str = "manual",
) -> str:
    """Return a 64-char SHA-256 hex digest identifying this execution attempt.

    The key is deterministic: identical inputs always produce the same key,
    which enables idempotent replay detection.
    """
    canonical = json.dumps(
        {
            "bid": str(business_id),
            "at": action_type,
            "et": entity_type,
            "eid": str(entity_id),
            "p": payload,
            "src": source,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:64]
