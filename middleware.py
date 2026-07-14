"""
Middleware Module
==================
Production middleware for:
  - Request/response logging
  - Request ID generation
  - Rate limiting
  - Security headers
  - Request timing
"""

import logging
import time
import uuid

from flask import g, request

logger = logging.getLogger(__name__)


def register_middleware(app):
    """Register all middleware on the Flask app."""

    # ---- Request ID & Timing ----
    @app.before_request
    def before_request():
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        g.start_time = time.perf_counter()

    @app.after_request
    def after_request(response):
        # Add request ID to response
        response.headers["X-Request-ID"] = getattr(g, "request_id", "unknown")

        # Log request details
        duration_ms = (time.perf_counter() - getattr(g, "start_time", 0)) * 1000
        logger.info(
            "[%s] %s %s %s -> %d (%.1fms)",
            getattr(g, "request_id", "?"),
            request.remote_addr,
            request.method,
            request.path,
            response.status_code,
            duration_ms,
        )

        # Warn on slow requests
        if duration_ms > 1000:
            logger.warning(
                "[%s] SLOW REQUEST: %s %s took %.1fms",
                getattr(g, "request_id", "?"),
                request.method,
                request.path,
                duration_ms,
            )

        return response

    # ---- Security Headers ----
    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        # Remove server header
        response.headers.pop("Server", None)
        return response

    logger.info("Middleware registered.")


def setup_rate_limiting(app):
    """Set up Flask-Limiter for rate limiting."""
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        from config import get_config

        cfg = get_config()

        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=[cfg.RATE_LIMIT_DEFAULT],
            storage_uri=cfg.RATELIMIT_STORAGE_URI,  # memory:// by default; set RATELIMIT_STORAGE_URI=redis://... for multi-worker
        )

        # Store limiter on app for use in blueprints
        app.extensions["limiter"] = limiter
        logger.info("Rate limiting enabled: %s", cfg.RATE_LIMIT_DEFAULT)
        return limiter

    except ImportError:
        logger.warning(
            "flask-limiter not installed. Rate limiting is DISABLED. "
            "Install with: pip install flask-limiter"
        )
        return None
