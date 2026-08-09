import json
import logging
from typing import AsyncGenerator
from app.config import get_settings
from app.utils.prompt_sanitizer import sanitize_user_input
from app.services.llm_rate_limiter import (
    llm_rate_limiter,
    LLMRateLimitExceeded,
    estimate_tokens,
)

settings = get_settings()

logger = logging.getLogger("llm_orchestrator")

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

CAPACITY_MESSAGE = "Baseer is at capacity right now, try again in a minute."


class LLMProviderUnavailable(Exception):
    """A real provider call failed at the transport/HTTP level (not rate limit)."""


def _safe_json(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value) if value else {}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        return {}


def _to_gemini_contents(messages) -> tuple[list[dict], str]:
    """Convert OpenAI-style messages into Gemini contents + system instruction text."""
    contents = []
    system_parts = []
    for m in messages or []:
        role = m.get("role")
        if role == "system":
            system_parts.append(m.get("content", ""))
            continue
        parts = []
        if m.get("content") and role != "tool":
            parts.append({"text": m["content"]})
        if role == "tool":
            name = m.get("name") or (m.get("tool_call_id") or "unknown")
            content = m.get("content") or "{}"
            try:
                parsed = json.loads(content)
            except Exception:
                parsed = {"result": content}
            parts.append({"functionResponse": {"name": name, "response": parsed}})
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            parts.append({"functionCall": {"name": fn.get("name"), "args": _safe_json(fn.get("arguments"))}})
        if not parts:
            continue
        gemini_role = "model" if role == "assistant" else "user"
        contents.append({"role": gemini_role, "parts": parts})
    return contents, "".join(system_parts)


def _to_gemini_tools(tools) -> list[dict]:
    declarations = []
    for t in tools or []:
        fn = t.get("function", {})
        declarations.append({
            "name": fn.get("name"),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters"),
        })
    return [{"functionDeclarations": declarations}]


def _from_gemini_response(data: dict) -> dict:
    """Normalize a Gemini generateContent response to the OpenAI chat shape."""
    choices = []
    candidates = data.get("candidates") or []
    if candidates:
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        tool_calls = []
        for i, p in enumerate(parts):
            fc = p.get("functionCall")
            if fc:
                tool_calls.append({
                    "id": f"call_gemini_{i}",
                    "type": "function",
                    "function": {"name": fc.get("name"), "arguments": json.dumps(fc.get("args", {}))},
                })
        message = {"role": "assistant", "content": text or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        choices.append({"message": message})
    usage = data.get("usageMetadata") or {}
    return {
        "choices": choices,
        "usage": {
            "prompt_tokens": usage.get("promptTokenCount"),
            "completion_tokens": usage.get("candidatesTokenCount"),
        },
    }


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
        self.use_mock = settings.USE_MOCK_LLM or not (settings.GROQ_API_KEY or settings.GOOGLE_AI_API_KEY)
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

    # --- provider plumbing -------------------------------------------------

    def _has_key(self, provider: str) -> bool:
        if provider == "groq":
            return bool(settings.GROQ_API_KEY)
        if provider == "google":
            return bool(settings.GOOGLE_AI_API_KEY)
        return False

    def _real_providers(self) -> list[str]:
        return [p for p in settings.provider_order if p in ("groq", "google")]

    async def _post_json(self, url: str, headers: dict, json_body: dict) -> dict:
        """POST JSON and return parsed body. Handles 429 (sets backoff_until)."""
        import asyncio
        import httpx
        from datetime import datetime, timedelta

        request_coro = httpx.AsyncClient().post(url, headers=headers, json=json_body)
        response = await asyncio.wait_for(request_coro, timeout=getattr(self, "timeout", 20))
        if getattr(response, "status_code", 200) == 429:
            retry_after = int(getattr(response, "headers", {}).get("Retry-After", 60))
            self.backoff_until = datetime.utcnow() + timedelta(seconds=retry_after)
            raise RuntimeError("rate_limited")
        if getattr(response, "status_code", 200) >= 400:
            raise RuntimeError(f"llm_http_error:{getattr(response, 'status_code', 'unknown')}")
        return response.json()

    async def _groq_chat(self, payload: dict) -> dict:
        """Call Groq's OpenAI-compatible chat/completions; returns OpenAI-shaped dict."""
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {**payload, "model": settings.GROQ_MODEL}
        return await self._post_json(GROQ_CHAT_URL, headers, body)

    async def _google_ai_chat(self, payload: dict) -> dict:
        """Call Google Gemini generateContent; normalizes response to OpenAI shape."""
        model = settings.GOOGLE_AI_MODEL
        url = f"{GEMINI_API_BASE}/{model}:generateContent?key={settings.GOOGLE_AI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        messages = payload.get("messages") or []
        contents, system = _to_gemini_contents(messages)
        body: dict = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if payload.get("tools"):
            body["tools"] = _to_gemini_tools(payload["tools"])
        body["generationConfig"] = {
            "temperature": payload.get("temperature", settings.LLM_TEMPERATURE),
            "maxOutputTokens": payload.get("max_tokens", settings.LLM_MAX_TOKENS),
        }
        data = await self._post_json(url, headers, body)
        return _from_gemini_response(data)

    # --- non-streaming (retained contract for recovery/chaos tests) --------

    async def generate_response(self, prompt: str, context: dict | None = None):
        """Non-streaming provider call with graceful failure + circuit breaker.

        Always attempts the real providers in LLM_PROVIDER_ORDER (this is the
        legacy contract exercised by the chaos/contract tests). Rate-limit
        pre-flight skips a provider; if every provider fails, returns None and
        marks the circuit breaker.
        """
        import asyncio
        import time

        self.total_requests += 1
        now_ts = time.time()
        if self.circuit_open:
            if self._circuit_opened_at and now_ts - self._circuit_opened_at >= self.recovery_timeout:
                self.circuit_half_open = True
                self.circuit_open = False
            else:
                return None

        payload = {
            "messages": [
                {"role": "system", "content": "You are NazmOS, a retail recovery assistant. Use only provided business context."},
                {"role": "user", "content": prompt},
            ],
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
        }
        if context:
            payload["messages"].insert(1, {"role": "system", "content": f"Context: {json.dumps(context, default=str)[:4000]}"})

        prompt_tokens = estimate_tokens(json.dumps(payload, default=str))

        for provider in self._real_providers():
            try:
                await llm_rate_limiter.consume(
                    provider,
                    prompt_tokens=prompt_tokens,
                    output_tokens=settings.LLM_MAX_TOKENS,
                )
            except LLMRateLimitExceeded as exc:
                self._log_rate_limit(provider, exc)
                continue
            try:
                if provider == "groq":
                    result = await self._groq_chat(payload)
                else:
                    result = await self._google_ai_chat(payload)
            except Exception:
                continue
            self.fallback_mode = False
            self.success_count += 1
            self.failure_count = 0
            if self.circuit_half_open and self.success_count >= self.success_threshold:
                self.circuit_half_open = False
                self.circuit_open = False
            return result

        self.fallback_mode = True
        self.failed_requests += 1
        self.failure_count += 1
        if self.failure_count >= getattr(self, "failure_threshold", 3):
            self.circuit_open = True
            self.circuit_half_open = True
            self._circuit_opened_at = time.time()
        return None

    @staticmethod
    def _log_rate_limit(provider: str, exc: LLMRateLimitExceeded) -> None:
        import logging
        logging.getLogger("llm_orchestrator").info(
            f"LLM rate limited on {provider}, skipping: {exc}"
        )

    # --- streaming (production chat path) ----------------------------------

    async def stream_response(
        self,
        message: str,
        system_prompt: str,
        db=None,
        business_id=None,
    ) -> AsyncGenerator[str, None]:
        if self.use_mock:
            async for chunk in self._mock_stream(message):
                yield chunk
            return

        for provider in self._real_providers():
            if not self._has_key(provider):
                continue
            try:
                async for chunk in self._provider_stream(provider, message, system_prompt, db, business_id):
                    yield chunk
                return
            except LLMRateLimitExceeded as exc:
                self._log_rate_limit(provider, exc)
                continue
            except LLMProviderUnavailable as exc:
                import logging
                logging.getLogger("llm_orchestrator").warning(
                    f"LLM provider {provider} unavailable: {exc}"
                )
                continue

        yield CAPACITY_MESSAGE

    async def _provider_stream(
        self,
        provider: str,
        message: str,
        system_prompt: str,
        db=None,
        business_id=None,
    ) -> AsyncGenerator[str, None]:
        from app.services.agent_tools import AGENT_TOOLS_SCHEMA, execute_agent_tool

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": sanitize_user_input(message)},
        ]
        payload = {
            "messages": messages,
            "tools": AGENT_TOOLS_SCHEMA,
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
        }

        result = await self._call_provider(provider, payload)
        choice = (result.get("choices") or [{}])[0]
        message_obj = choice.get("message") or {}
        tool_calls = message_obj.get("tool_calls") or []

        if tool_calls and db and business_id:
            messages.append(message_obj)
            for tool_call in tool_calls:
                func_name = tool_call.get("function", {}).get("name") or "unknown"
                raw_args = tool_call.get("function", {}).get("arguments") or "{}"
                func_args = _safe_json(raw_args)
                try:
                    tool_result = await execute_agent_tool(func_name, func_args, business_id, db)
                except Exception as exc:
                    logger.warning("agent tool execution failed", tool=func_name, error=str(exc))
                    tool_result = {"error": f"Tool '{func_name}' failed to execute"}
                messages.append({
                    "tool_call_id": tool_call.get("id"),
                    "role": "tool",
                    "name": func_name,
                    "content": json.dumps(tool_result, default=str),
                })
            follow_result = await self._call_provider(provider, {
                "messages": messages,
                "temperature": settings.LLM_TEMPERATURE,
                "max_tokens": settings.LLM_MAX_TOKENS,
            })
            choice = (follow_result.get("choices") or [{}])[0]
            message_obj = choice.get("message") or {}

        content = message_obj.get("content") or ""
        if not content and tool_calls:
            # The model produced only tool calls (no prose); stream a graceful
            # reply instead of a silent empty 200 response.
            content = "I checked your business data. What would you like to dig into next?"
        for char in content:
            yield char

    async def _call_provider(self, provider: str, payload: dict) -> dict:
        """Rate-limited single provider call; raises on transport/rate errors."""
        prompt_tokens = estimate_tokens(json.dumps(payload, default=str))
        await llm_rate_limiter.consume(
            provider,
            prompt_tokens=prompt_tokens,
            output_tokens=settings.LLM_MAX_TOKENS,
        )
        try:
            if provider == "groq":
                return await self._groq_chat(payload)
            return await self._google_ai_chat(payload)
        except RuntimeError as exc:
            if str(exc) == "rate_limited":
                raise LLMRateLimitExceeded(provider, "rpm", 0, 0)
            raise LLMProviderUnavailable(str(exc)) from exc
        except Exception as exc:
            raise LLMProviderUnavailable(str(exc)) from exc

    # --- mock streaming -----------------------------------------------------

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
