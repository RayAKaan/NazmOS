from pydantic import BaseModel
from datetime import datetime
from typing import Any


class ErrorResponse(BaseModel):
    error: bool = True
    code: str
    message: str
    detail: Any | None = None
    timestamp: datetime = datetime.utcnow()


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: datetime
    checks: dict | None = None
    environment: str | None = None
