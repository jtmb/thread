---
description: "Python conventions for the Thread project — Flask, sqlite3, Waitress, structured logging, and Pi deployment."
applyTo: "**/*.py"
---

# Python Conventions — Thread Project

## Language Target

- Python 3.9+ (Raspberry Pi OS Bookworm ships Python 3.11)
- Type hints mandatory on all public functions: `def foo(x: int) -> str:`
- Use `list[dict]` not `List[Dict]` (PEP 585, Python 3.9+)

## Docstrings — Google-Style Mandatory

Per AGENTS.md: every function, class, and module MUST have a human-readable docstring in Google style.

```python
def create_entry(
    db: sqlite3.Connection,
    session_id: int,
    content: str,
    priority: int = 5,
    tags: list[str] | None = None,
) -> dict:
    """Create a new context entry in the given session.

    Args:
        db: An active SQLite connection from the connection pool.
        session_id: The owning session's primary key.
        content: The entry text content (non-empty, max 100KB).
        priority: Importance score 0-10, default 5.
        tags: Optional list of string tags, max 20, each max 50 chars.

    Returns:
        A dict with all entry fields including the new id.

    Raises:
        ValueError: If content is empty or priority is out of range.
    """
```

## Framework & Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| Flask | 3.x | REST API (app factory pattern) |
| Waitress | 3.x | Production WSGI server (12 threads) |
| sqlite3 | stdlib | Database with FTS5, json1 |
| logging | stdlib | Structured NDJSON logging |
| functools | stdlib | `@lru_cache` for session lookups |
| threading | stdlib | Connection pool, write serialization |
| subprocess | stdlib | Git operations |

## SQLite Performance Pragmas — Apply on Every Connection

```python
PERFORMANCE_PRAGMAS = [
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA cache_size = -100000",    # 100MB page cache
    "PRAGMA mmap_size = 268435456",   # 256MB memory-mapped I/O
    "PRAGMA temp_store = MEMORY",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
]
```

## Caching Strategy

3-tier in-memory caching for agent retrieval speed:
1. **Session LRU**: `@lru_cache(maxsize=512)` on `get_session_by_name` — 95%+ hit rate, sessions change rarely
2. **SearchCache**: Custom TTL dict (5s TTL, 128 entries) — agents re-search identical terms within seconds
3. **TagCache**: Custom TTL dict (30s TTL) — tag lists change with mutations, but exact freshness isn't critical

Cache invalidation: `invalidate_caches(session_id)` called after every write mutation (create/update/delete entry).

## Threading & Connection Pool

- **Waitress** in production with 12 threads
- **Thread-local** SQLite connections via `threading.local()` — one conn per thread, no per-request open/close
- **Write serialization** via single `threading.Lock` — WAL mode means readers never wait
- **Connection cap** via `threading.Semaphore` — blocks up to `THREAD_POOL_TIMEOUT` seconds, then 503
- **Pre-warmed pool**: all connections opened at startup — zero latency on first request

## Structured Logging

- NDJSON format: `{"timestamp": "...", "level": "INFO", "message": "...", "requestId": "..."}`
- Use `logging` module — NEVER `print()` in production code paths
- `requestId` propagated via Flask `g` (set in `before_request`, cleared in `teardown_request`)
- Log to stderr by default (captured by systemd journald)

## Testing

- Framework: `pytest`
- Fixtures in `tests/conftest.py` — pool, app, client, git_manager
- Co-locate tests at repo root `tests/` (multi-package project)
- Test concurrency with `threading` module — simulate concurrent reads/writes

## Deployment

- systemd service (`deploy/thread.service`) with `MemoryMax=800M`, `StandardOutput=journal`
- All config via environment variables (12-factor app config)
- No Docker — bare-metal Pi for minimal overhead
