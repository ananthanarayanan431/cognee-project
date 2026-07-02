import time
import uuid
from collections import defaultdict, deque

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Hosts used by the test clients — never rate-limit or these break CI.
_EXEMPT_HOSTS = {"testclient", "testserver"}


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add baseline hardening headers to every response."""

    def __init__(self, app, enable_hsts: bool = False):
        super().__init__(app)
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if self.enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Lightweight in-memory per-IP sliding-window limiter.

    Adequate for a single-process deployment / demo. For multi-worker
    production, back this with Redis (the redis dep is already present) so the
    budget is shared across workers rather than per-process.
    """

    def __init__(self, app, per_minute: int = 120):
        super().__init__(app)
        self.per_minute = per_minute
        self.window = 60.0
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        client = request.client
        host = client.host if client else None
        # Skip disabled limiter, preflight, health checks, and test clients.
        if (
            self.per_minute <= 0
            or request.method == "OPTIONS"
            or request.url.path in ("/health", "/healthz", "/")
            or host is None
            or host in _EXEMPT_HOSTS
        ):
            return await call_next(request)

        now = time.monotonic()
        hits = self._hits[host]
        cutoff = now - self.window
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= self.per_minute:
            retry = max(1, int(self.window - (now - hits[0])))
            return JSONResponse(
                status_code=429,
                content={"success": False, "detail": "Too many requests. Please slow down."},
                headers={"Retry-After": str(retry)},
            )
        hits.append(now)
        return await call_next(request)
