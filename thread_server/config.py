"""Centralized configuration — the single source of truth for all settings.

AGENTS.md rule: One config module. All env vars and defaults live here.
No os.environ calls scattered across the codebase.
"""

import os

# ── Server ────────────────────────────────────────────────────────────────────
HOST: str = os.environ.get("THREAD_HOST", "0.0.0.0")
PORT: int = int(os.environ.get("THREAD_PORT", "5000"))
DB_PATH: str = os.environ.get("THREAD_DB_PATH", "data/thread.db")
GIT_BASE: str = os.environ.get("THREAD_GIT_BASE", "data/git/")
LOG_LEVEL: str = os.environ.get("THREAD_LOG_LEVEL", "INFO").upper()
LOG_FILE: str = os.environ.get("THREAD_LOG_FILE", "")  # Empty = stderr
DEBUG: bool = os.environ.get("THREAD_DEBUG", "false").lower() in ("true", "1", "yes")

# ── Thread Pool ───────────────────────────────────────────────────────────────
POOL_SIZE: int = int(os.environ.get("THREAD_POOL_SIZE", "12"))
POOL_TIMEOUT: float = float(os.environ.get("THREAD_POOL_TIMEOUT", "10"))

# ── SQLite Performance Pragmas (applied per connection) ────────────────────────
# 100MB page cache keeps hot pages in RAM — 3-10x faster repeated reads
SQLITE_CACHE_SIZE: int = -100_000
# 256MB memory-mapped I/O bypasses read() syscalls — critical for FTS5 speed
SQLITE_MMAP_SIZE: int = 268_435_456
PRAGMAS: list[str] = [
    f"PRAGMA journal_mode = WAL",
    f"PRAGMA synchronous = NORMAL",
    f"PRAGMA cache_size = {SQLITE_CACHE_SIZE}",
    f"PRAGMA mmap_size = {SQLITE_MMAP_SIZE}",
    f"PRAGMA temp_store = MEMORY",
    f"PRAGMA foreign_keys = ON",
    f"PRAGMA busy_timeout = 5000",
]

# ── Caching ───────────────────────────────────────────────────────────────────
SESSION_CACHE_SIZE: int = int(os.environ.get("THREAD_CACHE_SIZE", "512"))
SEARCH_CACHE_SIZE: int = int(os.environ.get("THREAD_SEARCH_CACHE_SIZE", "128"))
SEARCH_CACHE_TTL: float = float(os.environ.get("THREAD_SEARCH_CACHE_TTL", "5"))
TAG_CACHE_TTL: float = float(os.environ.get("THREAD_TAG_CACHE_TTL", "30"))

# ── Query Limits ──────────────────────────────────────────────────────────────
MAX_SEARCH_RESULTS: int = int(os.environ.get("THREAD_MAX_SEARCH_RESULTS", "100"))
DEFAULT_PAGE_SIZE: int = int(os.environ.get("THREAD_DEFAULT_PAGE_SIZE", "50"))
MAX_PAGE_SIZE: int = int(os.environ.get("THREAD_MAX_PAGE_SIZE", "200"))
MAX_BULK_SIZE: int = 100  # Max entries per bulk create request
MAX_CONTENT_LENGTH: int = 100_000  # 100KB max per entry content
MAX_UPLOAD_SIZE: int = 4 * 1024 * 1024  # 4MB max file upload

# ── Runtime State ─────────────────────────────────────────────────────────────
# _start_time is set by stats_collector.record_request_start()
_start_time: float = 0.0


def validate() -> None:
    """Validate all required configuration at startup. Fail fast if something is wrong."""
    if POOL_SIZE < 1:
        raise ValueError("THREAD_POOL_SIZE must be >= 1")
    if POOL_TIMEOUT <= 0:
        raise ValueError("THREAD_POOL_TIMEOUT must be > 0")
    if MAX_PAGE_SIZE > 1000:
        raise ValueError("THREAD_MAX_PAGE_SIZE must be <= 1000")
    if LOG_LEVEL not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise ValueError(f"Invalid THREAD_LOG_LEVEL: {LOG_LEVEL}")
