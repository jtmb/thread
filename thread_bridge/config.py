"""Bridge configuration — defaults and environment variable loading.

The bridge runs on the workstation, not the Pi. It connects to the Thread
server via HTTP. All config is read from process environment variables.
"""

import os

# Required: HTTP endpoint of the Thread server on the Raspberry Pi
THREAD_SERVER_URL: str = os.environ.get("THREAD_SERVER_URL", "http://localhost:5000")

# Default session name used when none is specified in tool calls
THREAD_DEFAULT_SESSION: str = os.environ.get("THREAD_DEFAULT_SESSION", "default")

# HTTP request timeout in seconds
THREAD_REQUEST_TIMEOUT: float = float(os.environ.get("THREAD_REQUEST_TIMEOUT", "10"))

# Max entries to return per search or list operation
THREAD_DEFAULT_LIMIT: int = int(os.environ.get("THREAD_DEFAULT_LIMIT", "50"))

# Max entries per batch read
THREAD_BATCH_MAX: int = 100


def validate() -> None:
    """Validate required configuration. Fail fast if critical values are missing."""
    if not THREAD_SERVER_URL:
        raise ValueError("THREAD_SERVER_URL is required")
    if THREAD_REQUEST_TIMEOUT <= 0:
        raise ValueError("THREAD_REQUEST_TIMEOUT must be > 0")
