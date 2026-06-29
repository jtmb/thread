"""HTTP client for the Thread server API.

Uses requests.Session for TCP connection reuse (HTTP keep-alive).
All calls include timeouts — hangs are worse than failures.

Performance:
- Session object reuses connections (one TCP handshake per thread)
- Batch read uses a single POST for multiple entry IDs
- Search includes cache=false option for agents needing fresh results
"""

import logging
import os
from typing import Any

import requests

from thread_bridge import config

logger = logging.getLogger(__name__)

# Module-level requests Session — connection reuse across calls
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Return (or create) the shared requests Session."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
    return _session


def _url(path: str) -> str:
    """Build a full server URL from a path."""
    return f"{config.THREAD_SERVER_URL.rstrip('/')}{path}"


def _handle_response(resp: requests.Response) -> Any:
    """Parse the response and raise on HTTP errors.

    Returns the parsed JSON body on success.
    Raises requests.HTTPError with embedded error info on failure.
    """
    if resp.status_code == 204:
        return None

    try:
        data = resp.json()
    except ValueError:
        resp.raise_for_status()
        return None

    if resp.ok:
        return data

    # Build a meaningful error from the standardized error shape
    error = data.get("error", {})
    msg = error.get("message", resp.reason or "Unknown error")
    code = error.get("code", "UNKNOWN")
    raise requests.HTTPError(
        f"{resp.status_code} {code}: {msg}",
        response=resp,
    )


# ── Sessions ────────────────────────────────────────────────────────────────


def list_sessions() -> list[dict]:
    """List all sessions on the server."""
    resp = _get_session().get(
        _url("/api/v1/sessions"),
        timeout=config.THREAD_REQUEST_TIMEOUT,
    )
    return _handle_response(resp)


def create_session(name: str, description: str = "") -> dict:
    """Create a new session on the server.

    Args:
        name: Unique session name (required).
        description: Optional human-readable description.

    Returns:
        The created session dict.

    Raises:
        requests.HTTPError: 409 CONFLICT if the session name already exists.
    """
    body = {"name": name, "description": description}
    resp = _get_session().post(
        _url("/api/v1/sessions"),
        json=body,
        timeout=config.THREAD_REQUEST_TIMEOUT,
    )
    return _handle_response(resp)


def get_session(name: str) -> dict | None:
    """Get a session by name. Returns None if not found."""
    resp = _get_session().get(
        _url(f"/api/v1/sessions/{name}"),
        timeout=config.THREAD_REQUEST_TIMEOUT,
    )
    if resp.status_code == 404:
        return None
    return _handle_response(resp)


# ── Entries ─────────────────────────────────────────────────────────────────


def create_entry(
    session: str,
    content: str,
    priority: int = 5,
    tags: list[str] | None = None,
) -> dict:
    """Create a new entry in the given session.

    Returns the created entry dict with id.
    """
    body = {"content": content, "priority": priority}
    if tags:
        body["tags"] = tags

    resp = _get_session().post(
        _url(f"/api/v1/sessions/{session}/entries"),
        json=body,
        timeout=config.THREAD_REQUEST_TIMEOUT,
    )
    return _handle_response(resp)


def read_entries(
    session: str,
    limit: int = 50,
    after: int | None = None,
) -> list[dict]:
    """Read entries from a session with cursor-based pagination.

    Args:
        session: Session name.
        limit: Max entries to return (server capped).
        after: Return entries with id > this value (cursor).

    Returns:
        List of entry dicts.
    """
    params = {"limit": limit}
    if after:
        params["after"] = after

    resp = _get_session().get(
        _url(f"/api/v1/sessions/{session}/entries"),
        params=params,
        timeout=config.THREAD_REQUEST_TIMEOUT,
    )
    data = _handle_response(resp)
    return data.get("data", []) if isinstance(data, dict) else data


def read_entries_batch(session: str, entry_ids: list[int]) -> list[dict]:
    """Fetch multiple entries by ID in a single HTTP call.

    Args:
        session: Session name.
        entry_ids: List of entry IDs (max 100).

    Returns:
        List of entry dicts (only those found in this session).
    """
    resp = _get_session().post(
        _url(f"/api/v1/sessions/{session}/entries/batch"),
        json={"ids": entry_ids},
        timeout=config.THREAD_REQUEST_TIMEOUT,
    )
    return _handle_response(resp)


def update_entry(
    session: str,
    entry_id: int,
    content: str | None = None,
    priority: int | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Update an existing entry. Only provided fields are changed.

    Returns the updated entry dict.
    """
    body: dict[str, Any] = {}
    if content is not None:
        body["content"] = content
    if priority is not None:
        body["priority"] = priority
    if tags is not None:
        body["tags"] = tags

    resp = _get_session().put(
        _url(f"/api/v1/sessions/{session}/entries/{entry_id}"),
        json=body,
        timeout=config.THREAD_REQUEST_TIMEOUT,
    )
    return _handle_response(resp)


def delete_entry(session: str, entry_id: int) -> bool:
    """Delete an entry by ID. Returns True if deleted (204), False otherwise."""
    resp = _get_session().delete(
        _url(f"/api/v1/sessions/{session}/entries/{entry_id}"),
        timeout=config.THREAD_REQUEST_TIMEOUT,
    )
    if resp.status_code == 204:
        return True
    if resp.status_code == 404:
        return False
    _handle_response(resp)
    return False


# ── Search ──────────────────────────────────────────────────────────────────


def search_entries(
    session: str,
    query: str,
    limit: int = 100,
    use_cache: bool = True,
) -> list[dict]:
    """Full-text search entries in a session.

    Args:
        session: Session name.
        query: FTS5 search query string.
        limit: Max results.
        use_cache: Use server-side cache (True) or bypass for fresh results.

    Returns:
        List of entry dicts with rank and snippet fields.
    """
    params = {
        "q": query,
        "limit": limit,
    }
    if not use_cache:
        params["cache"] = "false"

    resp = _get_session().get(
        _url(f"/api/v1/sessions/{session}/search"),
        params=params,
        timeout=config.THREAD_REQUEST_TIMEOUT,
    )
    data = _handle_response(resp)
    return data.get("results", []) if isinstance(data, dict) else data


def get_tags(session: str) -> list[str]:
    """Get all unique tags in a session."""
    resp = _get_session().get(
        _url(f"/api/v1/sessions/{session}/tags"),
        timeout=config.THREAD_REQUEST_TIMEOUT,
    )
    data = _handle_response(resp)
    return data.get("tags", []) if isinstance(data, dict) else data


# ── Bulk & Upload ───────────────────────────────────────────────────────────


def bulk_create_entries(
    session: str,
    entries: list[dict],
) -> dict:
    """Create multiple entries at once (max 100).

    Args:
        session: Session name.
        entries: List of dicts with content, priority, tags keys.

    Returns:
        Dict with created, failed, entries, errors fields.
    """
    resp = _get_session().post(
        _url(f"/api/v1/sessions/{session}/entries/bulk"),
        json={"entries": entries},
        timeout=config.THREAD_REQUEST_TIMEOUT,
    )
    return _handle_response(resp)


def upload_file(
    session: str,
    file_path: str,
    tags: str = "",
    priority: int = 5,
    chunk_size: int = 2048,
) -> dict:
    """Upload and chunk a local file to the server.

    Reads the file from disk and sends it as multipart/form-data.
    The server detects format (.md/.txt/.json/.jsonl/.messages.json), chunks, and creates entries.

    Args:
        session: Session name.
        file_path: Absolute or relative path to the file on disk.
        tags: Comma-separated tags applied to all chunks.
        priority: Priority for all created entries.
        chunk_size: Target chunk size for .txt files.

    Returns:
        Dict with filename, format, chunks, entries_created, entries.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f)}
        data = {
            "tags": tags,
            "priority": str(priority),
            "chunk_size": str(chunk_size),
        }
        resp = requests.post(
            _url(f"/api/v1/sessions/{session}/entries/upload"),
            files=files,
            data=data,
            # Don't use the shared session for multipart — different Content-Type
            timeout=config.THREAD_REQUEST_TIMEOUT * 2,  # Upload may be slower
        )

    return _handle_response(resp)


# ── Stats ───────────────────────────────────────────────────────────────────


def get_stats() -> dict:
    """Get server performance metrics."""
    resp = _get_session().get(
        _url("/api/v1/stats"),
        timeout=config.THREAD_REQUEST_TIMEOUT,
    )
    return _handle_response(resp)
