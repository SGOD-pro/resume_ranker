"""
middleware/rate_limit.py — Sliding Window Rate Limiting Middleware
===================================================================
Applies request rate limiting on sensitive public & auth endpoints:
- ATS check (/api/v2/jobs/ats-check, /api/v2/ats-check): max 10 requests/min per IP
- Auth login (/api/v2/auth/login): max 20 requests/min per IP
- Auth register (/api/v2/auth/register): max 10 requests/min per IP

NOTE: Resume uploads (/resumes, /upload-sessions) are EXEMPT from generic IP-based
request rate limiting to allow legitimate bulk uploads (e.g. 40+ PDFs). Protection
for uploads is enforced at the organization layer via upload session quotas,
bounded concurrency, file size, and page limits.
"""

import logging
import time
from collections import defaultdict
from typing import Dict, List

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Route pattern -> (max_requests, window_seconds)
RATE_LIMIT_RULES = [
    ("/ats-check", 10, 60),
    ("/auth/login", 20, 60),
    ("/auth/register", 10, 60),
]


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # client_ip -> list of timestamps
        self._history: Dict[str, List[float]] = defaultdict(list)

    def _get_client_key(self, request: Request, endpoint_tag: str) -> str:
        # Check forward headers if behind reverse proxy
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        return f"{client_ip}:{endpoint_tag}"

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        now = time.time()

        for pattern, max_requests, window_seconds in RATE_LIMIT_RULES:
            if pattern in path and request.method == "POST":
                key = self._get_client_key(request, pattern)
                timestamps = self._history[key]

                # Purge timestamps outside sliding window
                cutoff = now - window_seconds
                self._history[key] = [t for t in timestamps if t > cutoff]

                if len(self._history[key]) >= max_requests:
                    logger.warning(
                        "Rate limit exceeded for %s on %s (limit: %d/%ds)",
                        key, path, max_requests, window_seconds
                    )
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": {
                                "code": "RATE_LIMIT_EXCEEDED",
                                "message": f"Too many requests to {pattern}. Please wait before retrying.",
                                "retry_after_seconds": window_seconds,
                            }
                        },
                        headers={"Retry-After": str(window_seconds)},
                    )

                self._history[key].append(now)
                break

        return await call_next(request)
