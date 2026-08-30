"""WS8 — legacy / experimental surface isolation.

The what-if and demo engines (simulation_engine, time_machine, nazm_planner,
closed_loop_experiment, v8_business_simulator) are OPTIONAL, read-only-ish
projection surfaces.  This suite pins that:

1. ``simulate_time_machine`` is a pure projection — deterministic, bounded by
   the recoverable-range estimate, and impossible for it to write to money
   tables (it takes no session).
2. ``create_simulation`` persists ONLY its own ``Simulation`` row (isolated
   demo table), never core tables.
3. Static wiring guard: the monetized decision chain never imports a demo
   module; demo modules may only be reached from explicitly allowed files.
"""
import ast
import pathlib

import pytest

APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"

BANNED_DEMO_ROOT = {
    "v8_business_simulator",
    "closed_loop_experiment",
    "simulation_engine",
    "time_machine",
    "nazm_planner",
}

# Files allowed to reach a demo module (demonstration endpoints / the what-if
# simulation surface).  Everything else in app/ that imports one fails.
DEMO_ALLOWED_IMPORTERS = {
    "app.routers.intelligence",
    "app.routers.money_audit",
    "app.routers.agent",
    "app.services.intelligence_api",        # /simulate what-if surface
    "app.services.closed_loop_experiment",  # its own experimental driver
}

# The monetized chain: these modules must never depend on a demo engine.
PROTECTED_CANONICAL = {
    "execution_engine",
    "agent_action_executor",
    "action_registry",
    "agent_tools",
    "action_executor",
    "money_audit_service",
    "recovery_intelligence",
    "recovery_match_matcher",
    "recovery_match_service",
    "analytics_service",
    "goal_service",
    "goal_domains",
    "audit_engine",
    "autonomy_service",
    "runtime",
    "decision_engine",
}


def _py_files():
    for path in sorted(APP_DIR.rglob("*.py")):
        yield path, pathlib.PurePosixPath(path.relative_to(APP_DIR.parent)).as_posix()


def _imported_demo_roots(filename: str, tree: ast.AST) -> set[str]:
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for banned in BANNED_DEMO_ROOT:
                    if banned == alias.name.split(".")[-1]:
                        roots.add(banned)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            parts = mod.split(".")
            imported_names = {n.name for n in node.names}
            for banned in BANNED_DEMO_ROOT:
                if banned in parts or banned in imported_names:
                    roots.add(banned)
    return roots


def _demo_import_map() -> dict[str, set[str]]:
    out = {}
    for path, dotted in _py_files():
        if ".pyc" in dotted:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        roots = _imported_demo_roots(dotted, tree)
        if roots:
            mod_name = dotted[:-3].replace("/", ".") if dotted.endswith(".py") else dotted
            out[mod_name] = roots
    return out


def test_demo_modules_only_reachable_from_allowlist():
    importers = _demo_import_map()
    violations = {
        mod: roots for mod, roots in importers.items()
        if mod not in DEMO_ALLOWED_IMPORTERS and mod not in PROTECTED_CANONICAL
        and not mod.startswith("app.tasks") and not mod.startswith("app.utils")
    }
    assert violations == {}, f"demo engines reachable from: {violations}"


def test_canonical_chain_never_imports_demo_engines():
    importers = _demo_import_map()
    violations = {
        mod: roots for mod, roots in importers.items()
        if mod in PROTECTED_CANONICAL
    }
    assert violations == {}, \
        f"monetized chain depends on demo engines: {violations}"


def test_time_machine_is_deterministic_and_bounded():
    from app.services.time_machine import simulate_time_machine

    base = {
        "sku": "1001", "product_name": "Milk", "classification": "FAST",
        "current_stock": 10, "cost_price_sar": 5.0, "sell_price_sar": 8.0,
        "daily_velocity": 2.0, "days_of_supply": 5,
        "action_type": "discount", "recoverable_low_sar": 20.0,
        "recoverable_high_sar": 40.0,
    }
    items = [{**base, "sku": "1001"}, {**base, "sku": "1002"}]
    days = [simulate_time_machine(items=items, horizon_days=30)
            for _ in range(2)]
    assert days[0].do_nothing.total_impact_sar == days[1].do_nothing.total_impact_sar
    assert days[0].nazmos_recommendation.total_impact_sar == days[1].nazmos_recommendation.total_impact_sar
    assert days[0].do_nothing.estimated is True, "projections are always ESTIMATES"

    for it in days[0].nazmos_recommendation.item_details:
        # projection is an ESTIMATE bounded by the recoverable range
        if it.financial_impact_sar > 0:
            assert it.financial_impact_sar <= 40.0, \
                "estimated impact must never exceed the recoverable_high bound"
    assert days[0].do_nothing.item_details, "scenario must produce a do-nothing projection"


import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.services.simulation_engine import create_simulation


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_create_simulation_persists_only_own_table(db):
    """Simulation engine writes nothing outside Simulation (its isolated demo
    table): prove core monetized tables stay untouched on the same session."""
    import uuid

    bid = uuid.uuid4()
    sim = await create_simulation(
        db, bid, "ws8-isolation",
        scenario={"what_if": "discount_fast_movers"},
        assumptions={"horizon_days": 30},
    )
    await db.commit()

    sim_rows = (await db.execute(text("SELECT COUNT(*) FROM simulations"))).scalar()
    money_rows = (await db.execute(text("SELECT COUNT(*) FROM money_audit_actions"))).scalar()
    exec_rows = (await db.execute(text("SELECT COUNT(*) FROM execution_jobs"))).scalar()
    audit_rows = (await db.execute(text("SELECT COUNT(*) FROM money_audits"))).scalar()
    assert sim_rows == 1
    assert money_rows == 0, "simulation must not create money actions"
    assert exec_rows == 0, "simulation must not create execution jobs"
    assert audit_rows == 0, "simulation must not create audits"
    assert sim.status == "completed"