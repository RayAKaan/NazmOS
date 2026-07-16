from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.utils.logger import setup_logger, log_request
import time

logger = setup_logger("api")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        response = await call_next(request)
        
        process_time = (time.time() - start_time) * 1000
        
        log_request(
            logger,
            request.method,
            request.url.path,
            response.status_code,
            process_time,
        )
        
        response.headers["X-Process-Time"] = str(process_time)
        return response
