from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import time

from app.utils.logger import setup_logger, log_request
from app.utils.logging_context import (
    set_request_id,
    set_business_id,
    generate_request_id,
)

logger = setup_logger("api")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or generate_request_id()
        request.state.request_id = request_id
        set_request_id(request_id)

        # Best-effort business_id extraction from query path or form/json body.
        business_id = request.query_params.get("business_id") or request.path_params.get("business_id")
        if not business_id and request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.body()
                if body:
                    import json
                    payload = json.loads(body)
                    if isinstance(payload, dict):
                        business_id = payload.get("business_id")
            except Exception:
                business_id = None
        if business_id:
            set_business_id(str(business_id))

        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception as exc:
            process_time = (time.time() - start_time) * 1000
            logger.error(
                f"Unhandled error in {request.method} {request.url.path}",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "response_time_ms": process_time,
                    "error": str(exc),
                },
            )
            raise

        process_time = (time.time() - start_time) * 1000

        user_id = None
        if hasattr(request.state, "user") and request.state.user:
            user_id = str(request.state.user.id)

        log_request(
            logger,
            request.method,
            request.url.path,
            response.status_code,
            process_time,
            user_id=user_id,
            business_id=business_id,
        )

        response.headers["X-Process-Time"] = str(process_time)
        response.headers["X-Request-ID"] = request_id
        return response
