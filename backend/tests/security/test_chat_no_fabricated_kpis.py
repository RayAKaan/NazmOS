"""Regression: chat context must never contain fabricated merchant KPIs.

The chat endpoint (and the ContextBuilder it feeds) previously hardcoded
fabricated business values (sales=18450, profit=3200, transactions=145,
wednesday_dip_pct=31, weekend_uplift_pct=38, "13 stockouts", etc.) directly
into the AI system prompt. This is source-of-truth poisoning: the model is told
merchant-specific facts that have no basis in the ledger.

These tests assert:
1. No hardcoded merchant KPI literals remain in the chat/context code path.
2. The chat KPI builders can never produce fabricated values — they return
   UNKNOWN/unavailable when no ledger data exists.
3. The ContextBuilder does NOT inject a fabricated default patterns dict.
4. The chat suggestions / context_summary cannot fabricate stockout counts.
"""
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2] / "app"

# The exact literals previously fabricated. A curated scan across every Python
# file in app/ must never contain these in a chat/context source.
FABRICATED_LITERALS = [
    "18450",
    '"profit": 3200',
    "wednesday_dip_pct",
    "weekend_uplift_pct",
    "dip by 31%",
    '"context_summary": "3 critical stockouts',
    "tuesday_dip_pct",
    "peak_hours",
    '"today": {"sales": 18450',
    "3 critical stockouts",
    "4 dead stock items",
]

CHAT_FILES = [
    "routers/chat.py",
    "services/context_builder.py",
    "services/chat_memory.py",
    "services/prompt_engine.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("literal", FABRICATED_LITERALS)
def test_no_fabricated_kpi_literal_in_chat_path(literal):
    """The proven-fabricated literals must be absent from the chat source path."""
    hits = []
    for rel in CHAT_FILES:
        src = _read(APP_ROOT / rel)
        if literal in src:
            hits.append(rel)
    assert not hits, (
        f"Fabricated KPI literal {literal!r} still present in: {hits}"
    )


def test_no_fabricated_numbers_in_any_chat_kpi_source():
    """chat.py and context_builder.py must not contain the old hardcoded trio."""
    for rel in ("routers/chat.py", "services/context_builder.py"):
        src = _read(APP_ROOT / rel)
        for literal in ('"sales": 18450', "profit\": 3200", "transactions\": 145"):
            assert literal not in src, f"{rel} still contains {literal}"


def test_context_builder_has_no_fabricated_pattern_fallback():
    """ContextBuilder must not inject a merchant-fabricated default patterns dict."""
    src = _read(APP_ROOT / "services/context_builder.py")
    assert "perfect_day_of_week" not in src
    # must not bake in a mercantile 28%/42% fabrications
    assert "tuesday_dip_pct" not in src
    assert "weekend_uplift_pct" not in src
    assert "peak_hours" not in src


def test_chat_uses_deterministic_kpi_functions():
    """chat.py must compute KPIs via DB-backed helpers, not inline constants."""
    src = _read(APP_ROOT / "routers/chat.py")
    assert "_compute_chat_kpis" in src, "chat.py must compute KPIs from the ledger"
    assert "_compute_weekday_patterns" in src, "chat.py must compute patterns from data"
    assert "_compute_chat_alerts" in src, "chat.py must compute stock alerts from data"


@pytest.mark.asyncio
async def test_chat_kpis_unknown_when_no_data_present():
    """With no ledger rows, the KPI builder must return UNKNOWN, never 0/fabricated."""
    from app.routers.chat import _compute_chat_kpis, _UNKNOWN

    class _NoRows:
        async def execute(self, *a, **k):
            class _R:
                def fetchone(self):
                    return None
            return _R()

    kpis = await _compute_chat_kpis(_NoRows(), "b1")
    assert kpis["today"]["sales"] == _UNKNOWN
    assert kpis["today"]["profit"] == _UNKNOWN
    assert kpis["today"]["transactions"] == _UNKNOWN
    assert kpis["stock_value"] == _UNKNOWN


@pytest.mark.asyncio
async def test_chat_kpis_unknown_on_db_exception():
    """Any DB failure must degrade to UNKNOWN, never a fabricated number."""
    from app.routers.chat import _compute_chat_kpis, _UNKNOWN

    class _Fail:
        async def execute(self, *a, **k):
            raise RuntimeError("db down")

    kpis = await _compute_chat_kpis(_Fail(), "b1")
    assert kpis["today"]["sales"] == _UNKNOWN
    assert kpis["today"]["profit"] == _UNKNOWN


@pytest.mark.asyncio
async def test_weekday_patterns_empty_without_data():
    """Patterns must be empty (not fabricated) when the ledger has no dates."""
    from app.routers.chat import _compute_weekday_patterns

    class _NoRows:
        async def execute(self, *a, **k):
            class _R:
                def fetchone(self):
                    # row exists but best_dow is NULL (no data)
                    class _Row:
                        best_dow = None
                        worst_dow = None
                        sat_wed_gap_pct = None
                    return _Row()
            return _R()

    patterns = await _compute_weekday_patterns(_NoRows(), "b1")
    assert patterns == {}, "patterns must not fabricate when no data exists"


@pytest.mark.asyncio
async def test_chat_alerts_zero_from_empty_ledger():
    """Without data, alerts must report 0 counts derived from SQL, not inventory facts."""
    from app.routers.chat import _compute_chat_alerts

    class _NoRows:
        async def execute(self, *a, **k):
            class _R:
                def fetchone(self):
                    return None
            return _R()

    alerts = await _compute_chat_alerts(_NoRows(), "b1")
    assert alerts == {"stockouts": 0, "low_stock": 0}


# Used by the parametrized test literal scan.
_APP_ROOT = APP_ROOT