"""WS4 — execution-path clarity (EXECUTION_PATH_ADR.md).

The ADR defines two intentional paths:
  Simulated:  execution_engine.execute_from_request  → must NOT mutate business data
  Real:       agent_action_executor.execute_agent_action → DOES mutate business data

These tests lock that boundary so it cannot silently blur:
  1. behavioral — the simulated path never touches items/inventory and emits
     an execution.completed event;
  2. behavioral — the real path actually mutates the database;
  3. static — the production router wiring matches the ADR entry points.
"""
import ast
import pathlib

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from tests.fixtures.merchants import seed_recurring_stockout_merchant

APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


def _imports(module: "pathlib.Path") -> set[str]:
    """Fully-qualified modules imported by ``module``.

    ``from X import Y`` where X is a package (e.g. ``from app.services
    import execution_engine``) is resolved against the app tree so a real
    submodule name is recorded, not just the package.
    """
    app_root = APP_DIR.parent
    tree = ast.parse(module.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            for alias in node.names:
                candidate = f"{node.module}.{alias.asname or alias.name}"
                rel = app_root / (candidate.replace(".", "/") + ".py")
                if rel.is_file() or (app_root / (node.module.replace(".", "/")) / f"{alias.name}.py").is_file():
                    out.add(candidate)
    return out


async def test_simulated_path_never_mutates_business_data(db):
    from app.services.execution_engine import execute_from_request

    info = await seed_recurring_stockout_merchant(db)
    bid = info["business_id"]
    item_id = info["item_id"]

    before = dict((await db.execute(
        text("SELECT sell_price FROM items WHERE id = :i"), {"i": item_id}
    )).fetchone()._mapping)
    before_stock = (await db.execute(
        text("SELECT current_stock FROM inventory WHERE item_id = :i"), {"i": item_id}
    )).scalar_one()

    job = await execute_from_request(
        db, bid, "restock", "item", item_id, {"recommended_qty": 50}
    )
    await db.commit()

    assert job.status == "completed"
    assert job.result.get("simulated") is True

    after = dict((await db.execute(
        text("SELECT sell_price FROM items WHERE id = :i"), {"i": item_id}
    )).fetchone()._mapping)
    after_stock = (await db.execute(
        text("SELECT current_stock FROM inventory WHERE item_id = :i"), {"i": item_id}
    )).scalar_one()
    assert after["sell_price"] == before["sell_price"], "simulated path must not reprice"
    assert after_stock == before_stock, "simulated path must not move stock"

    ev = (await db.execute(
        text("SELECT event_type, source FROM events WHERE business_id = :b AND event_type = 'execution.completed'"),
        {"b": bid},
    )).fetchall()
    assert len(ev) == 1 and ev[0].source == "execution_engine"


async def test_same_action_both_paths_contract(db_session):
    """ADR §7 gap: the SAME action type must differ — simulate vs real mutate."""
    from uuid import uuid4

    from app.services.agent_action_executor import execute_agent_action
    from app.services.execution_engine import execute_from_request

    info = await seed_recurring_stockout_merchant(db_session)
    bid = info["business_id"]
    item_id = info["item_id"]
    original = float((await db_session.execute(
        text("SELECT sell_price FROM items WHERE id = :i"), {"i": item_id}
    )).scalar_one())

    # Real path first: reprices the item.
    outcome = await execute_agent_action(
        db_session, bid, str(uuid4()), "pricing_decrease",
        {"item_id": item_id, "suggested_price": 2.5},
    )
    assert outcome["executed"] is True, f"real path should execute, got {outcome}"
    assert float((await db_session.execute(
        text("SELECT sell_price FROM items WHERE id = :i"), {"i": item_id}
    )).scalar_one()) == 2.5, "real path must persist the new price"
    await db_session.commit()

    # Simulated path: same action type must NOT reprice again.
    item_b = info["item_id"]
    job = await execute_from_request(
        db_session, bid, "pricing_decrease", "item", item_b, {"suggested_price": 1.0}
    )
    await db_session.commit()
    assert job.result.get("simulated") is True
    still = float((await db_session.execute(
        text("SELECT sell_price FROM items WHERE id = :i"), {"i": item_id}
    )).scalar_one())
    assert still == 2.5, "simulated path must not apply the requested price"
    assert original == 3.0, "fixture sanity: milk priced at 3.0"


def test_production_router_wiring_matches_adr():
    intel_imports = _imports(APP_DIR / "routers" / "intelligence.py")
    assert "app.services.execution_engine" in intel_imports
    assert "app.services.agent_action_executor" not in intel_imports, \
        "simulated entry point must not import the real executor"

    for name in ("agent.py", "whatsapp.py"):
        imports = _imports(APP_DIR / "routers" / name)
        assert "app.services.agent_action_executor" in imports, f"{name} must use the real executor"
        assert "app.services.execution_engine" not in imports, \
            f"{name} approval path must not bypass via the simulated engine"

    api_imports = _imports(APP_DIR / "services" / "intelligence_api.py")
    assert "app.services.execution_engine" in api_imports
    assert "app.services.agent_action_executor" not in api_imports


def test_shared_registry_is_only_real_path_bridge():
    """runtime/autonomy bridge to the executor is deliberate and singular."""
    runtime = _imports(APP_DIR / "services" / "runtime.py")
    autonomy = _imports(APP_DIR / "services" / "autonomy_service.py")
    assert "app.services.agent_action_executor" in runtime
    assert "app.services.agent_action_executor" in autonomy
    assert "app.services.execution_engine" not in runtime, \
        "runtime must not simulate real actions"