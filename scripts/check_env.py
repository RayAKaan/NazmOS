#!/usr/bin/env python3
"""Pre-flight environment validation for NazmOS deployments.

Run this before `docker compose up` or before promoting an environment. It fails
closed on dangerous configurations rather than letting the app start silently in
an unsafe mode.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings


def _fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)


def _warn(message: str) -> None:
    print(f"WARN: {message}", file=sys.stderr)


def _ok(message: str) -> None:
    print(f"OK:   {message}")


def main() -> int:
    settings = get_settings()
    exit_code = 0

    if settings.ENVIRONMENT == "production":
        if settings.SECRET_KEY == "dev-secret-key-change-in-production-minimum-32-chars":
            _fail("SECRET_KEY is still the dev default in production")
            exit_code = 1
        elif len(settings.SECRET_KEY) < 32:
            _fail("SECRET_KEY must be >= 32 characters in production")
            exit_code = 1
        else:
            _ok("SECRET_KEY is not the dev default")

        if settings.DATABASE_URL.startswith("sqlite"):
            _fail("SQLite cannot be used in production")
            exit_code = 1
        else:
            _ok("Database URL points to PostgreSQL")

        if settings.USE_MOCK_LLM:
            _warn("USE_MOCK_LLM=true in production — merchant LLM responses are canned")
        else:
            _ok("Mock LLM is disabled in production")

        if not settings.SENTRY_DSN:
            _warn("SENTRY_DSN is not set — uncaught exceptions will not be aggregated")
        else:
            _ok("Sentry DSN is configured")

        if not settings.CORS_ORIGINS or "localhost" in settings.CORS_ORIGINS:
            _warn("CORS_ORIGINS may include localhost in production")
        else:
            _ok("CORS_ORIGINS does not include localhost")

        if not re.match(r"^https?://", settings.OPENROUTER_BASE_URL or ""):
            _warn("OPENROUTER_BASE_URL does not look like a valid URL")
        else:
            _ok("OpenRouter base URL is set")

    else:
        _ok(f"Environment is {settings.ENVIRONMENT}; production-only checks skipped")

    print("Environment check complete.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
