"""Session CRUD routes — create, list, read, delete context sessions.

Blueprint: sessions_bp
URL prefix: /api/v1/sessions
"""

import logging

from flask import Blueprint, g, jsonify, make_response, request

from thread_server import models
from thread_server.cache import invalidate_caches
from thread_server.git_manager import git_manager

logger = logging.getLogger(__name__)

sessions_bp = Blueprint("sessions", __name__, url_prefix="/api/v1/sessions")


@sessions_bp.route("", methods=["GET"])
def list_sessions():
    """List all sessions, newest first."""
    db = g.db
    sessions = models.list_sessions(db)
    return jsonify(sessions)


@sessions_bp.route("", methods=["POST"])
def create_session():
    """Create a new session.

    Request body: {"name": "...", "description": "..."}
    Returns 201 Created with the session object.
    Returns 409 Conflict if the session name already exists.
    """
    db = g.db
    body = request.get_json(silent=True)
    if not body:
        return _error(400, "VALIDATION", "Request body must be valid JSON")

    name = body.get("name", "").strip()
    if not name:
        return _error(400, "VALIDATION", "name is required")

    description = body.get("description", "").strip()

    # Check for duplicate name
    existing = models.get_session_by_name(db, name)
    if existing:
        return _error(409, "CONFLICT", f"Session '{name}' already exists")

    session = models.create_session(db, name, description)

    # Best-effort git commit
    if git_manager:
        git_manager.commit_session_created(name)

    response = make_response(jsonify(session), 201)
    response.headers["Location"] = f"/api/v1/sessions/{name}"
    return response


@sessions_bp.route("/<name>", methods=["GET"])
def get_session(name: str):
    """Get a session by its unique name.

    Returns 200 with the session object, or 404 if not found.
    """
    db = g.db
    session = models.get_session_by_name(db, name)
    if session is None:
        return _error(404, "NOT_FOUND", f"Session '{name}' not found")
    return jsonify(session)


@sessions_bp.route("/<name>", methods=["DELETE"])
def delete_session(name: str):
    """Delete a session and all its entries (CASCADE).

    Returns 204 No Content, or 404 if not found.
    """
    db = g.db
    session = models.get_session_by_name(db, name)
    if session is None:
        return _error(404, "NOT_FOUND", f"Session '{name}' not found")

    models.delete_session(db, session["id"])
    invalidate_caches(session["id"])

    # Best-effort git commit
    if git_manager:
        git_manager.commit_session_deleted(name)

    return "", 204


def _error(status: int, code: str, message: str) -> tuple:
    """Build a standardized error response tuple.

    Args:
        status: HTTP status code.
        code: Machine-readable error code (e.g., VALIDATION).
        message: Human-readable description.

    Returns:
        (response_json, status_code) tuple for Flask.
    """
    return (
        jsonify(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "details": [],
                    "requestId": getattr(g, "request_id", None),
                }
            }
        ),
        status,
    )
