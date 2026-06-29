"""Data access layer — pure functions that operate on a sqlite3.Connection.

All functions accept `db: sqlite3.Connection` for testability and thread-safety.
Caching is a separate layer (see cache.py) that wraps these functions.
Models don't know about caches — they just query the database.
"""

import json
import logging
import sqlite3

from thread_server import config

logger = logging.getLogger(__name__)

# ── Schema ─────────────────────────────────────────────────────────────────────


def init_db(db: sqlite3.Connection) -> None:
    """Execute the schema DDL. Idempotent — uses IF NOT EXISTS throughout."""
    import os

    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r") as f:
        db.executescript(f.read())
    logger.debug("Schema initialized (or already present)")


# ── Sessions ───────────────────────────────────────────────────────────────────


def create_session(db: sqlite3.Connection, name: str, description: str = "") -> dict:
    """Create a new session.

    Args:
        db: Active database connection.
        name: Unique session name (e.g., 'vscode-cline').
        description: Optional human-readable description.

    Returns:
        Dict with id, name, description, created_at, updated_at.
    """
    db.execute(
        "INSERT INTO sessions (name, description) VALUES (?, ?)",
        (name, description),
    )
    db.commit()
    return get_session_by_name(db, name)  # type: ignore[return-value]


def get_session_by_name(db: sqlite3.Connection, name: str) -> dict | None:
    """Look up a session by its unique name. Uses the covering index.

    This is the single hottest query path — cached via @lru_cache in cache.py.
    """
    row = db.execute("SELECT * FROM sessions WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def get_session_by_id(db: sqlite3.Connection, session_id: int) -> dict | None:
    """Look up a session by primary key."""
    row = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def list_sessions(db: sqlite3.Connection) -> list[dict]:
    """Return all sessions with entry counts, newest first.

    Uses a correlated subquery to count entries per session in a single
    round-trip. The COUNT aggregates on the covering index — no table scan.
    """
    rows = db.execute(
        """SELECT s.*,
                  (SELECT COUNT(*) FROM entries e WHERE e.session_id = s.id) AS entry_count
           FROM sessions s
           ORDER BY s.created_at DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def delete_session(db: sqlite3.Connection, session_id: int) -> bool:
    """Delete a session and all its entries (CASCADE). Returns True if deleted."""
    cur = db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    db.commit()
    return cur.rowcount > 0


# ── File Upload Offsets ────────────────────────────────────────────────────────


def get_file_offset(db: sqlite3.Connection, session_id: int, filename: str) -> int | None:
    """Get the last known byte offset for a file in a session.

    Returns None if the file has never been uploaded to this session.
    """
    row = db.execute(
        "SELECT byte_offset FROM file_uploads WHERE session_id = ? AND filename = ?",
        (session_id, filename),
    ).fetchone()
    return row["byte_offset"] if row else None


def upsert_file_offset(
    db: sqlite3.Connection,
    session_id: int,
    filename: str,
    byte_offset: int,
    entries_created: int = 0,
) -> None:
    """Insert or update the byte-offset tracking row for a file upload.

    Called after every upload so the next incremental upload knows where to resume.
    """
    db.execute(
        """INSERT INTO file_uploads (session_id, filename, byte_offset, entries_created)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(session_id, filename) DO UPDATE SET
               byte_offset = excluded.byte_offset,
               entries_created = entries_created + excluded.entries_created,
               updated_at = datetime('now')""",
        (session_id, filename, byte_offset, entries_created),
    )
    db.commit()


# ── Entries ────────────────────────────────────────────────────────────────────


def _row_to_entry(row: sqlite3.Row) -> dict:
    """Convert a database row to an entry dict with parsed tags."""
    entry = dict(row)
    if "tags" in entry and isinstance(entry["tags"], str):
        entry["tags"] = json.loads(entry["tags"])
    return entry


def create_entry(
    db: sqlite3.Connection,
    session_id: int,
    content: str,
    priority: int = 5,
    tags: list[str] | None = None,
) -> dict:
    """Create a new context entry in the given session.

    Args:
        db: Active database connection.
        session_id: Owning session primary key.
        content: Text content (non-empty, max 100KB).
        priority: Importance score 0-10, default 5.
        tags: Optional string tags list.

    Returns:
        Dict with all entry fields including the new id.

    Raises:
        ValueError: If content is empty or priority out of range.
    """
    if not content or not content.strip():
        raise ValueError("Entry content must not be empty")
    if len(content) > config.MAX_CONTENT_LENGTH:
        raise ValueError(f"Entry content exceeds max length of {config.MAX_CONTENT_LENGTH}")
    if not 0 <= priority <= 10:
        raise ValueError("Priority must be between 0 and 10")
    if tags is not None and len(tags) > 20:
        raise ValueError("Maximum 20 tags per entry")

    tags_json = json.dumps(tags or [])
    cur = db.execute(
        "INSERT INTO entries (session_id, content, priority, tags) VALUES (?, ?, ?, ?)",
        (session_id, content, priority, tags_json),
    )
    db.commit()
    return _row_to_entry(
        db.execute("SELECT * FROM entries WHERE id = ?", (cur.lastrowid,)).fetchone()
    )


def get_entry(db: sqlite3.Connection, entry_id: int) -> dict | None:
    """Get a single entry by primary key."""
    row = db.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    return _row_to_entry(row) if row else None


def list_entries(
    db: sqlite3.Connection,
    session_id: int,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """List entries in a session with offset pagination.

    Prefer list_entries_cursor() for deep pagination — it uses cursor-based
    pagination which is O(log n) instead of OFFSET's O(n).
    """
    limit = limit or config.DEFAULT_PAGE_SIZE
    limit = min(limit, config.MAX_PAGE_SIZE)
    rows = db.execute(
        """SELECT * FROM entries
           WHERE session_id = ?
           ORDER BY created_at DESC, id DESC
           LIMIT ? OFFSET ?""",
        (session_id, limit, offset),
    ).fetchall()
    return [_row_to_entry(r) for r in rows]


def list_entries_cursor(
    db: sqlite3.Connection,
    session_id: int,
    after_id: int = 0,
    limit: int | None = None,
    sort: str = "asc",
) -> list[dict]:
    """List entries using cursor-based pagination — O(log n) via index seek.

    Args:
        db: Active database connection.
        session_id: Session to list entries from.
        after_id: Cursor value. When sort=asc, returns id > after_id.
                  When sort=desc, returns id < after_id (use a high value like
                  current max id + 1 to start from the end).
        limit: Max entries to return (capped at MAX_PAGE_SIZE).
        sort: 'asc' (oldest first, default) or 'desc' (newest first).

    Returns:
        List of entry dicts.
    """
    limit = limit or config.DEFAULT_PAGE_SIZE
    limit = min(limit, config.MAX_PAGE_SIZE)
    if sort == "desc":
        rows = db.execute(
            """SELECT * FROM entries
               WHERE session_id = ? AND id < ?
               ORDER BY id DESC
               LIMIT ?""",
            (session_id, after_id, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT * FROM entries
               WHERE session_id = ? AND id > ?
               ORDER BY id ASC
               LIMIT ?""",
            (session_id, after_id, limit),
        ).fetchall()
    return [_row_to_entry(r) for r in rows]


def get_entries_batch(db: sqlite3.Connection, entry_ids: list[int]) -> list[dict]:
    """Fetch multiple entries by ID in a single query.

    Used by the MCP bridge for batch reads — one round-trip instead of N.
    Max 100 IDs per call.
    """
    if not entry_ids:
        return []
    if len(entry_ids) > config.MAX_BULK_SIZE:
        raise ValueError(f"Batch read limited to {config.MAX_BULK_SIZE} IDs")

    placeholders = ",".join("?" for _ in entry_ids)
    rows = db.execute(
        f"SELECT * FROM entries WHERE id IN ({placeholders}) ORDER BY id",
        entry_ids,
    ).fetchall()
    return [_row_to_entry(r) for r in rows]


def update_entry(
    db: sqlite3.Connection,
    entry_id: int,
    content: str | None = None,
    priority: int | None = None,
    tags: list[str] | None = None,
) -> dict | None:
    """Update an existing entry. Only provided fields are changed.

    Returns the updated entry dict, or None if the entry doesn't exist.
    """
    existing = get_entry(db, entry_id)
    if existing is None:
        return None

    new_content = content if content is not None else existing["content"]
    new_priority = priority if priority is not None else existing["priority"]
    new_tags = json.dumps(tags) if tags is not None else json.dumps(existing["tags"])

    if not 0 <= new_priority <= 10:
        raise ValueError("Priority must be between 0 and 10")

    db.execute(
        """UPDATE entries
           SET content = ?, priority = ?, tags = ?, updated_at = datetime('now')
           WHERE id = ?""",
        (new_content, new_priority, new_tags, entry_id),
    )
    db.commit()
    return get_entry(db, entry_id)


def delete_entry(db: sqlite3.Connection, entry_id: int) -> bool:
    """Delete an entry by ID. Returns True if deleted, False if not found."""
    cur = db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    db.commit()
    return cur.rowcount > 0


# ── Search ─────────────────────────────────────────────────────────────────────


def search_entries(
    db: sqlite3.Connection,
    session_id: int,
    query: str,
    limit: int | None = None,
) -> list[dict]:
    """Full-text search using FTS5 with BM25 ranking.

    Reads directly from entries_fts (external content table backed by entries).
    No JOIN needed — all entry columns are available directly.

    Args:
        db: Active database connection.
        session_id: Session to search within.
        query: FTS5 query string. Supports: plain terms, prefix (pyth*),
               phrase ("context server"), negation (python -java).
        limit: Max results (capped at MAX_SEARCH_RESULTS).

    Returns:
        List of entry dicts with added 'rank' (float) and 'snippet' (str) fields.
    """
    limit = limit or config.MAX_SEARCH_RESULTS
    limit = min(limit, config.MAX_SEARCH_RESULTS)

    if not query or not query.strip():
        # Empty query → return most recent entries
        return list_entries(db, session_id, limit=limit)

    rows = db.execute(
        """SELECT rowid AS id, content, tags, priority, created_at, updated_at, session_id,
                  bm25(entries_fts) AS rank,
                  snippet(entries_fts, 1, '<mark>', '</mark>', '...', 64) AS snippet
           FROM entries_fts
           WHERE entries_fts MATCH ? AND session_id = ?
           ORDER BY rank
           LIMIT ?""",
        (query, session_id, limit),
    ).fetchall()
    return [_row_to_entry(r) for r in rows]


def get_all_tags(db: sqlite3.Connection, session_id: int) -> list[str]:
    """Return all unique tags used in a session.

    Uses SQLite's json_each to extract individual tags from the JSON array.
    """
    rows = db.execute(
        """SELECT DISTINCT json_each.value AS tag
           FROM entries, json_each(entries.tags)
           WHERE entries.session_id = ?
           ORDER BY tag""",
        (session_id,),
    ).fetchall()
    return [r["tag"] for r in rows if r["tag"]]
