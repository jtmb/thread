"""Authentication routes — login, logout, status, and password change.

Blueprint: auth_bp
URL prefix: /api/v1/auth

Endpoints:
  POST /api/v1/auth/login           — exchange password for a Bearer token
  POST /api/v1/auth/logout          — acknowledge logout (stateless, token is client-side)
  POST /api/v1/auth/change-password — change admin password (requires valid token)
  GET  /api/v1/auth/status          — check if the request carries a valid token

Username is always "admin" (single-user system) — the client only sends a
password. When THREAD_AUTH_ENABLED=false, any password succeeds with a
dummy token, keeping the API contract stable regardless of auth state.
"""

import logging

from flask import Blueprint, g, jsonify, request

from thread_server import auth, config

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/v1/auth/login", methods=["POST"])
def login():
    """Authenticate and return a Bearer token.

    Request body: {"password": "...", "expires_in": <int|0>}
    Username is always "admin" (single-user system).

    expires_in controls token lifetime:
      - absent (default): uses AUTH_TOKEN_EXPIRY (24h by default)
      - 0: token never expires (no `exp` claim in payload)
      - > 0: token expires after that many seconds

    Responses:
        200: {"token": "...", "expires_in": 86400|null, "token_type": "Bearer"}
        400: Missing or malformed body
        401: Invalid credentials
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "bad_request", "message": "JSON body required"}), 400

    password = body.get("password", "")

    if not password:
        return jsonify({"error": "bad_request", "message": "password is required"}), 400

    # Parse optional expires_in — 0 means no expiry, absent means default
    expires_in = body.get("expires_in")
    if expires_in is not None and (not isinstance(expires_in, int) or expires_in < 0):
        return jsonify({"error": "bad_request", "message": "expires_in must be a non-negative integer"}), 400

    # Auth disabled: auto-succeed with a token for any password
    if not config.AUTH_ENABLED:
        token = auth.create_token(config.AUTH_USERNAME, expiry_seconds=expires_in)
        return jsonify({
            "token": token,
            "expires_in": None if expires_in == 0 else (expires_in if expires_in is not None else config.AUTH_TOKEN_EXPIRY),
            "token_type": "Bearer",
        })

    # Auth enabled: verify password for the single admin user
    if not auth.verify_password(password, auth.get_password_hash()):
        logger.warning("Login failed (bad password)")
        return jsonify({"error": "unauthorized", "message": "Invalid password"}), 401

    token = auth.create_token(config.AUTH_USERNAME, expiry_seconds=expires_in)
    logger.info("User '%s' logged in successfully", config.AUTH_USERNAME)
    return jsonify({
        "token": token,
        "expires_in": None if expires_in == 0 else (expires_in if expires_in is not None else config.AUTH_TOKEN_EXPIRY),
        "token_type": "Bearer",
    })


@auth_bp.route("/api/v1/auth/logout", methods=["POST"])
def logout():
    """Acknowledge logout.

    Tokens are stateless — the client discards the token. This endpoint
    exists for API completeness and to allow future server-side token
    blacklisting without changing the client contract.
    """
    return jsonify({"status": "ok"})


@auth_bp.route("/api/v1/auth/change-password", methods=["POST"])
def change_password():
    """Change the admin password.

    Request body: {"current_password": "...", "new_password": "..."}

    Validates the current password, then persists the new password hash
    to disk so it survives server restarts.

    Responses:
        200: {"status": "ok", "message": "Password changed"}
        400: Missing or malformed body, or new password too short
        401: Current password incorrect
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "bad_request", "message": "JSON body required"}), 400

    # Password changes only make sense when auth is enabled
    if not config.AUTH_ENABLED:
        return jsonify({"error": "bad_request", "message": "Authentication is disabled, no password to change"}), 400

    current_password = body.get("current_password", "")
    new_password = body.get("new_password", "")

    if not current_password or not new_password:
        return jsonify({"error": "bad_request", "message": "current_password and new_password are required"}), 400

    if len(new_password) < 8:
        return jsonify({"error": "bad_request", "message": "New password must be at least 8 characters"}), 400

    # Verify current password
    if not auth.verify_password(current_password, auth.get_password_hash()):
        logger.warning("Change password failed: current password incorrect")
        return jsonify({"error": "unauthorized", "message": "Current password is incorrect"}), 401

    # Hash and persist the new password
    new_hash = auth.hash_password(new_password)
    auth.save_password_hash(new_hash)

    logger.info("Password changed successfully")
    return jsonify({"status": "ok", "message": "Password changed"})


@auth_bp.route("/api/v1/auth/status", methods=["GET"])
def auth_status():
    """Return the current authentication status.

    When auth is enabled, relies on the middleware having set g.username.
    When auth is disabled, checks the Bearer token directly for consistency.
    """
    # Check middleware-set username first
    if getattr(g, "username", None):
        return jsonify({"authenticated": True, "username": g.username, "auth_enabled": config.AUTH_ENABLED})

    # Auth disabled — check token manually for API consistency
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        payload = auth.verify_token(auth_header[7:])
        if payload:
            return jsonify({"authenticated": True, "username": payload.get("sub"), "auth_enabled": config.AUTH_ENABLED})

    return jsonify({"authenticated": False, "username": None, "auth_enabled": config.AUTH_ENABLED})
