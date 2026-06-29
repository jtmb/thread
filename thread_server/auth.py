"""Token-based authentication with zero external dependencies.

Uses HMAC-SHA256 signed tokens and PBKDF2-HMAC-SHA256 password hashing —
all from Python's stdlib. No JWT library, no bcrypt, no pip installs needed.

Token format: base64(header).base64(payload).base64(signature)
  - header: {"alg": "HS256", "typ": "THREAD"}
  - payload: {"sub": "<username>", "iat": <issued_at_unix>, "exp": <expiry_unix>}
  - signature: HMAC-SHA256(header.payload, secret_key)

Password storage: pbkdf2:sha256:600000$<salt>$<hash>

Usage:
    from thread_server import auth

    token = auth.create_token("admin", secret, expiry=86400)
    payload = auth.verify_token(token, secret)  # → dict or None
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from thread_server import config

# PBKDF2 iteration count — OWASP recommends 600K for SHA-256 (2023+)
PBKDF2_ITERATIONS = 600_000
PBKDF2_HASH_FUNC = "sha256"
PBKDF2_SALT_BYTES = 16
TOKEN_SEPARATOR = "."

# Ephemeral signing key — auto-generated when AUTH_SECRET_KEY is empty.
# Process-local: all tokens created by this server instance use the same key
# for the lifetime of the process. Restart → all tokens invalidated.
_ephemeral_signing_key: str | None = None


def _ephemeral_key() -> str:
    """Return the ephemeral signing key, generating one if needed.

    When AUTH_SECRET_KEY is not configured (auth disabled, default),
    each server process auto-generates a random key. This allows the
    /api/v1/auth/status endpoint to verify tokens even in disabled mode.
    """
    global _ephemeral_signing_key
    if _ephemeral_signing_key is None:
        _ephemeral_signing_key = generate_secret_key()
    return _ephemeral_signing_key


# ── Token Creation & Verification ────────────────────────────────────────────

def create_token(username: str, secret_key: str | None = None, expiry_seconds: int | None = None) -> str:
    """Create a signed authentication token.

    Args:
        username: The subject (user) this token identifies.
        secret_key: HMAC signing key. Defaults to config.AUTH_SECRET_KEY.
                     Auto-generates a random key if the config value is empty.
        expiry_seconds: Token lifetime in seconds. Defaults to config.AUTH_TOKEN_EXPIRY.

    Returns:
        Base64-encoded token string: header.payload.signature
    """
    if secret_key is None:
        secret_key = config.AUTH_SECRET_KEY or _ephemeral_key()
    if expiry_seconds is None:
        expiry_seconds = config.AUTH_TOKEN_EXPIRY

    now = int(time.time())
    header = {"alg": "HS256", "typ": "THREAD"}
    payload = {"sub": username, "iat": now, "exp": now + expiry_seconds}

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")))

    signing_input = f"{header_b64}{TOKEN_SEPARATOR}{payload_b64}"
    signature = _hmac_sha256(signing_input, secret_key)
    sig_b64 = _b64url_encode(signature)

    return f"{header_b64}{TOKEN_SEPARATOR}{payload_b64}{TOKEN_SEPARATOR}{sig_b64}"


def verify_token(token: str, secret_key: str | None = None) -> dict | None:
    """Verify a token and return its payload if valid.

    Checks: signature integrity, expiry time, and structural validity.
    Returns None for any failure — no distinction between expired and tampered
    (avoids leaking token structure to attackers).

    Args:
        token: The raw token string (header.payload.signature).
        secret_key: HMAC signing key. Defaults to config.AUTH_SECRET_KEY.

    Returns:
        Payload dict (sub, iat, exp) if valid, None otherwise.
    """
    if secret_key is None:
        secret_key = config.AUTH_SECRET_KEY or _ephemeral_key()

    parts = token.split(TOKEN_SEPARATOR)
    if len(parts) != 3:
        return None

    header_b64, payload_b64, sig_b64 = parts

    # Verify signature
    signing_input = f"{header_b64}{TOKEN_SEPARATOR}{payload_b64}"
    expected_sig = _hmac_sha256(signing_input, secret_key)
    if not hmac.compare_digest(_b64url_encode(expected_sig), sig_b64):
        return None

    # Decode payload
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (json.JSONDecodeError, ValueError):
        return None

    # Check expiry
    if payload.get("exp", 0) <= int(time.time()):
        return None

    return payload


# ── Password Hashing ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256.

    Format: pbkdf2:sha256:600000$<salt>$<hash>
    Salt is generated per call — each invocation produces a different hash.

    Args:
        password: The plaintext password to hash.

    Returns:
        Storable hash string.
    """
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        PBKDF2_HASH_FUNC,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    salt_hex = salt.hex()
    dk_hex = dk.hex()
    return f"pbkdf2:{PBKDF2_HASH_FUNC}:{PBKDF2_ITERATIONS}${salt_hex}${dk_hex}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored PBKDF2 hash.

    Args:
        password: The plaintext password to check.
        stored_hash: Hash from hash_password().

    Returns:
        True if the password matches.
    """
    if not stored_hash:
        return False

    try:
        prefix, rest = stored_hash.split("$", 1)
        algo_part, iterations_str = prefix.split(":", 2)[1:] if prefix.startswith("pbkdf2:") else ("", "")
        iterations = int(iterations_str) if iterations_str else PBKDF2_ITERATIONS
        salt_hex, dk_hex = rest.split("$", 1)

        salt = bytes.fromhex(salt_hex)
        expected_dk = bytes.fromhex(dk_hex)

        actual_dk = hashlib.pbkdf2_hmac(
            PBKDF2_HASH_FUNC,
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected_dk),
        )
        return hmac.compare_digest(actual_dk, expected_dk)
    except (ValueError, IndexError):
        return False


# ── Key Generation ───────────────────────────────────────────────────────────

def generate_secret_key() -> str:
    """Generate a cryptographically random secret key.

    Returns:
        64 hex characters (32 random bytes), suitable for HMAC-SHA256 signing.
    """
    return secrets.token_hex(32)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _b64url_encode(data: str | bytes) -> str:
    """Base64url encode (no padding, URL-safe characters)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """Base64url decode (adds padding back automatically)."""
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def _hmac_sha256(message: str, key: str) -> bytes:
    """Compute HMAC-SHA256."""
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
