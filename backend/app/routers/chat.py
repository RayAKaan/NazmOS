from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from datetime import datetime
import json
import uuid
from typing import Optional

from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.database import get_db, User, ChatSession, ChatMessage
from app.services.llm_orchestrator import LLMOrchestrator
from app.services.context_builder import ContextBuilder
from app.services.prompt_engine import build_system_prompt, extract_decisions_from_response
from app.services.chat_memory import ChatMemoryService
from app.services.decision_engine import DecisionEngine
from app.services.cache_service import CacheService
from app.services.intelligence_api_client import IntelligenceAPIClient
from app.utils.prompt_sanitizer import sanitize_user_input
from app.config import get_settings
from app.services.feature_flags import require_feature_enabled

settings = get_settings()
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
llm_orchestrator = LLMOrchestrator()

_UNKNOWN = "unavailable"

KPI_QUERY = text("""
    WITH today_txns AS (
        SELECT
            COALESCE(SUM(t.quantity * t.unit_price), 0) AS sales,
            COALESCE(SUM(t.quantity * (t.unit_price - COALESCE(t.cost_price, i.cost_price, 0))), 0) AS profit,
            COUNT(*) AS transactions
        FROM transactions t
        LEFT JOIN items i ON i.id = t.item_id
        WHERE t.business_id = :b
          AND DATE(t.transaction_at) = CURRENT_DATE
          AND t.transaction_type = 'sale'
    ),
    inventory_val AS (
        SELECT COALESCE(SUM(inv.current_stock * i.cost_price), 0) AS stock_value
        FROM inventory inv
        JOIN items i ON i.id = inv.item_id
        WHERE i.business_id = :b
    )
    SELECT
        t.sales, t.profit, t.transactions,
        iv.stock_value
    FROM today_txns t, inventory_val iv
""")

WEEKDAY_QUERY = text("""
    WITH daily AS (
        SELECT
            DATE(transaction_at) AS day,
            EXTRACT(ISODOW FROM transaction_at) AS dow,
            SUM(quantity * unit_price) AS sales
        FROM transactions
        WHERE business_id = :b
          AND transaction_type = 'sale'
          AND transaction_at >= NOW() - INTERVAL '90 days'
        GROUP BY 1, 2
    ),
    by_dow AS (
        SELECT dow, AVG(sales) AS avg_sales
        FROM daily
        GROUP BY dow
    ),
    totals AS (
        SELECT
            MAX(avg_sales) AS best_avg,
            MIN(avg_sales) AS worst_avg,
            MAX(avg_sales) FILTER (WHERE dow = 6) AS sat_avg,
            MAX(avg_sales) FILTER (WHERE dow = 3) AS wed_avg
            -- dow 6 = Saturday, dow 3 = Wednesday in ISODOW
        FROM by_dow
    )
    SELECT
        (SELECT dow FROM by_dow ORDER BY avg_sales DESC LIMIT 1) AS best_dow,
        (SELECT dow FROM by_dow ORDER BY avg_sales ASC LIMIT 1) AS worst_dow,
        CASE WHEN sat_avg > 0 AND wed_avg > 0
             THEN ROUND(((sat_avg - wed_avg) / sat_avg * 100)::numeric, 1)
             ELSE NULL END AS sat_wed_gap_pct,
        (SELECT ARRAY_AGG(dow ORDER BY avg_sales DESC) FROM by_dow) AS dow_rank
    FROM totals
""")


DOW_LABELS = {
    1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday",
    5: "Friday", 6: "Saturday", 7: "Sunday",
}


async def _compute_chat_kpis(db: Any, business_id: str) -> dict:
    """Compute today's real KPIs from the ledger. Never fabricate."""
    try:
        res = await db.execute(KPI_QUERY, {"b": business_id})
        row = res.fetchone()
        if not row:
            return {"today": {"sales": _UNKNOWN, "profit": _UNKNOWN,
                              "transactions": _UNKNOWN},
                    "stock_value": _UNKNOWN}
        return {
            "today": {
                "sales": float(row.sales) if row.sales else _UNKNOWN,
                "profit": float(row.profit) if row.profit else _UNKNOWN,
                "transactions": int(row.transactions) if row.transactions else _UNKNOWN,
            },
            "stock_value": float(row.stock_value) if row.stock_value else _UNKNOWN,
        }
    except Exception:
        return {"today": {"sales": _UNKNOWN, "profit": _UNKNOWN,
                          "transactions": _UNKNOWN},
                "stock_value": _UNKNOWN}


async def _compute_weekday_patterns(db: Any, business_id: str) -> dict:
    """Compute real weekday patterns from the ledger. Returns UNKNOWN for
    insufficient data rather than fabricating patterns."""
    try:
        res = await db.execute(WEEKDAY_QUERY, {"b": business_id})
        row = res.fetchone()
        if not row or row.best_dow is None:
            return {}
        best = DOW_LABELS.get(int(row.best_dow), _UNKNOWN)
        worst = DOW_LABELS.get(int(row.worst_dow), _UNKNOWN)
        return {
            "best_day_of_week": best,
            "worst_day_of_week": worst,
            "sat_wed_gap_pct": float(row.sat_wed_gap_pct) if row.sat_wed_gap_pct is not None else _UNKNOWN,
        }
    except Exception:
        return {}


async def _compute_chat_alerts(db: Any, business_id: str) -> dict:
    """Compute real stock alerts for context_summary — no fabricated counts."""
    try:
        res = await db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE inv.current_stock = 0) AS stockout_count,
                COUNT(*) FILTER (WHERE inv.current_stock > 0
                    AND inv.current_stock < COALESCE(inv.reorder_point, 5)) AS low_stock_count
            FROM inventory inv
            JOIN items i ON i.id = inv.item_id
            WHERE i.business_id = :b
        """), {"b": business_id})
        row = res.fetchone()
        if not row:
            return {"stockouts": 0, "low_stock": 0}
        return {"stockouts": row.stockout_count or 0,
                "low_stock": row.low_stock_count or 0}
    except Exception:
        return {"stockouts": 0, "low_stock": 0}


class ChatReasonRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    context: dict = Field(default_factory=dict)


@router.post("/")
async def chat(
    message: str,
    session_id: Optional[str] = None,
    business_id: str = None,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    if business_id:
        await assert_business_access(db, business_id, current_user)
        await require_feature_enabled(db, "chat_enabled", business_id=business_id)

    clean_message = sanitize_user_input(message)

    if not session_id:
        session_id = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO chat_sessions (id, business_id, user_id, title, last_message_at)
                VALUES (:id, :business_id, :user_id, :title, NOW())
            """),
            {
                "id": session_id,
                "business_id": business_id,
                "user_id": str(current_user.id),
                "title": clean_message[:50],
            }
        )
        await db.commit()
    else:
        result = await db.execute(
            text("UPDATE chat_sessions SET last_message_at = NOW() "
                 "WHERE id = :id AND user_id = :uid RETURNING id"),
            {"id": session_id, "uid": str(current_user.id)}
        )
        if not result.fetchone():
            raise HTTPException(404, "Session not found")
        await db.commit()

    memory = ChatMemoryService(session_id)
    history = await memory.get_history()

    context_builder = ContextBuilder(business_id)

    # ── Deterministic KPIs: computed from the ledger, never fabricated ────
    kpis = await _compute_chat_kpis(db, business_id)
    patterns = await _compute_weekday_patterns(db, business_id)
    alerts = []
    top_items = []
    inventory_items = []
    dead_stock = []
    forecasts = {}

    context = await context_builder.build(
        db, kpis, alerts, top_items, inventory_items, dead_stock, forecasts, patterns
    )
    system_prompt = build_system_prompt(context, clean_message, history)

    async def event_stream():
        full_response = ""
        session_msg_id = str(uuid.uuid4())

        try:
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id, 'message_id': session_msg_id})}\n\n"

            async for chunk in llm_orchestrator.stream_response(
                clean_message, system_prompt, db=db, business_id=business_id
            ):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

            decisions = extract_decisions_from_response(full_response)
            await memory.add_message("user", clean_message)
            await memory.add_message("assistant", full_response)

            await db.execute(
                text("""
                    INSERT INTO chat_messages
                        (id, session_id, role, content, decisions, created_at)
                    VALUES (:id, :session_id, 'user', :content, '[]', NOW())
                """),
                {"id": str(uuid.uuid4()), "session_id": session_id, "content": clean_message}
            )
            await db.execute(
                text("""
                    INSERT INTO chat_messages
                        (id, session_id, role, content, decisions, created_at)
                    VALUES (:id, :session_id, 'assistant', :content, :decisions, NOW())
                """),
                {
                    "id": session_msg_id,
                    "session_id": session_id,
                    "content": full_response,
                    "decisions": json.dumps(decisions),
                }
            )
            await db.execute(
                text("""
                    UPDATE chat_sessions
                    SET message_count = message_count + 2, total_tokens = total_tokens + :tokens
                    WHERE id = :id
                """),
                {"id": session_id, "tokens": len(full_response) // 4}
            )
            await db.commit()

            yield f"data: {json.dumps({'type': 'done', 'decisions': decisions, 'message_id': session_msg_id})}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Something went wrong. Please try again.'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/sessions")
async def get_sessions(
    business_id: str,
    page: int = 1,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await require_feature_enabled(db, "chat_enabled", business_id=business_id)
    offset = (page - 1) * limit

    result = await db.execute(
        text("""
            SELECT id, title, message_count, last_message_at, created_at
            FROM chat_sessions
            WHERE business_id = :business_id AND is_archived = false
            ORDER BY last_message_at DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """),
        {"business_id": business_id, "limit": limit, "offset": offset}
    )
    sessions = result.fetchall()

    return {
        "sessions": [
            {
                "id": str(s.id),
                "title": s.title or "New Conversation",
                "message_count": s.message_count,
                "last_message_at": s.last_message_at.isoformat() if s.last_message_at else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sessions
        ],
        "page": page,
        "limit": limit,
    }


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    ownership = await db.execute(
        text("SELECT id FROM chat_sessions WHERE id = :sid AND user_id = :uid"),
        {"sid": session_id, "uid": str(current_user.id)}
    )
    if not ownership.fetchone():
        raise HTTPException(404, "Session not found")

    result = await db.execute(
        text("""
            SELECT id, role, content, decisions, created_at
            FROM chat_messages
            WHERE session_id = :session_id
            ORDER BY created_at ASC
        """),
        {"session_id": session_id}
    )
    messages = result.fetchall()

    return {
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "decisions": json.loads(m.decisions) if m.decisions else [],
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]
    }


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await db.execute(
        text("UPDATE chat_sessions SET is_archived = true WHERE id = :id AND user_id = :uid RETURNING id"),
        {"id": session_id, "uid": str(current_user.id)}
    )
    if not result.fetchone():
        raise HTTPException(404, "Session not found")
    await db.commit()
    return {"status": "archived"}


@router.get("/suggestions")
async def get_suggestions(
    business_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await require_feature_enabled(db, "chat_enabled", business_id=business_id)
    alerts = await _compute_chat_alerts(db, business_id)
    suggestions = [
        "What should I order urgently right now?",
        "Which items are trending up this week?",
        "What's my stock value tied up in slow-moving items?",
        "Forecast my sales for next week",
        "Give me a full action plan to improve margins",
        "Which items have the worst sell-through rate?",
    ]

    return {
        "suggestions": suggestions,
        "context_summary": f"{alerts['stockouts']} critical stockouts, "
                           f"{alerts['low_stock']} low-stock items",
    }


@router.post("/reason")
async def chat_reason(
    business_id: str,
    request: ChatReasonRequest,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Phase 7: structured reasoning endpoint for the chat assistant.

    Returns a natural-language answer, a decision, and an optional plan from the
    Unified Intelligence API. This lets the chat layer consume the same
    intelligence surface as the rest of NazmOS.
    """
    await require_feature_enabled(db, "chat_enabled", business_id=business_id)
    clean_message = sanitize_user_input(request.message)
    client = IntelligenceAPIClient(db, business_id)
    result = await client.reason(question=clean_message, context=request.context)
    await db.commit()
    return {
        "answer": result["answer"],
        "decision": result["decision"].ranked_action if result.get("decision") else None,
        "plan": {"goal": result["plan"].goal, "steps": result["plan"].steps} if result.get("plan") else None,
        "sources": result.get("sources", []),
    }
