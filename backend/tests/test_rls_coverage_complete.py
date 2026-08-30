"""WS2 drift-guard: every ORM business-scoped table must have RLS coverage.

Enumerates every table in ``Base.metadata`` that carries a tenant column
(``business_id`` or the stock-recovery ``*_business_id`` columns) and asserts
the table is covered by a ``CREATE POLICY *_tenant_isolation`` statement in
some Alembic migration, OR is explicitly listed here as exempt.

The exempt list is deliberate, documented debt:
  - team_members        backs the cross-tenant "which businesses does this user
                        belong to" lookup in routers/businesses.py — RLS would
                        hide memberships outside the current tenant.
  - team_invitations, supplier_prices, partner_referrals, idempotency_keys
                        have a NULLABLE business_id; RLS WITH CHECK would reject
                        rows written with NULL, so tenant-column normalization
                        must precede RLS enablement.

This test runs on SQLite (no database required) so it fires in CI on every
suite run.
"""
from __future__ import annotations

import ast
import glob
import os

import pytest

from app.database.models import Base

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")

TENANT_SCHEMA = "business_id"
TENANT_SCHEMA_ALT = ("seller_business_id", "buyer_business_id", "actor_business_id")

# Deliberately excluded — see module docstring. Must never grow without
# closing the underlying nullable/cross-tenant gap first.
EXEMPT = {
    "idempotency_keys",
    "partner_referrals",
    "supplier_prices",
    "team_invitations",
    "team_members",
}


def _policy_covered_tables() -> set[str]:
    """Table names referenced by any *_tenant_isolation policy creation."""
    covered: set[str] = set()
    for path in glob.glob(os.path.join(MIGRATIONS_DIR, "*.py")):
        try:
            tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        except (OSError, SyntaxError):
            pytest.fail(f"Cannot parse migration {path} for RLS coverage scan")
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "TENANT_TABLES" for t in node.targets
            ):
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    for el in node.value.elts:
                        if isinstance(el, ast.Constant) and isinstance(el.value, str):
                            covered.add(el.value)
            if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
                # e.g. ``for table in ("business_context", "event_derivations"):``
                for el in node.iter.elts:
                    if isinstance(el, ast.Constant) and isinstance(el.value, str):
                        covered.add(el.value)
            if isinstance(node, ast.Dict) and any(
                isinstance(v, ast.Constant) and v.value in TENANT_SCHEMA_ALT
                for v in node.values
            ):
                # CUSTOM_COLUMN_TABLES: keys are the policy-covered table names,
                # values are the tenant column that differs from business_id.
                for k in node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        covered.add(k.value)
    return covered


def _orm_business_scoped_tables() -> set[str]:
    result: set[str] = set()
    for table in Base.metadata.tables.values():
        columns = {c.name for c in table.columns}
        if TENANT_SCHEMA in columns or columns.intersection(TENANT_SCHEMA_ALT):
            result.add(table.name)
    return result


def test_every_business_scoped_table_has_rls_coverage():
    covered = _policy_covered_tables()
    assert covered, "No RLS policy coverage detected in any migration"
    missing = sorted(table for table in _orm_business_scoped_tables() - covered - EXEMPT)
    assert not missing, (
        "Business-scoped ORM tables without an RLS tenant_isolation policy: "
        f"{missing}. Add a policy migration (and app-role grants), then update "
        "test_rls_predicate_indexes.TENANT_TABLES; do not extend EXEMPT without "
        "closing the nullable/cross-tenant gap first."
    )


def test_phase_b_core_services_migration_covers_expected_tables():
    """The WS2 hardening migration must keep covering the nine core tables."""
    covered = _policy_covered_tables()
    for table in (
        "agent_runs",
        "audit_runs",
        "business_goals",
        "constraint_blocks",
        "findings",
        "goal_progress_history",
        "impact_ledger",
        "learned_outcomes",
        "pilot_baselines",
    ):
        assert table in covered, f"{table} lost its RLS tenant_isolation policy"


def test_exempt_allowlist_never_grows_silently():
    """EXEMPT must stay fixed at the five documented nullable/cross-tenant tables."""
    assert EXEMPT == {
        "idempotency_keys",
        "partner_referrals",
        "supplier_prices",
        "team_invitations",
        "team_members",
    }