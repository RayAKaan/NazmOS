"""Tests for Phase 4: RLS code-prep.

4.1 -- ``agent_action_executor.approve_agent_action`` must not commit partway
       through a request.  A mid-function commit ends the transaction that
       carries ``SET LOCAL app.current_tenant_id``, so a later statement would
       run without RLS tenant context.  The function now commits exactly once.

4.2 -- ``app.database.connection`` must re-apply ``SET LOCAL app.current_tenant_id``
       (and the restricted app role) at the start of *every* transaction, so
       any commit point keeps RLS context for subsequent statements.
"""
import uuid

import pytest
from sqlalchemy import text

from app.services.agent_action_executor import approve_agent_action


class TestAgentActionExecutorSingleCommit:
    """4.1 -- no mid-function commit in the not-found path."""

    async def test_not_found_returns_without_committing(self, monkeypatch):
        commits = []
        wrote = []

        class FakeResult:
            def fetchone(self):
                return None

        class FakeSession:
            async def execute(self, stmt, params):
                wrote.append(str(stmt))
                return FakeResult()

            async def commit(self):
                commits.append(True)

        result = await approve_agent_action(
            FakeSession(),
            uuid.uuid4(),
            note="n/a",
            decided_by=uuid.uuid4(),
        )

        assert result["ok"] is False
        assert commits == [], "not-found path must not commit partway"
        assert len(wrote) == 1, "only the lookup UPDATE should run on the not-found path"


class TestConnectionReappliesRlsContext:
    """4.2 -- SET LOCAL is re-issued on every transaction begin."""

    def test_begin_listener_registered_for_production_engine(self):
        import app.database.connection as conn
        from sqlalchemy.engine.base import Engine

        sync_engine = conn.engine.sync_engine
        assert isinstance(sync_engine, Engine)
        begin_listeners = sync_engine.dispatch.begin.listeners
        assert len(begin_listeners) == 1

    def test_begin_listener_issues_set_local(self, monkeypatch):
        import app.database.connection as conn

        # Bind a fake engine whose transactions execute driver SQL directly.
        sqls = []

        class FakeConn:
            def exec_driver_sql(self, statement, *args, **kwargs):
                sqls.append(statement)

        listener = conn.engine.sync_engine.dispatch.begin.listeners[0]
        fn = getattr(listener, "fn", None) or listener

        monkeypatch.setattr(conn, "get_rls_tenant_id", lambda: "tenant-1234")
        monkeypatch.setattr(
            conn.settings, "DATABASE_APP_ROLE", "nazmos_app"
        )

        fn(FakeConn())

        assert "SET LOCAL app.current_tenant_id = 'tenant-1234'" in sqls
        assert 'SET LOCAL ROLE "nazmos_app"' in sqls

    def test_begin_listener_skips_when_no_tenant(self, monkeypatch):
        import app.database.connection as conn

        sqls = []

        class FakeConn:
            def exec_driver_sql(self, statement, *args, **kwargs):
                sqls.append(statement)

        listener = conn.engine.sync_engine.dispatch.begin.listeners[0]
        fn = getattr(listener, "fn", None) or listener

        monkeypatch.setattr(conn, "get_rls_tenant_id", lambda: None)
        monkeypatch.setattr(conn.settings, "DATABASE_APP_ROLE", "")

        fn(FakeConn())

        assert sqls == [], "no SET LOCAL when there is no tenant context"
