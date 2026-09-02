"""Tests for the OpenCode Master System Prompt (PROMPT 2) + agent rendering.

Verifies the static prompt is DLP-clean, does not leak merchant field names, is
synchronized with the enforced output-gate field names, and renders into an
OpenCode agent whose tool permissions are entirely denied (pure reasoning).
"""
from __future__ import annotations

import pytest

from app.security.ai_adapter import OpenCodeSubprocessTransport
from app.security.dlp import DLP_RULES, DlpScanner
from app.security.master_prompt import (
    FULL_SYSTEM_PROMPT,
    MASTER_SYSTEM_PROMPT,
    AGENT_DENIED_PERMISSIONS,
    OUTPUT_SCHEMA,
    render_agent_markdown,
)

FORBIDDEN_MERCHANT_FIELDS = ["two_factor_secret", "credentials_encrypted"]
ENFORCED_OUTPUT_FIELDS = {
    "decision",
    "confidence",
    "reasoning",
    "evidence_ids",
    "risk_flags",
    "alternative_decision",
    "challenge",
}


def test_master_prompt_is_dlp_clean():
    scanner = DlpScanner(rules=list(DLP_RULES), strict=True)
    assert scanner.scan(MASTER_SYSTEM_PROMPT) == []
    assert scanner.scan(FULL_SYSTEM_PROMPT) == []
    assert scanner.scan(render_agent_markdown()) == []


def test_master_prompt_does_not_leak_merchant_field_names():
    for field in FORBIDDEN_MERCHANT_FIELDS:
        assert field not in MASTER_SYSTEM_PROMPT.lower()


def test_output_schema_uses_enforced_field_names():
    # The prompt must use evidence_ids, NOT the draft's evidence_refs.
    assert "evidence_ids" in OUTPUT_SCHEMA
    assert "evidence_refs" not in OUTPUT_SCHEMA
    for field in ENFORCED_OUTPUT_FIELDS:
        assert field in OUTPUT_SCHEMA


def test_output_schema_field_names_match_gate_schema():
    from app.security.output_gate import OutputVerdict

    gate_fields = {f.name for f in OutputVerdict.__dataclass_fields__.values()}
    assert ENFORCED_OUTPUT_FIELDS <= gate_fields


def test_agent_permissions_all_denied():
    agent = render_agent_markdown()
    assert "permission:" in agent
    for key, value in AGENT_DENIED_PERMISSIONS.items():
        assert f"{key}: {value}" in agent
    assert all(value == "deny" for value in AGENT_DENIED_PERMISSIONS.values())


def test_agent_has_no_tool_permission_grants():
    # No permission value may grant access (e.g. allow/ask).
    assert set(AGENT_DENIED_PERMISSIONS.values()) == {"deny"}


def test_subprocess_render_agent_matches_master_prompt():
    rendered = OpenCodeSubprocessTransport._render_agent(FULL_SYSTEM_PROMPT)
    assert FULL_SYSTEM_PROMPT in rendered
    assert "read: deny" in rendered
    assert "bash: deny" in rendered
    scanner = DlpScanner(rules=list(DLP_RULES), strict=True)
    assert scanner.scan(rendered) == []
