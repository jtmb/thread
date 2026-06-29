"""Entry CRUD routes — single, batch, bulk, and file upload operations.

Blueprint: entries_bp
URL prefix: /api/v1/sessions/<session_name>/entries

All routes resolve the session name to an ID before operating.
Cache invalidation happens on every mutation.
"""

import logging

from flask import Blueprint, g, jsonify, make_response, request

from thread_server import config, models
from thread_server.cache import invalidate_caches
from thread_server.chunker import (
    chunk_by_format,
    detect_format,
    is_binary,
)
from thread_server.git_manager import git_manager

logger = logging.getLogger(__name__)

entries_bp = Blueprint("entries", __name__)


def _resolve_session(name: str) -> dict | None:
    """Resolve a session name for read-only endpoints.

    Returns None if the session doesn't exist (caller should return 404).
    """
    db = g.db
    session = models.get_session_by_name(db, name)
    if session is None:
        return None
    g.session_id = session["id"]
    g.session_name = name
    return session


def _resolve_or_create_session(name: str) -> dict | None:
    """Resolve a session, auto-creating it if necessary.

    For mutation endpoints (POST), a missing session is auto-created
    so that agents can start populating entries immediately without
    an explicit session creation step. Read endpoints still 404.

    Returns:
        The session dict, or None on error.
    """
    db = g.db
    session = models.get_session_by_name(db, name)
    if session is not None:
        g.session_id = session["id"]
        g.session_name = name
        return session

    # Auto-create: mutations shouldn't fail just because a session
    # doesn't exist yet — the agent's intent to store is clear.
    try:
        session = models.create_session(db, name)
        g.session_id = session["id"]
        g.session_name = name
        logger.info("Auto-created session '%s' on entry mutation", name)
        return session
    except Exception as e:
        logger.error("Failed to auto-create session '%s': %s", name, e)
        return None


def _error(status: int, code: str, message: str) -> tuple:
    """Build a standardized error response tuple."""
    return (
        jsonify({
            "error": {
                "code": code,
                "message": message,
                "details": [],
                "requestId": getattr(g, "request_id", None),
            }
        }),
        status,
    )


# ── Single Entry CRUD ────────────────────────────────────────────────────────


@entries_bp.route("/api/v1/sessions/<name>/entries", methods=["GET"])
def list_entries(name: str):
    """List entries in a session with cursor-based pagination.

    Query params: ?after=<id>&limit=<int>&sort=asc|desc
    - sort=asc (default): id > after, ORDER BY id ASC (oldest first)
    - sort=desc: id < after, ORDER BY id DESC (newest first).
      For the first page, use a high after value (or omit it — server
      auto-resolves to max_id + 1).
    """
    if not _resolve_session(name):
        return _error(404, "NOT_FOUND", f"Session '{name}' not found")

    db = g.db

    after_id = request.args.get("after", type=int)
    limit = request.args.get(
        "limit", config.DEFAULT_PAGE_SIZE, type=int
    )
    limit = min(limit, config.MAX_PAGE_SIZE)
    sort = request.args.get("sort", "asc", type=str)

    if sort not in ("asc", "desc"):
        return _error(400, "INVALID_SORT", "sort must be 'asc' or 'desc'")

    # When sort=desc and no after cursor, resolve to max_id + 1 to start
    # from the newest entry
    if sort == "desc" and after_id is None:
        row = db.execute(
            "SELECT MAX(id) FROM entries WHERE session_id = ?",
            (g.session_id,),
        ).fetchone()
        max_id = row[0] if row and row[0] else 0
        after_id = max_id + 1

    # Sensible default for asc
    if sort == "asc" and after_id is None:
        after_id = 0

    entries = models.list_entries_cursor(
        db, g.session_id, after_id=after_id, limit=limit, sort=sort
    )

    # Build pagination cursor
    has_more = len(entries) == limit
    if entries:
        next_cursor = entries[-1]["id"] if sort == "asc" else entries[-1]["id"]
    else:
        next_cursor = None

    return jsonify({
        "data": entries,
        "pagination": {
            "cursor": str(next_cursor) if next_cursor else None,
            "hasMore": has_more,
        },
    })


@entries_bp.route("/api/v1/sessions/<name>/entries", methods=["POST"])
def create_entry(name: str):
    """Create a single entry in a session.

    Request body: {"content": "...", "priority": 7, "tags": ["python"]}
    Auto-creates the session if it doesn't already exist.
    Returns 201 Created with the entry object.
    """
    if not _resolve_or_create_session(name):
        return _error(500, "INTERNAL", f"Could not resolve or create session '{name}'")

    body = request.get_json(silent=True)
    if not body:
        return _error(400, "VALIDATION", "Request body must be valid JSON")

    content = body.get("content", "").strip()
    if not content:
        return _error(400, "VALIDATION", "content is required")

    priority = body.get("priority", 5)
    tags = body.get("tags")

    try:
        entry = models.create_entry(g.db, g.session_id, content, priority=priority, tags=tags)
    except ValueError as e:
        return _error(400, "VALIDATION", str(e))

    invalidate_caches(g.session_id)

    # Best-effort git commit
    if git_manager:
        git_manager.commit_entry_added(name, entry["id"])

    response = make_response(jsonify(entry), 201)
    response.headers["Location"] = f"/api/v1/sessions/{name}/entries/{entry['id']}"
    return response


@entries_bp.route("/api/v1/sessions/<name>/entries/<int:entry_id>", methods=["GET"])
def get_entry(name: str, entry_id: int):
    """Get a single entry by ID."""
    if not _resolve_session(name):
        return _error(404, "NOT_FOUND", f"Session '{name}' not found")

    entry = models.get_entry(g.db, entry_id)
    if entry is None or entry["session_id"] != g.session_id:
        return _error(404, "NOT_FOUND", f"Entry {entry_id} not found in session '{name}'")

    return jsonify(entry)


@entries_bp.route("/api/v1/sessions/<name>/entries/<int:entry_id>", methods=["PUT"])
def update_entry(name: str, entry_id: int):
    """Update an existing entry. Only provided fields are changed.

    Request body: {"content": "...", "priority": 8, "tags": ["newtag"]}
    All fields are optional.
    """
    if not _resolve_session(name):
        return _error(404, "NOT_FOUND", f"Session '{name}' not found")

    existing = models.get_entry(g.db, entry_id)
    if existing is None or existing["session_id"] != g.session_id:
        return _error(404, "NOT_FOUND", f"Entry {entry_id} not found in session '{name}'")

    body = request.get_json(silent=True)
    if not body:
        return _error(400, "VALIDATION", "Request body must be valid JSON")

    content = body.get("content")
    priority = body.get("priority")
    tags = body.get("tags")

    try:
        updated = models.update_entry(g.db, entry_id, content=content, priority=priority, tags=tags)
    except ValueError as e:
        return _error(400, "VALIDATION", str(e))

    invalidate_caches(g.session_id)

    # Best-effort git commit
    if git_manager:
        git_manager.commit_entry_updated(name, entry_id)

    return jsonify(updated)


@entries_bp.route("/api/v1/sessions/<name>/entries/<int:entry_id>", methods=["DELETE"])
def delete_entry(name: str, entry_id: int):
    """Delete an entry by ID. Returns 204 No Content."""
    if not _resolve_session(name):
        return _error(404, "NOT_FOUND", f"Session '{name}' not found")

    existing = models.get_entry(g.db, entry_id)
    if existing is None or existing["session_id"] != g.session_id:
        return _error(404, "NOT_FOUND", f"Entry {entry_id} not found in session '{name}'")

    models.delete_entry(g.db, entry_id)
    invalidate_caches(g.session_id)

    # Best-effort git commit
    if git_manager:
        git_manager.commit_entry_deleted(name, entry_id)

    return "", 204


# ── Batch & Bulk Operations ──────────────────────────────────────────────────


@entries_bp.route("/api/v1/sessions/<name>/entries/batch", methods=["POST"])
def batch_read(name: str):
    """Fetch multiple entries by ID in a single round-trip.

    Request: {"ids": [1, 5, 12]}
    Max 100 IDs. Returns list of entries in order.
    """
    if not _resolve_session(name):
        return _error(404, "NOT_FOUND", f"Session '{name}' not found")

    body = request.get_json(silent=True)
    if not body or not isinstance(body.get("ids"), list):
        return _error(400, "VALIDATION", "ids must be a list of integers")

    ids = body["ids"]
    if len(ids) > config.MAX_BULK_SIZE:
        return _error(400, "VALIDATION", f"Batch read limited to {config.MAX_BULK_SIZE} IDs")

    entries = models.get_entries_batch(g.db, ids)
    # Filter to only this session's entries
    entries = [e for e in entries if e["session_id"] == g.session_id]
    return jsonify(entries)


@entries_bp.route("/api/v1/sessions/<name>/entries/bulk", methods=["POST"])
def bulk_create(name: str):
    """Create multiple entries at once.

    Request: {"entries": [{"content": "...", "priority": 7, "tags": [...]}, ...]}
    Max 100 entries. Returns 207 Multi-Status with per-entry results.
    """
    if not _resolve_or_create_session(name):
        return _error(500, "INTERNAL", f"Could not resolve or create session '{name}'")

    body = request.get_json(silent=True)
    if not body or not isinstance(body.get("entries"), list):
        return _error(400, "VALIDATION", "entries must be a list")

    entries_data = body["entries"]
    if len(entries_data) > config.MAX_BULK_SIZE:
        return _error(400, "VALIDATION", f"Bulk create limited to {config.MAX_BULK_SIZE} entries")

    created: list[dict] = []
    errors: list[dict] = []

    for i, entry_data in enumerate(entries_data):
        content = entry_data.get("content", "").strip()
        if not content:
            errors.append({"index": i, "code": "VALIDATION", "message": "content is required"})
            continue

        priority = entry_data.get("priority", 5)
        tags = entry_data.get("tags")

        try:
            entry = models.create_entry(g.db, g.session_id, content, priority=priority, tags=tags)
            created.append(entry)
        except ValueError as e:
            errors.append({"index": i, "code": "VALIDATION", "message": str(e)})

    invalidate_caches(g.session_id)

    # Best-effort git commits for each created entry
    if git_manager:
        for entry in created:
            git_manager.commit_entry_added(name, entry["id"])

    # Use 207 Multi-Status when there are partial failures
    status_code = 207 if errors else 201
    response = make_response(
        jsonify({
            "created": len(created),
            "failed": len(errors),
            "entries": created,
            "errors": errors,
        }),
        status_code,
    )
    return response


# ── File Upload ──────────────────────────────────────────────────────────────


@entries_bp.route("/api/v1/sessions/<name>/entries/upload", methods=["POST"])
def upload_file(name: str):
    """Upload a document file (.md, .txt, .json) and create chunked entries.

    Multipart form fields:
        file: (required) The document to upload
        tags: (optional) Comma-separated tags applied to all chunks
        priority: (optional) Priority 0-10 applied to all chunks (default 5)
        chunk_size: (optional) Target chunk size for .txt files (default 2048)

    Returns 201 with created entries list.
    Returns 413 if file exceeds MAX_UPLOAD_SIZE.
    Returns 415 if format is unsupported or binary.
    """
    if not _resolve_or_create_session(name):
        return _error(500, "INTERNAL", f"Could not resolve or create session '{name}'")

    # Validate file presence
    if "file" not in request.files:
        return _error(400, "VALIDATION", "file is required")

    uploaded = request.files["file"]
    if not uploaded.filename:
        return _error(400, "VALIDATION", "file has no filename")

    # Read file into memory (capped by MAX_UPLOAD_SIZE)
    content_bytes = uploaded.read()
    if len(content_bytes) > config.MAX_UPLOAD_SIZE:
        return _error(413, "TOO_LARGE", f"File exceeds max upload size of {config.MAX_UPLOAD_SIZE // 1024 // 1024}MB")

    # Detect binary files
    if is_binary(content_bytes[:8192]):
        return _error(415, "UNSUPPORTED_MEDIA", "Binary files are not supported")

    # ── Incremental upload: skip already-imported bytes ──
    offset_str = request.form.get("offset", "")
    if offset_str:
        try:
            offset = int(offset_str)
        except ValueError:
            return _error(400, "VALIDATION", "offset must be an integer")
    else:
        # Auto-resolve from tracked file offset (incremental re-uploads)
        tracked = models.get_file_offset(g.db, g.session_id, uploaded.filename)
        offset = tracked if tracked is not None else 0

    if offset < 0:
        return _error(400, "VALIDATION", "offset must be >= 0")
    if offset > len(content_bytes):
        return _error(400, "VALIDATION", "offset exceeds file size")

    # If there's nothing new, return early
    if offset == len(content_bytes):
        return jsonify({
            "filename": uploaded.filename,
            "format": detect_format(uploaded.filename),
            "chunks": 0,
            "entries_created": 0,
            "entries": [],
            "byte_offset": offset,
            "skipped_bytes": 0,
        }), 201

    # Slice from offset. When a manual offset is provided, skip to the next
    # newline boundary so we never start mid-line. Auto-tracked offsets always
    # land at clean boundaries (end of last ingested byte).
    skipped = 0
    if offset > 0 and offset_str:
        remaining = content_bytes[offset:]
        nl_pos = remaining.find(b"\n")
        if nl_pos >= 0:
            skipped = nl_pos + 1  # skip the partial line + its newline
            remaining = remaining[skipped:]
        else:
            return jsonify({
                "filename": uploaded.filename,
                "format": detect_format(uploaded.filename),
                "chunks": 0,
                "entries_created": 0,
                "entries": [],
                "byte_offset": offset,
                "skipped_bytes": len(remaining),
            }), 201
    else:
        remaining = content_bytes[offset:]

    # Decode the new portion
    try:
        text = remaining.decode("utf-8")
    except UnicodeDecodeError:
        return _error(415, "UNSUPPORTED_MEDIA", "File must be UTF-8 encoded text")

    # Detect format from filename
    try:
        fmt = detect_format(uploaded.filename)
    except ValueError as e:
        return _error(415, "UNSUPPORTED_MEDIA", str(e))

    # Parse optional form fields
    tags_str = request.form.get("tags", "")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
    # Auto-tag with the source filename for traceability
    if tags is None:
        tags = []
    tags.append(uploaded.filename)

    priority_str = request.form.get("priority", "5")
    try:
        priority = int(priority_str)
    except ValueError:
        return _error(400, "VALIDATION", "priority must be an integer")

    chunk_size_str = request.form.get("chunk_size", str(config.DEFAULT_PAGE_SIZE))
    try:
        chunk_size = int(chunk_size_str)
    except ValueError:
        chunk_size = 2048

    # Chunk the document
    try:
        chunks = chunk_by_format(text, fmt, chunk_size=chunk_size)
    except ValueError as e:
        return _error(400, "VALIDATION", str(e))

    if not chunks:
        return _error(400, "VALIDATION", "No content found in uploaded file")

    # Create entries from chunks
    created_entries: list[dict] = []
    for chunk in chunks:
        try:
            entry = models.create_entry(
                g.db,
                g.session_id,
                chunk.content,
                priority=priority,
                tags=tags,
            )
            created_entries.append(entry)
        except ValueError as e:
            logger.warning("Failed to create entry from chunk %d: %s", chunk.index, e)

    invalidate_caches(g.session_id)

    # Best-effort git commits for each created entry
    if git_manager:
        for entry in created_entries:
            git_manager.commit_entry_added(name, entry["id"])

    # Track byte offset for incremental re-uploads
    new_offset = len(content_bytes)
    try:
        models.upsert_file_offset(
            g.db,
            g.session_id,
            uploaded.filename,
            byte_offset=new_offset,
            entries_created=len(created_entries),
        )
    except Exception:
        logger.warning("Failed to persist file offset for %s", uploaded.filename, exc_info=True)

    return jsonify({
        "filename": uploaded.filename,
        "format": fmt,
        "chunks": len(chunks),
        "entries_created": len(created_entries),
        "entries": created_entries,
        "byte_offset": new_offset,
        "skipped_bytes": skipped if offset > 0 else 0,
    }), 201
