from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import os


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds comprehensive security headers to all responses.
    
    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: max-age=31536000
    - Content-Security-Policy
    - Referrer-Policy
    - Permissions-Policy
    - X-Request-ID (for tracing)
    """
    
    CSP_DIRECTIVE = "; ".join([
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data: https: blob:",
        "media-src 'self' data: blob:",
        "connect-src 'self' https://api.groq.com https://generativelanguage.googleapis.com https://api.stripe.com",
        "frame-src 'none'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "upgrade-insecure-requests",
    ])
    

    @staticmethod
    def set_default_headers(response: Response) -> Response:
        """Compatibility helper used by tests and simple ASGI wrappers."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @staticmethod
    def add_custom_headers(response: Response, headers: dict) -> Response:
        for key, value in (headers or {}).items():
            response.headers[str(key)] = str(value)
        return response

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        
        request_id = request.headers.get("X-Request-ID", self._generate_request_id())
        
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["X-Request-ID"] = request_id
        
        hsts_max_age = int(os.getenv("HSTS_MAX_AGE", "31536000"))
        include_subdomains = os.getenv("HSTS_INCLUDE_SUBDOMAINS", "true").lower() == "true"
        
        hsts_value = f"max-age={hsts_max_age}"
        if include_subdomains:
            hsts_value += "; includeSubDomains"
        if os.getenv("HSTS_PRELOAD", "false").lower() == "true":
            hsts_value += "; preload"
        
        response.headers["Strict-Transport-Security"] = hsts_value
        
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        response.headers["Permissions-Policy"] = "; ".join([
            "accelerometer=()",
            "camera=()",
            "geolocation=()",
            "gyroscope=()",
            "magnetometer=()",
            "microphone=()",
            "payment=()",
        ])
        
        if os.getenv("ENVIRONMENT", "development") == "production":
            response.headers["Content-Security-Policy"] = self.CSP_DIRECTIVE
        
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        return response
    
    def _generate_request_id(self) -> str:
        import uuid
        return str(uuid.uuid4())


class CORSMiddleware(BaseHTTPMiddleware):
    """
    Enhanced CORS middleware with strict configuration.
    """
    
    def __init__(
        self,
        app,
        allowed_origins: list = None,
        allowed_methods: list = None,
        allowed_headers: list = None,
        max_age: int = 600,
        allow_credentials: bool = True
    ):
        super().__init__(app)
        
        self.allowed_origins = allowed_origins or [
            "https://nazmos.ai",
            "https://www.nazmos.ai",
            "http://localhost:3000",
            "http://localhost:8000",
        ]
        
        self.allowed_methods = allowed_methods or [
            "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
        ]
        
        self.allowed_headers = allowed_headers or [
            "Accept",
            "Accept-Language",
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "X-CSRF-Token",
        ]
        
        self.max_age = max_age
        self.allow_credentials = allow_credentials
    

    @staticmethod
    def set_default_headers(response: Response) -> Response:
        """Compatibility helper used by tests and simple ASGI wrappers."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @staticmethod
    def add_custom_headers(response: Response, headers: dict) -> Response:
        for key, value in (headers or {}).items():
            response.headers[str(key)] = str(value)
        return response

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            origin = request.headers.get("origin")
            
            if origin in self.allowed_origins:
                return Response(
                    status_code=200,
                    headers={
                        "Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Methods": ", ".join(self.allowed_methods),
                        "Access-Control-Allow-Headers": ", ".join(self.allowed_headers),
                        "Access-Control-Max-Age": str(self.max_age),
                        "Access-Control-Allow-Credentials": str(self.allow_credentials).lower(),
                        "Vary": "Origin",
                    }
                )
            else:
                return Response(status_code=403)
        
        response = await call_next(request)
        
        origin = request.headers.get("origin")
        if origin in self.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = str(self.allow_credentials).lower()
            response.headers["Vary"] = "Origin"
        
        return response


def get_cors_config() -> dict:
    return {
        "origins": ["https://nazmos.ai", "https://www.nazmos.ai", "http://localhost:3000", "http://localhost:8000"],
        "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "headers": ["Accept", "Accept-Language", "Authorization", "Content-Type", "X-Request-ID", "X-CSRF-Token"],
    }
