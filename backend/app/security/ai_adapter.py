"""AI transports: the only ways a capsule-backed prompt leaves the process.

All transports share one contract -- ``complete(system_prompt, user_prompt)
-> str`` -- and all enforce the outbound DLP scan on the prompts they send and
an inbound DLP scan on the responses they return. Responses are un-trusted until
the output gate validates them.

opencode_brain.py decides which transport to use; this module only supplies
transport implementations plus a factory based on settings.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
from typing import Awaitable, Callable

import httpx

from app.security.ai_policy import CircuitBreaker
from app.security.dlp import DLP_RULES, DlpScanner, DLPViolationError
from app.security.master_prompt import AGENT_DENIED_PERMISSIONS, FULL_SYSTEM_PROMPT

logger = logging.getLogger("ai_adapter")


class AITransportError(Exception):
    """Transport-level failure (timeout, unavailable, DLP block, HTTP error)."""


def _guard_outbound(system_prompt: str, user_prompt: str) -> None:
    scanner = DlpScanner(rules=list(DLP_RULES), strict=True)
    scanner.assert_clean(system_prompt, context="outbound_system")
    scanner.assert_clean(user_prompt, context="outbound_user")


class LLMTransport:
    """Wraps an existing async LLM callable (e.g. LLMOrchestrator chat_completion)."""

    def __init__(
        self,
        llm_caller: Callable[[str, str], Awaitable[str | None]],
        *,
        timeout_seconds: float = 45,
        breaker: CircuitBreaker | None = None,
    ):
        self._caller = llm_caller
        self._timeout = timeout_seconds
        self._breaker = breaker or CircuitBreaker()

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        if self._breaker.is_open:
            raise AITransportError("circuit_open")
        _guard_outbound(system_prompt, user_prompt)
        try:
            response = await asyncio.wait_for(
                self._caller(system_prompt, user_prompt),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            self._breaker.record_failure()
            raise AITransportError("llm_timeout") from exc
        except Exception as exc:
            self._breaker.record_failure()
            raise AITransportError(f"llm_call_failed:{type(exc).__name__}") from exc
        if response is None or not response.strip():
            self._breaker.record_failure()
            raise AITransportError("llm_empty_response")
        try:
            DlpScanner(rules=list(DLP_RULES), strict=True).assert_clean(
                response, context="inbound_response"
            )
        except DLPViolationError as exc:
            self._breaker.record_failure()
            raise AITransportError(f"dlp_inbound:{exc}") from exc
        self._breaker.record_success()
        return response


class OpenCodeSubprocessTransport:
    """Hardened in-process subprocess transport for the local OpenCode CLI.

    Hardening applied regardless of environment:
      - no shell=True (argv is a list)
      - isolated temp working directory
      - minimal environment allowlist (PATH/HOME + explicitly allowed keys)
      - strict timeout with process kill on expiry
    """

    ALLOWED_BASIC_ENV = ("PATH", "HOME", "USERPROFILE", "SystemRoot", "TEMP", "TMP", "NODE_ENV")

    def __init__(
        self,
        *,
        timeout_seconds: float = 30,
        binary_path: str | None = None,
        model: str = "",
        max_chars: int = 200_000,
        allow_additional_env: tuple[str, ...] = (),
        breaker: CircuitBreaker | None = None,
    ):
        self._timeout = timeout_seconds
        self._binary_path = binary_path or find_opencode_bin()
        self._model = model
        self._max_chars = max_chars
        self._allow_extra = tuple(allow_additional_env)
        self._breaker = breaker or CircuitBreaker()

    def is_available(self) -> bool:
        return self._binary_path is not None

    def _build_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in self.ALLOWED_BASIC_ENV:
            if os.getenv(key):
                env[key] = os.getenv(key, "")
        for key in self._allow_extra:
            if os.getenv(key):
                env[key] = os.getenv(key, "")
        # Provider key for the requested model only, and only when the caller
        # opted in via allow_additional_env.
        return env

    @staticmethod
    def _render_agent(system_prompt: str) -> str:
        """Render an OpenCode agent .md whose body is the system prompt and whose
        tool permissions are all denied (pure reasoning). This is how the master
        prompt is delivered as a genuine system role — never concatenated into
        the user message."""
        lines = [
            "---",
            "description: NazmOS isolated reasoning engine (system role)",
            "mode: primary",
            "permission:",
        ]
        for key, value in AGENT_DENIED_PERMISSIONS.items():
            lines.append(f"  {key}: {value}")
        lines.append("---")
        lines.append("")
        lines.append(system_prompt)
        return "\n".join(lines)

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        if self._breaker.is_open:
            raise AITransportError("circuit_open")
        if not self.is_available():
            raise AITransportError("opencode_not_found")

        _guard_outbound(system_prompt, user_prompt)

        cmd = [self._binary_path, "run", "--format", "json", "--pure"]
        if self._model:
            cmd.extend(["--model", self._model])
        cmd.extend(["--agent", "nazmos-brain", user_prompt])

        workdir = tempfile.mkdtemp(prefix="nazmos-brain-")
        # Per-project agent dir (opencode resolves `--agent nazmos-brain` from
        # <cwd>/.opencode/agents/ -- project-scoped, no global config mutation).
        agents_dir = os.path.join(workdir, ".opencode", "agents")
        os.makedirs(agents_dir, exist_ok=True)
        agent_path = os.path.join(agents_dir, "nazmos-brain.md")
        with open(agent_path, "w", encoding="utf-8") as fh:
            fh.write(self._render_agent(system_prompt))
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_env(),
                cwd=workdir,
            )
        except Exception as exc:
            self._breaker.record_failure()
            raise AITransportError(f"opencode_spawn_failed:{type(exc).__name__}") from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError as exc:
            try:
                proc.kill()
            except Exception:
                pass
            self._breaker.record_failure()
            raise AITransportError("opencode_timeout") from exc
        finally:
            try:
                shutil.rmtree(workdir, ignore_errors=True)
            except Exception:
                pass

        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

        if proc.returncode != 0:
            self._breaker.record_failure()
            raise AITransportError(f"opencode_nonzero:{proc.returncode} {stderr[:200]}")

        if len(stdout) > self._max_chars:
            self._breaker.record_failure()
            raise AITransportError("opencode_output_too_large")

        try:
            DlpScanner(rules=list(DLP_RULES), strict=True).assert_clean(
                stdout, context="inbound_response"
            )
        except DLPViolationError as exc:
            self._breaker.record_failure()
            raise AITransportError(f"dlp_inbound:{type(exc).__name__}") from exc

        self._breaker.record_success()
        return stdout


class OpenCodeRunnerClient:
    """HTTP client for the dedicated ``opencode_runner`` sidecar container.

    The runner owns a hardened, isolated OpenCode subprocess (read-only rootfs,
    dropped capabilities, no merchant mounts, no database access). This client
    only posts the capsule-shaped prompts and returns the stdout text.
    """

    def __init__(self, url: str, *, timeout_seconds: float = 45):
        self._url = url.rstrip("/")
        self._timeout = timeout_seconds
        self._breaker = CircuitBreaker()

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        _guard_outbound(system_prompt, user_prompt)
        payload = {
            "master_system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "timeout_seconds": min(float(self._timeout), 60),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout + 5) as client:
                response = await client.post(f"{self._url}/run", json=payload)
        except Exception as exc:
            raise AITransportError("runner_http_failed") from exc
        if response.status_code != 200:
            raise AITransportError(f"runner_http:{response.status_code}")
        try:
            data = response.json()
        except Exception as exc:
            raise AITransportError("runner_invalid_json") from exc
        if data.get("status") not in (None, "ok"):
            reason = str(data.get("reason", "unknown"))[:200]
            self._breaker.record_failure()
            raise AITransportError(f"runner_rejected:{reason}")
        output = data.get("output")
        if not isinstance(output, str) or not output.strip():
            raise AITransportError("runner_empty_output")
        try:
            DlpScanner(rules=list(DLP_RULES), strict=True).assert_clean(
                output, context="inbound_response"
            )
        except DLPViolationError as exc:
            raise AITransportError(f"dlp_inbound:{type(exc).__name__}") from exc
        return output


def find_opencode_bin() -> str | None:
    """Locate the opencode executable (config path -> PATH -> npm global)."""
    explicit = os.getenv("NAZMOS_OPENCODE_BIN", "")
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
    found = shutil.which("opencode")
    if found:
        return found
    npm_global = os.path.expandvars(r"%APPDATA%\npm\opencode.cmd")
    if os.path.isfile(npm_global):
        return npm_global
    return None


def default_transport(settings: object | None = None) -> OpenCodeSubprocessTransport | OpenCodeRunnerClient:
    """Factory: use the isolated runner container when configured, else the
    hardened in-process subprocess transport."""
    runner_url = getattr(settings, "OPENCODE_RUNNER_URL", "") or os.getenv("OPENCODE_RUNNER_URL", "")
    if runner_url:
        return OpenCodeRunnerClient(runner_url)
    return OpenCodeSubprocessTransport(
        timeout_seconds=float(getattr(settings, "OPENCODE_TIMEOUT_SECONDS", 30) if settings else 30),
        model=os.getenv("NAZMOS_OPENCODE_MODEL", ""),
    )