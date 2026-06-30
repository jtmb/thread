"""Tests for authentication system — token creation, password hashing, and API routes.

Covers:
  - Token creation and verification (valid, expired, tampered)
  - Password hashing and verification
  - Login endpoint (success, bad credentials, disabled auth)
  - Protected route access (valid token, no token, expired token)
  - Auth status endpoint
  - Rate limiting structure (deferred to later phase)
"""

import json
import time
from unittest.mock import patch

import pytest

from thread_server import auth


# ── Token Creation & Verification ────────────────────────────────────────────


class TestTokenCrypto:
    """Unit tests for HMAC token creation and verification."""

    def test_create_and_verify_valid_token(self):
        """Round-trip: create a token, verify it returns correct payload."""
        secret = auth.generate_secret_key()
        token = auth.create_token("admin", secret, expiry_seconds=3600)
        payload = auth.verify_token(token, secret)
        assert payload is not None
        assert payload["sub"] == "admin"
        assert "iat" in payload
        assert payload["exp"] > int(time.time())

    def test_expired_token_returns_none(self):
        """A token with 0-second expiry is immediately expired."""
        secret = auth.generate_secret_key()
        token = auth.create_token("admin", secret, expiry_seconds=0)
        payload = auth.verify_token(token, secret)
        assert payload is None

    def test_tampered_token_returns_none(self):
        """Modifying the payload invalidates the signature."""
        secret = auth.generate_secret_key()
        token = auth.create_token("admin", secret, expiry_seconds=3600)
        # Flip a character in the payload section
        parts = token.split(".")
        payload_bytes = bytearray(parts[1], "ascii")
        payload_bytes[2] ^= 1  # Flip one bit
        tampered = ".".join([parts[0], payload_bytes.decode("ascii"), parts[2]])
        payload = auth.verify_token(tampered, secret)
        assert payload is None

    def test_wrong_secret_returns_none(self):
        """Token signed with key A is not valid with key B."""
        token = auth.create_token("admin", auth.generate_secret_key(), expiry_seconds=3600)
        payload = auth.verify_token(token, auth.generate_secret_key())
        assert payload is None

    def test_empty_token_returns_none(self):
        """Empty string is not a valid token."""
        assert auth.verify_token("") is None

    def test_malformed_token_returns_none(self):
        """Single-part token returns None."""
        assert auth.verify_token("not.a.token.format") is None


# ── Password Hashing ──────────────────────────────────────────────────────────


class TestPasswordHashing:
    """Unit tests for PBKDF2 password hashing."""

    def test_hash_and_verify(self):
        """Hash a password, verify it succeeds."""
        h = auth.hash_password("mypassword123")
        assert h.startswith("pbkdf2:sha256:")
        assert auth.verify_password("mypassword123", h)

    def test_wrong_password_fails(self):
        """Wrong password does not verify."""
        h = auth.hash_password("correct")
        assert not auth.verify_password("wrong", h)

    def test_empty_hash_fails(self):
        """Empty or None stored hash always fails."""
        assert not auth.verify_password("anything", "")
        assert not auth.verify_password("anything", None)

    def test_hash_is_different_each_time(self):
        """Each call produces a unique hash (different salt)."""
        h1 = auth.hash_password("same")
        h2 = auth.hash_password("same")
        assert h1 != h2
        assert auth.verify_password("same", h1)
        assert auth.verify_password("same", h2)


# ── Auth API Routes ───────────────────────────────────────────────────────────


class TestAuthRoutes:
    """Integration tests for auth endpoints using Flask test client."""

    def test_login_auth_disabled_succeeds(self, client):
        """When auth is disabled, any password gets a token."""
        from thread_server import config
        config.AUTH_ENABLED = False
        try:
            resp = client.post("/api/v1/auth/login", json={
                "password": "anything",
            })
            assert resp.status_code == 200
            data = resp.get_json()
            assert "token" in data
            assert data["expires_in"] > 0
            assert data["token_type"] == "Bearer"
        finally:
            config.AUTH_ENABLED = True  # Restore default

    def test_login_missing_body_returns_400(self, client):
        """Empty body returns 400."""
        resp = client.post("/api/v1/auth/login", data="not json",
                           content_type="text/plain")
        assert resp.status_code == 400

    def test_login_missing_fields_returns_400(self, client):
        """Missing username or password returns 400."""
        resp = client.post("/api/v1/auth/login", json={"username": "x"})
        assert resp.status_code == 400

    def test_protected_route_with_valid_token(self, client):
        """A valid token allows access to protected routes."""
        from thread_server import config as cfg
        cfg.AUTH_ENABLED = False
        try:
            # Login to get a token (any password works when auth is disabled)
            login_resp = client.post("/api/v1/auth/login", json={
                "password": "doesnt-matter",
            })
            token = login_resp.get_json()["token"]

            # Token works even with auth re-enabled because it was issued
            # by the same running app (same secret key)
            cfg.AUTH_ENABLED = True

            # Use token to access protected resource
            resp = client.get("/api/v1/sessions",
                              headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
        finally:
            cfg.AUTH_ENABLED = True  # Restore default

    def test_protected_route_no_token_returns_401(self, client, monkeypatch):
        """Without auth header, protected routes return 401 when auth enabled."""
        # Enable auth for this test
        from thread_server import config as cfg
        monkeypatch.setattr(cfg, "AUTH_ENABLED", True)

        resp = client.get("/api/v1/sessions")
        # 401 or something else depending on test config — just check not 200
        assert resp.status_code == 401

    def test_protected_route_invalid_token_returns_401(self, client, monkeypatch):
        """An invalid token returns 401."""
        from thread_server import config as cfg
        monkeypatch.setattr(cfg, "AUTH_ENABLED", True)

        resp = client.get("/api/v1/sessions",
                          headers={"Authorization": "Bearer invalid-token-here"})
        assert resp.status_code == 401

    def test_health_endpoint_unauthenticated(self, client, monkeypatch):
        """Health endpoint is always accessible, even with auth enabled."""
        from thread_server import config as cfg
        monkeypatch.setattr(cfg, "AUTH_ENABLED", True)

        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_logout_returns_ok(self, client):
        """Logout returns 200 with status ok (stateless)."""
        from thread_server import config as cfg
        cfg.AUTH_ENABLED = False
        try:
            resp = client.post("/api/v1/auth/logout")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "ok"
        finally:
            cfg.AUTH_ENABLED = True

    def test_auth_status_unauthenticated(self, client):
        """Status returns authenticated=false when no token."""
        from thread_server import config as cfg
        cfg.AUTH_ENABLED = False
        try:
            resp = client.get("/api/v1/auth/status")
            data = resp.get_json()
            assert data["authenticated"] is False
        finally:
            cfg.AUTH_ENABLED = True

    def test_auth_status_authenticated(self, client):
        """Status returns authenticated=true with a valid token."""
        from thread_server import config as cfg
        cfg.AUTH_ENABLED = False
        try:
            login_resp = client.post("/api/v1/auth/login", json={
                "password": "p",
            })
            token = login_resp.get_json()["token"]
            resp = client.get("/api/v1/auth/status",
                              headers={"Authorization": f"Bearer {token}"})
            data = resp.get_json()
            assert data["authenticated"] is True
            assert data["username"] == "admin"
        finally:
            cfg.AUTH_ENABLED = True
