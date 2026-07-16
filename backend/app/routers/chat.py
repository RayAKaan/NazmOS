from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from datetime import datetime
import json
import uuid
from typing import Optional

from app.middleware.auth_middleware import get_current_user
from app.database import get_db, User, ChatSession, ChatMessage
from app.services.llm_orchestrator import LLMOrchestrator
from app.services.context_builder import ContextBuilder
from app.services.prompt_engine import build_system_prompt, extract_decisions_from_response
from app.services.chat_memory import ChatMemoryService
from app.services.decision_engine import DecisionEngine
from app.services.cache_service import CacheService
from app.utils.prompt_sanitizer import sanitize_user_input
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
llm_orchestrator = LLMOrchestrator()


@router.post("/")
async def chat(
    message: str,
    session_id: Optional[str] = None,
    business_id: str = None,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
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
        await db.execute(
            text("UPDATE chat_sessions SET last_message_at = NOW() WHERE id = :id"),
            {"id": session_id}
        )
        await db.commit()

    memory = ChatMemoryService(session_id)
    history = await memory.get_history()

    context_builder = ContextBuilder(business_id)
    kpis = {"today": {"sales": 18450, "profit": 3200, "transactions": 145}}
    alerts = []
    top_items = []
    inventory_items = []
    dead_stock = []
    forecasts = {}
    patterns = {
        "best_day_of_week": "Saturday",
        "worst_day_of_week": "Wednesday",
        "wednesday_dip_pct": 31,
        "weekend_uplift_pct": 38,
    }
    
    context = await context_builder.build(
        db, kpis, alerts, top_items, inventory_items, dead_stock, forecasts, patterns
    )
    system_prompt = build_system_prompt(context, clean_message, history)

    async def event_stream():
        full_response = ""
        session_msg_id = str(uuid.uuid4())

        try:
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id, 'message_id': session_msg_id})}\n\n"

            async for chunk in llm_orchestrator.stream_response(clean_message, system_prompt):
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
    suggestions = [
        "What should I order urgently right now?",
        "Why do Wednesday sales always dip by 31%?",
        "What's my stock value tied up in dead items?",
        "Forecast my weekend sales this Saturday and Sunday",
        "Which items are trending up this week?",
        "Give me a full action plan to improve margins",
    ]

    return {
        "suggestions": suggestions,
        "context_summary": "3 critical stockouts, 4 dead stock items, weekend in 2 days",
    }
