"""Authentication routes — login, logout, and status check.

Blueprint: auth_bp
URL prefix: /api/v1/auth

Endpoints:
  POST /api/v1/auth/login  — exchange username + password for a Bearer token
  POST /api/v1/auth/logout — acknowledge logout (stateless, token is client-side)
  GET  /api/v1/auth/status — check if the request carries a valid token

When THREAD_AUTH_ENABLED=false, login always succeeds with a dummy token
and password verification is skipped. This keeps the API contract stable
regardless of whether auth is enabled.
"""

import logging

from flask import Blueprint, g, jsonify, request

from thread_server import auth, config

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/v1/auth/login", methods=["POST"])
def login():
    """Authenticate and return a Bearer token.

    Request body: {"username": "...", "password": "..."}

    Responses:
        200: {"token": "...", "expires_in": 86400, "token_type": "Bearer"}
        400: Missing or malformed body
        401: Invalid credentials
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "bad_request", "message": "JSON body required"}), 400

    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not username or not password:
        return jsonify({"error": "bad_request", "message": "username and password are required"}), 400

    # Auth disabled: auto-succeed with a token for any credentials
    if not config.AUTH_ENABLED:
        token = auth.create_token(username)
        return jsonify({
            "token": token,
            "expires_in": config.AUTH_TOKEN_EXPIRY,
            "token_type": "Bearer",
        })

    # Auth enabled: verify credentials
    if username != config.AUTH_USERNAME:
        logger.warning("Login attempt for unknown user: %s", username)
        return jsonify({"error": "unauthorized", "message": "Invalid username or password"}), 401

    if not auth.verify_password(password, config.AUTH_PASSWORD_HASH):
        logger.warning("Login failed for user: %s (bad password)", username)
        return jsonify({"error": "unauthorized", "message": "Invalid username or password"}), 401

    token = auth.create_token(username)
    logger.info("User '%s' logged in successfully", username)
    return jsonify({
        "token": token,
        "expires_in": config.AUTH_TOKEN_EXPIRY,
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
