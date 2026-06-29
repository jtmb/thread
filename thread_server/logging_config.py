"""Structured NDJSON logging — per AGENTS.md observability rules.

Every log line is a JSON object with timestamp, level, message, requestId, and
optional traceId. Logs go to stderr by default (captured by systemd journald).
Never use print() in production code paths.
"""

import json
import logging
import logging.config
import sys
import uuid
from datetime import datetime, timezone

from flask import Flask, g, request

from thread_server import config

REQUEST_ID_HEADER = "X-Request-Id"
TRACE_ID_HEADER = "X-Trace-Id"


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Include request ID if available (set by Flask before_request hook)
        try:
            request_id = getattr(g, "request_id", None)
        except RuntimeError:
            # Not in Flask application context (e.g., during startup or tests)
            request_id = None
        if request_id:
            log_entry["requestId"] = request_id

        # Include trace ID if set
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            log_entry["traceId"] = trace_id

        # Include exception info if present
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(app: Flask) -> None:
    """Configure the root logger with JSON formatting for structured logging.

    Args:
        app: The Flask application instance.
    """
    level = logging.DEBUG if config.DEBUG else getattr(logging, config.LOG_LEVEL, logging.INFO)

    # Determine the handler: stderr (journald) or file
    if config.LOG_FILE:
        handler: logging.Handler = logging.FileHandler(config.LOG_FILE)
    else:
        handler = logging.StreamHandler(sys.stderr)

    handler.setFormatter(JsonFormatter())
    handler.setLevel(level)

    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Remove any existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Quiet down noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    # Register Flask hooks for request ID propagation
    app.before_request(_before_request)
    app.teardown_request(_teardown_request)

    app.logger.info(
        "Logging initialized: level=%s handler=%s",
        config.LOG_LEVEL,
        "stderr" if not config.LOG_FILE else config.LOG_FILE,
    )


def _before_request() -> None:
    """Set request ID and trace ID on Flask's g before each request."""
    g.request_id = request.headers.get(REQUEST_ID_HEADER) or f"req_{uuid.uuid4().hex[:12]}"
    g.trace_id = request.headers.get(TRACE_ID_HEADER) or g.request_id
    g.start_time = datetime.now(timezone.utc)
    app = request.environ.get("flask.app")
    if app:
        app.logger.debug(
            "Request started: %s %s",
            request.method,
            request.path,
        )


def _teardown_request(exc: Exception | None = None) -> None:
    """Log request completion with status and duration."""
    app = request.environ.get("flask.app") if request and request.environ else None
    if app and hasattr(g, "start_time"):
        duration_ms = (datetime.now(timezone.utc) - g.start_time).total_seconds() * 1000
        status = getattr(g, "response_status", getattr(request, "status_code", 500))
        app.logger.info(
            "Request completed: %s %s → %s (%.1fms)",
            request.method,
            request.path,
            status,
            duration_ms,
        )
