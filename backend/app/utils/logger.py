"""Structured logging for NazmOS.

Outputs JSON to stdout so logs can be aggregated by Loki, Datadog, CloudWatch, or
similar. Automatically includes request/business correlation IDs when they are set
in the logging context.
"""
import logging
import re
import sys
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from app.config import get_settings
from app.utils.logging_context import get_request_id, get_business_id

settings = get_settings()

# Attributes that exist on every LogRecord and should not be double-logged.
_STANDARD_LOGRECORD_ATTRS = frozenset(
    [
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "getMessage",
        "message",
    ]
)

# Keys whose values must never be emitted in plain text logs.
_PII_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "secret",
        "secret_key",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "api_key",
        "api_secret",
        "credit_card",
        "card_number",
        "cvv",
        "iban",
        "phone",
        "phone_number",
        "email",
        "whatsapp_number",
        "address",
        "cr_number",
        "wasfaty_id",
        "credentials_encrypted",
        "credentials_version",
        "two_factor_secret",
    }
)

_REDACTED = "[REDACTED]"

# Loose patterns for PII that may appear in free-form strings.
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\b(?:\+?966|0)?5\d{8}\b")
_SAUSSI_ID_RE = re.compile(r"\b1\d{9}\b")


def _redact_scalar(value: Any) -> Any:
    """Replace a scalar value with a redaction marker."""
    if value is None:
        return None
    if isinstance(value, str):
        if len(value) <= 4:
            return _REDACTED
        return value[:2] + "***" + value[-2:]
    if isinstance(value, (bytes, bytearray)):
        return "[REDACTED_BYTES]"
    return _REDACTED


def _redact_string(value: str) -> str:
    """Redact PII patterns from free-form strings."""
    value = _EMAIL_RE.sub(_REDACTED, value)
    value = _PHONE_RE.sub(_REDACTED, value)
    value = _SAUSSI_ID_RE.sub(_REDACTED, value)
    return value


def redact_pii(data: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``data`` with known PII fields redacted."""
    if not isinstance(data, dict):
        if isinstance(data, str):
            return _redact_string(data)
        return data
    result: dict[str, Any] = {}
    for key, value in data.items():
        lower_key = key.lower()
        if lower_key in _PII_KEYS:
            result[key] = _REDACTED
        elif isinstance(value, dict):
            result[key] = redact_pii(value)
        elif isinstance(value, list):
            result[key] = [
                redact_pii(item) if isinstance(item, dict) else
                (_redact_string(item) if isinstance(item, str) else item)
                for item in value
            ]
        elif isinstance(value, str):
            result[key] = _redact_string(value)
        else:
            result[key] = value
    return result


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_string(message),
        }

        # Merge in any extra fields passed via `extra={...}`.
        for attr in dir(record):
            if attr.startswith("_") or attr in _STANDARD_LOGRECORD_ATTRS:
                continue
            value = getattr(record, attr)
            # Avoid serializing methods/objects accidentally.
            if callable(value):
                continue
            log_data[attr] = value

        # Always include correlation IDs from the async context if present.
        request_id = get_request_id()
        if request_id:
            log_data["request_id"] = request_id
        business_id = get_business_id()
        if business_id:
            log_data["business_id"] = business_id

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(redact_pii(log_data), default=str)


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

    return logger


def log_request(
    logger: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    response_time_ms: float,
    user_id: str | None = None,
    business_id: str | None = None,
) -> None:
    logger.info(
        f"{method} {path} - {status_code}",
        extra={
            "method": method,
            "path": path,
            "status_code": status_code,
            "response_time_ms": response_time_ms,
            "user_id": user_id,
            "business_id": business_id,
        },
    )


def log_slow_query(logger: logging.Logger, query: str, duration_ms: float) -> None:
    logger.warning(
        f"Slow query detected: {duration_ms}ms",
        extra={
            "query": query,
            "duration_ms": duration_ms,
        },
    )
