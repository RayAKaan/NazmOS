import json
from typing import List, Optional
from app.services.cache_service import CacheService


class ChatMemoryService:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.key = f"chat_history:{session_id}"
        self.ttl = 7200

    async def get_history(self) -> List[dict]:
        cached = await CacheService.get(self.key)
        if cached:
            return cached
        return []

    async def add_message(self, role: str, content: str):
        history = await self.get_history()
        history.append({"role": role, "content": content, "timestamp": str(hash(content))})
        
        if len(history) > 16:
            history = history[-16:]
        
        await CacheService.set(self.key, history, self.ttl)

    async def clear(self):
        await CacheService.delete(self.key)

    async def get_context_summary(self) -> str:
        history = await self.get_history()
        if not history:
            return "No prior conversation."
        
        return "\n".join([
            f"{'Owner' if m['role'] == 'user' else 'Baseer'}: {m['content'][:200]}"
            for m in history[-6:]
        ])


class ChatMemory:
    """Compatibility in-memory chat memory for resilience tests."""
    _messages: list[dict] = []

    async def add_message(self, user_id, session_id, role: str, content: str, metadata: dict | None = None):
        self._messages.append({
            "user_id": str(user_id),
            "session_id": str(session_id),
            "role": role,
            "content": content,
            "metadata": metadata or {},
        })
        return True

    async def get_recent_messages(self, user_id, session_id, limit: int = 10):
        return [m for m in self._messages if m["user_id"] == str(user_id) and m["session_id"] == str(session_id)][-limit:]
