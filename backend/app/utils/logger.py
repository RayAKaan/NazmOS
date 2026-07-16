import logging
import sys
import json
from datetime import datetime
from typing import Any
from app.config import get_settings

settings = get_settings()


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    
    return logger


def log_request(logger: logging.Logger, method: str, path: str, status_code: int, response_time_ms: float, user_id: str | None = None):
    logger.info(
        f"{method} {path} - {status_code}",
        extra={
            "method": method,
            "path": path,
            "status_code": status_code,
            "response_time_ms": response_time_ms,
            "user_id": user_id,
        }
    )


def log_slow_query(logger: logging.Logger, query: str, duration_ms: float):
    logger.warning(
        f"Slow query detected: {duration_ms}ms",
        extra={
            "query": query,
            "duration_ms": duration_ms,
        }
    )
