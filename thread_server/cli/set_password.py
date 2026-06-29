"""CLI tool — generate a password hash for use with THREAD_AUTH_PASSWORD_HASH.

Usage:
    python -m thread_server.cli.set_password

Prompts for a password (hidden input), hashes it with PBKDF2-HMAC-SHA256
(600K iterations), and prints the hash string ready for the env var.
Also prints a random secret key for THREAD_AUTH_SECRET_KEY.
"""

import getpass
import sys

from thread_server.auth import generate_secret_key, hash_password


def main() -> None:
    """Interactive password hashing CLI."""

    print("Thread Authentication Setup")
    print("=" * 40)
    print()

    # Generate secret key
    secret = generate_secret_key()
    print(f"THREAD_AUTH_SECRET_KEY={secret}")
    print()

    # Prompt for password (twice to confirm)
    while True:
        pw1 = getpass.getpass("Enter password: ")
        if len(pw1) < 4:
            print("Password must be at least 4 characters.")
            continue
        pw2 = getpass.getpass("Confirm password: ")
        if pw1 != pw2:
            print("Passwords do not match. Try again.")
            continue
        break

    # Hash and print
    pw_hash = hash_password(pw1)
    print()
    print(f"THREAD_AUTH_PASSWORD_HASH={pw_hash}")
    print()
    print("Copy the two lines above into your environment or .env file.")
    print()
    print("Then set THREAD_AUTH_ENABLED=true to enable authentication.")
    print("Default username is 'admin' — set THREAD_AUTH_USERNAME to change it.")


if __name__ == "__main__":
    main()
