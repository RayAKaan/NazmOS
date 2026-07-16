#!/usr/bin/env python3
"""Validate a NazmOS environment file before deployment."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

REQUIRED = ["ENVIRONMENT", "DATABASE_URL", "REDIS_URL", "SECRET_KEY", "CORS_ORIGINS", "UPLOAD_DIR", "OPENROUTER_BASE_URL", "LLM_MODEL"]
DANGEROUS_SECRET_PARTS = ["dev-secret", "CHANGE_ME", "minimum-32", "password"]


def parse_env(path: Path) -> dict[str, str]:
    data = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backend/.env.production.example")
    if not path.exists():
        raise SystemExit(f"Missing env file: {path}")
    env = parse_env(path)
    errors = []
    for key in REQUIRED:
        if not env.get(key):
            errors.append(f"Missing required key: {key}")
    secret = env.get("SECRET_KEY", "")
    if env.get("ENVIRONMENT") == "production":
        if len(secret) < 32:
            errors.append("SECRET_KEY must be at least 32 characters")
        if any(part in secret for part in DANGEROUS_SECRET_PARTS):
            errors.append("SECRET_KEY still looks like a placeholder/dev value")
    if env.get("USE_MOCK_LLM", "true").lower() == "false" and not env.get("OPENROUTER_API_KEY"):
        errors.append("OPENROUTER_API_KEY is required when USE_MOCK_LLM=false")
    if env.get("USE_MOCK_LLM", "true").lower() == "false" and "CHANGE_ME" in env.get("OPENROUTER_API_KEY", ""):
        errors.append("OPENROUTER_API_KEY still looks like a placeholder")
    for key in ["DATABASE_URL", "REDIS_URL", "OPENROUTER_BASE_URL"]:
        value = env.get(key, "")
        if value:
            parsed = urlparse(value)
            if not parsed.scheme:
                errors.append(f"{key} is not a valid URL")
    if errors:
        print("Environment validation FAILED:")
        for error in errors:
            print("-", error)
        raise SystemExit(1)
    print(f"Environment validation OK: {path}")


if __name__ == "__main__":
    main()
