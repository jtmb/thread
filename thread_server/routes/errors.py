"""Centralized Flask error handlers.

Registered on the Flask app to ensure every error response follows the
standardized error shape from api-design.instructions.md:

    {"error": {"code": "...", "message": "...", "details": [], "requestId": "..."}}

Handlers are registered indirectly via register_error_handlers(app) so
they can be unit-tested with a fresh app instance.
"""

import logging

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> None:
    """Register all error handlers on the given Flask app instance.

    Args:
        app: The Flask application to register handlers on.
    """

    @app.errorhandler(400)
    def handle_400(exc: HTTPException):
        """Validation errors — malformed input."""
        logger.warning("400 Bad Request: %s %s — %s", request.method, request.path, exc.description)
        return _error_response(400, "VALIDATION", str(exc.description))

    @app.errorhandler(404)
    def handle_404(exc: HTTPException):
        """Resource not found."""
        return _error_response(404, "NOT_FOUND", str(exc.description) or "Resource not found")

    @app.errorhandler(409)
    def handle_409(exc: HTTPException):
        """Resource conflict (duplicate name, version mismatch)."""
        logger.warning("409 Conflict: %s %s — %s", request.method, request.path, exc.description)
        return _error_response(409, "CONFLICT", str(exc.description))

    @app.errorhandler(413)
    def handle_413(exc: HTTPException):
        """Payload too large."""
        return _error_response(413, "TOO_LARGE", str(exc.description) or "Request entity too large")

    @app.errorhandler(415)
    def handle_415(exc: HTTPException):
        """Unsupported media type."""
        return _error_response(415, "UNSUPPORTED_MEDIA", str(exc.description) or "Unsupported media type")

    @app.errorhandler(422)
    def handle_422(exc: HTTPException):
        """Unprocessable entity — semantic validation failure."""
        return _error_response(422, "UNPROCESSABLE", str(exc.description))

    @app.errorhandler(429)
    def handle_429(exc: HTTPException):
        """Rate limit exceeded."""
        return _error_response(429, "RATE_LIMITED", "Rate limit exceeded. Try again later.")

    @app.errorhandler(500)
    def handle_500(exc: HTTPException):
        """Unexpected server error — log the full trace, return clean message."""
        logger.exception("500 Internal Server Error: %s %s", request.method, request.path)
        return _error_response(500, "INTERNAL", "An unexpected error occurred. Request ID: " + getattr(g, "request_id", "unknown"))


def _error_response(status: int, code: str, message: str) -> tuple:
    """Build a Flask error response tuple in the standard shape.

    Args:
        status: HTTP status code.
        code: Machine-readable error code string.
        message: Human-readable error description.

    Returns:
        (response_body, status_code) tuple.
    """
    return (
        jsonify({
            "error": {
                "code": code,
                "message": message,
                "details": [],
                "requestId": getattr(g, "request_id", None),
            }
        }),
        status,
    )
