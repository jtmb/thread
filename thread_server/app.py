"""Flask application factory — the single entry point for creating the Thread server.

Creates the Flask app, starts the connection pool, initializes caches,
registers blueprints and error handlers. Designed for testability:
every create_app() call produces a fresh, isolated instance.
"""

import logging
import os
import time
import uuid
from pathlib import Path

from flask import Flask, g, request

from thread_server import config, cache, models, auth as auth_module
from thread_server import database as db_module
from thread_server.database import init_pool
from thread_server.git_manager import init_git_manager
from thread_server.logging_config import setup_logging
from thread_server.routes import (
    health as health_routes,
    sessions as session_routes,
    entries as entry_routes,
    search as search_routes,
    stats as stats_routes,
    auth as auth_routes,
    events as events_routes,
    errors as error_handlers,
)
from thread_server.stats_collector import (
    record_request_start,
    record_request_duration,
)

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Build and configure the Flask application.

    Order of operations:
    1. Validate configuration
    2. Create Flask app
    3. Setup structured JSON logging
    4. Start the database connection pool (pre-warm all connections)
    5. Initialize caches + git manager
    6. Register route blueprints
    7. Register error handlers
    8. Register request logging hooks

    Returns:
        A fully configured Flask application instance ready to serve.
    """
    # 1. Validate config — fail fast if anything is wrong
    config.validate()
    logger.info("Configuration validated")

    # 2. Create the Flask app
    frontend_dir = Path(__file__).parent.parent / config.FRONTEND_DIR
    app = Flask(
        __name__,
        static_folder=str(frontend_dir / "static"),
        static_url_path="/dashboard/static",
        template_folder=str(frontend_dir / "templates"),
    )
    app.json.sort_keys = False  # Preserve field order in JSON responses

    # Set debug mode from config
    if config.DEBUG:
        app.config["DEBUG"] = True
        app.config["TESTING"] = False
        logger.warning("Debug mode enabled — NEVER use in production")

    # 3. Setup structured logging
    setup_logging(app)

    # 4. Start the connection pool (pre-warm all connections)
    init_pool()
    db_module.pool.start()
    logger.info("Database pool started: %d connections", db_module.pool.total_connections)

    # Initialize the database schema (uses main thread's pool connection)
    db = db_module.pool.get()
    try:
        models.init_db(db)
        logger.info("Database schema verified")
    finally:
        pass  # Connection stays with this thread (bootstrap)

    # 5. Initialize caches + git manager
    cache.init_caches()
    init_git_manager()
    logger.info("Caches and git manager initialized")

    # 6. Register route blueprints
    app.register_blueprint(health_routes.health_bp)
    app.register_blueprint(session_routes.sessions_bp)
    app.register_blueprint(entry_routes.entries_bp)
    app.register_blueprint(search_routes.search_bp)
    app.register_blueprint(stats_routes.stats_bp)
    app.register_blueprint(auth_routes.auth_bp)
    app.register_blueprint(events_routes.events_bp)

    # Register frontend blueprint (serves the SPA at /dashboard/*)
    from thread_frontend import frontend_bp
    app.register_blueprint(frontend_bp)

    logger.info("Route blueprints registered")

    # 7. Register error handlers
    error_handlers.register_error_handlers(app)

    # 8. Register request logging hooks
    _register_request_hooks(app)

    config._start_time = time.monotonic()
    record_request_start()

    logger.info("Thread server ready (debug=%s)", config.DEBUG)
    return app


def _check_auth() -> None:
    """Verify Bearer token for protected routes when auth is enabled.

    Sets g.username on success. Aborts with 401 on failure.
    Skipped paths: /api/v1/health, /api/v1/auth/login, OPTIONS preflight,
    and the SSE /api/v1/events endpoint (auth via query param ?token=).
    """
    # Auth disabled: pass through
    if not config.AUTH_ENABLED:
        return

    # Skip unauthenticated paths
    public_paths = ("/api/v1/health", "/api/v1/auth/login")
    if request.path.startswith(public_paths) or request.method == "OPTIONS":
        return

    # SSE endpoint: check token query param (EventSource can't send headers)
    if request.path.startswith("/api/v1/events"):
        token = request.args.get("token", "")
    else:
        # Standard Bearer token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            if request.path.startswith("/dashboard/"):
                return  # Frontend routes are public HTML (auth checked client-side)
            from flask import abort
            abort(401, description="Missing Authorization header")
        token = auth_header[7:]  # Strip "Bearer " prefix

    if not token:
        if request.path.startswith("/api/v1/events"):
            return  # No token on SSE — allow (view grabs token itself)
        from flask import abort
        abort(401, description="Missing authentication token")

    payload = auth_module.verify_token(token)
    if payload is None:
        from flask import abort
        abort(401, description="Invalid or expired token")

    g.username = payload.get("sub", "unknown")
    logger.debug("Authenticated user: %s", g.username)


def _register_request_hooks(app: Flask) -> None:
    """Register before_request and after_request hooks for logging and metrics."""

    @app.before_request
    def _before():
        """Attach DB connection, request ID, and timing to Flask's g."""
        g.request_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:12]}"
        g.trace_id = request.headers.get("X-Trace-Id") or g.request_id
        g.start_time = time.monotonic()

        # Skip frontend routes (SPA HTML + static assets) — they don't need a DB connection
        if request.path.startswith("/dashboard/"):
            return

        # Auth middleware: verify Bearer tokens when auth is enabled
        _check_auth()

        # Attach DB connection for this thread (from pre-warmed pool)
        try:
            g.db = db_module.pool.get()
            db_module.pool.mark_busy()
        except RuntimeError as e:
            logger.error("Failed to get DB connection: %s", e)
            from flask import abort

            abort(503, description="Service unavailable — connection pool exhausted")

    @app.after_request
    def _after(response):
        """Log request completion, track stats, add diagnostic headers."""
        response.headers["X-Request-Id"] = getattr(g, "request_id", "unknown")

        # Mark thread as idle — it's no longer processing a request
        if db_module.pool is not None:
            db_module.pool.mark_idle()

        if hasattr(g, "start_time"):
            duration_ms = (time.monotonic() - g.start_time) * 1000
            response.headers["X-Duration-Ms"] = f"{duration_ms:.1f}"

            # Track in ring buffer for stats
            record_request_duration(duration_ms)

            logger.debug(
                "Request: %s %s → %s (%.1fms)",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
            )

        # CORS: open in debug mode, same-origin in production
        if config.DEBUG:
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"

        return response
