import json
from typing import AsyncGenerator
from app.config import get_settings
from app.utils.prompt_sanitizer import sanitize_user_input

settings = get_settings()


MOCK_RESPONSES = {
    "restock": """📦 **Weekly Restock Plan**

Based on your current inventory data, here are the items you need to order immediately:

**URGENT - Order Today:**
- **Almarai Fresh Milk 1L**: Only 18 cartons left, selling 9/day = **2 days remaining**
  → Order: 135 cartons (1,012 SAR estimated cost)
  
- **Nova Water 330ml x24**: Only 24 packs left, selling 12/day = **2 days remaining**
  → Order: 180 packs (1,440 SAR estimated cost)

- **Lusine White Bread**: Only 8 packs left, selling 6/day = **1.3 days remaining**
  → Order: 100 packs (500 SAR estimated cost)

**Order This Week:**
- Almarai Laban 1L: 3.4 days remaining
- Nadec Milk 1L: 4.2 days remaining
- Lay's Classic Salted: 4.5 days remaining

💡 **Total urgent order value: 2,952 SAR**

📅 Place order by tomorrow morning to avoid stockouts.

```decisions
[
  {"action": "RESTOCK", "item_id": null, "item_name": "Almarai Fresh Milk 1L", "quantity": 135, "unit": "cartons", "by_when": "ASAP", "reason": "Critical - 2 days stock remaining", "estimated_value": 1012, "confidence": 0.95, "priority": 1},
  {"action": "RESTOCK", "item_id": null, "item_name": "Nova Water 330ml x24", "quantity": 180, "unit": "packs", "by_when": "ASAP", "reason": "Critical - 2 days stock remaining", "estimated_value": 1440, "confidence": 0.95, "priority": 1},
  {"action": "RESTOCK", "item_id": null, "item_name": "Lusine White Bread", "quantity": 100, "unit": "packs", "by_when": "tomorrow", "reason": "Critical - 1.3 days stock remaining", "estimated_value": 500, "confidence": 0.92, "priority": 1}
]
```""",
    "recovery_match": """🔁 **Recovery Match Preview**

NazmOS found healthy surplus stock that could potentially be recovered through nearby opted-in stores.

**Example:**
- Coffee Beans 250g: 40 surplus bags
- Estimated recovery: 1,440 SAR
- Rule: same city, healthy shelf life, both sides approve before contact reveal

💡 **Action:** Review Recovery Match preview and keep inventory updated so NazmOS can identify real matches.

```decisions
[
  {"action": "REVIEW", "item_id": null, "item_name": "Recovery Match Preview", "quantity": 1, "unit": "system", "by_when": "this_week", "reason": "Healthy surplus stock may be recoverable through nearby store matching", "estimated_value": 1440, "confidence": 0.82, "priority": 2}
]
```""",
    "whatsapp": """💬 **WhatsApp Retail Assistant Preview**

**Customer Query Simulated (Najdi Dialect):**
*"يا هلا والله، بكم قهوة V60 البن الإثيوبي؟ وهل توصلون لحَي الملقا بالرياض؟"*

**NazmOS Reply Generated:**
*"يا هلا بك وأبراك الساعات! ☕ قهوة V60 البن الإثيوبي الفاخر عندنا بـ 22 ريال. ونعم نوصل لحَي الملقا خلال 25 دقيقة."*

💡 **Action:** Keep prices and stock updated so assistant replies remain accurate.

```decisions
[]
```""",
    "dead_stock": """💀 **Dead Stock Analysis**

Your inventory has items that are not moving. Start with controlled discounts or bundles before writing them off.

💡 **Immediate action:** Review the Money Audit page and approve one recovery action.

```decisions
[
  {"action": "DISCOUNT", "item_id": null, "item_name": "Slow Moving Stock", "quantity": 1, "unit": "batch", "by_when": "this_week", "reason": "Capital tied up in slow-moving items", "estimated_value": 500, "confidence": 0.80, "priority": 2}
]
```""",
}


class LLMOrchestrator:
    def __init__(self):
        self.use_mock = settings.USE_MOCK_LLM or not settings.OPENROUTER_API_KEY
        self.fallback_mode = False
        self.backoff_until = None
        self.total_requests = 0
        self.failed_requests = 0
        self.failure_count = 0
        self.failure_threshold = 3
        self.success_count = 0
        self.success_threshold = 2
        self.recovery_timeout = 30
        self.circuit_open = False
        self.circuit_half_open = False
        self._circuit_opened_at = None

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        if settings.OPENROUTER_SITE_URL:
            headers["HTTP-Referer"] = settings.OPENROUTER_SITE_URL
        if settings.OPENROUTER_APP_NAME:
            headers["X-Title"] = settings.OPENROUTER_APP_NAME
        return headers

    def _chat_url(self) -> str:
        return settings.OPENROUTER_BASE_URL.rstrip("/") + "/chat/completions"

    async def generate_response(self, prompt: str, context: dict | None = None):
        """Non-streaming OpenRouter-compatible API with graceful failure behavior."""
        import asyncio
        from datetime import datetime, timedelta
        import httpx
        import time

        self.total_requests += 1
        now_ts = time.time()
        if self.circuit_open:
            if self._circuit_opened_at and now_ts - self._circuit_opened_at >= self.recovery_timeout:
                self.circuit_half_open = True
                self.circuit_open = False
            else:
                return None

        request_coro = None
        try:
            payload = {
                "model": settings.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "You are NazmOS, a retail recovery assistant. Use only provided business context."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": settings.LLM_TEMPERATURE,
                "max_tokens": settings.LLM_MAX_TOKENS,
            }
            if context:
                payload["messages"].insert(1, {"role": "system", "content": f"Context: {json.dumps(context, default=str)[:4000]}"})

            request_coro = httpx.AsyncClient().post(self._chat_url(), headers=self._headers(), json=payload)
            response = await asyncio.wait_for(request_coro, timeout=getattr(self, "timeout", 20))
            if getattr(response, "status_code", 200) == 429:
                retry_after = int(getattr(response, "headers", {}).get("Retry-After", 60))
                self.backoff_until = datetime.utcnow() + timedelta(seconds=retry_after)
                raise RuntimeError("rate_limited")
            if getattr(response, "status_code", 200) >= 400:
                raise RuntimeError(f"llm_http_error:{getattr(response, 'status_code', 'unknown')}")

            result = response.json()
            self.fallback_mode = False
            self.success_count += 1
            self.failure_count = 0
            if self.circuit_half_open and self.success_count >= self.success_threshold:
                self.circuit_half_open = False
                self.circuit_open = False
            return result
        except Exception:
            if request_coro is not None and hasattr(request_coro, "close"):
                try:
                    request_coro.close()
                except Exception:
                    pass
            self.fallback_mode = True
            self.failed_requests += 1
            self.failure_count += 1
            if self.failure_count >= getattr(self, "failure_threshold", 3):
                self.circuit_open = True
                self.circuit_half_open = True
                self._circuit_opened_at = time.time()
            return None

    async def stream_response(self, message: str, system_prompt: str) -> AsyncGenerator[str, None]:
        if self.use_mock:
            async for chunk in self._mock_stream(message):
                yield chunk
        else:
            async for chunk in self._openrouter_stream(message, system_prompt):
                yield chunk

    async def _mock_stream(self, message: str) -> AsyncGenerator[str, None]:
        message_lower = message.lower()
        response = None
        if any(w in message_lower for w in ["match", "recovery match", "surplus", "nearby", "dead stock", "مخزون", "مطابقة"]):
            response = MOCK_RESPONSES.get("recovery_match")
        elif any(w in message_lower for w in ["whatsapp", "واتساب", "order", "طلب", "قهوة", "بكم", "توصيل", "سعر", "chat"]):
            response = MOCK_RESPONSES.get("whatsapp")
        else:
            for key, resp in MOCK_RESPONSES.items():
                if key in message_lower:
                    response = resp
                    break
        if not response:
            response = """Hello — I am NazmOS, your retail recovery assistant.

I can help with:

📦 Restock planning
💀 Dead stock recovery
🔁 Recovery Match preview
📊 Money Audit actions

```decisions
[]
```"""

        for char in response:
            yield char
            import asyncio
            await asyncio.sleep(0.015)

    async def _openrouter_stream(self, message: str, system_prompt: str, db=None, business_id=None) -> AsyncGenerator[str, None]:
        import httpx
        from app.services.agent_tools import AGENT_TOOLS_SCHEMA, execute_agent_tool

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": sanitize_user_input(message)},
        ]
        payload = {
            "model": settings.LLM_MODEL,
            "messages": messages,
            "tools": AGENT_TOOLS_SCHEMA,
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(self._chat_url(), headers=self._headers(), json=payload)
                response.raise_for_status()
                result = response.json()
                choice = (result.get("choices") or [{}])[0]
                message_obj = choice.get("message") or {}
                tool_calls = message_obj.get("tool_calls") or []

                if tool_calls and db and business_id:
                    messages.append(message_obj)
                    for tool_call in tool_calls:
                        func_name = tool_call.get("function", {}).get("name")
                        raw_args = tool_call.get("function", {}).get("arguments") or "{}"
                        func_args = json.loads(raw_args)
                        tool_result = await execute_agent_tool(func_name, func_args, business_id, db)
                        messages.append({
                            "tool_call_id": tool_call.get("id"),
                            "role": "tool",
                            "name": func_name,
                            "content": json.dumps(tool_result),
                        })
                    response = await client.post(self._chat_url(), headers=self._headers(), json={
                        "model": settings.LLM_MODEL,
                        "messages": messages,
                        "temperature": settings.LLM_TEMPERATURE,
                        "max_tokens": settings.LLM_MAX_TOKENS,
                    })
                    response.raise_for_status()
                    result = response.json()
                    choice = (result.get("choices") or [{}])[0]
                    message_obj = choice.get("message") or {}

                content = message_obj.get("content") or ""
                for char in content:
                    yield char
        except Exception as exc:
            self.fallback_mode = True
            yield f"I could not reach the model router. NazmOS can continue with rule-based recovery actions. ({type(exc).__name__})"
