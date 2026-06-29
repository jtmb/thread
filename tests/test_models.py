"""Unit tests for data access layer (models.py).

All tests use the `db` fixture which provides a thread-local connection
from a pre-warmed pool with the full schema applied.
"""

import sqlite3

import pytest

from thread_server import models


# ── Sessions ───────────────────────────────────────────────────────────────────


def test_create_session_returns_dict(db):
    """create_session returns a dict with all expected fields."""
    session = models.create_session(db, "test-create", "desc")
    assert session["id"] is not None
    assert session["name"] == "test-create"
    assert session["description"] == "desc"
    assert "created_at" in session
    assert "updated_at" in session


def test_create_session_duplicate_name_raises(db):
    """Creating a session with an existing name raises IntegrityError."""
    models.create_session(db, "dup", "first")
    with pytest.raises(sqlite3.IntegrityError):
        models.create_session(db, "dup", "second")


def test_get_session_by_name_found(db):
    """get_session_by_name returns the correct session dict."""
    models.create_session(db, "find-me", "Look for me")
    session = models.get_session_by_name(db, "find-me")
    assert session is not None
    assert session["name"] == "find-me"
    assert session["description"] == "Look for me"


def test_get_session_by_name_missing(db):
    """get_session_by_name returns None for unknown name."""
    assert models.get_session_by_name(db, "nonexistent") is None


def test_get_session_by_id_found(db):
    """get_session_by_id returns the correct session dict."""
    created = models.create_session(db, "by-id", "")
    session = models.get_session_by_id(db, created["id"])
    assert session is not None
    assert session["id"] == created["id"]


def test_get_session_by_id_missing(db):
    """get_session_by_id returns None for unknown ID."""
    assert models.get_session_by_id(db, 99999) is None


def test_list_sessions_empty(db):
    """list_sessions returns empty list when no sessions exist."""
    assert models.list_sessions(db) == []


def test_list_sessions_returns_all(db):
    """list_sessions returns all created sessions."""
    models.create_session(db, "s1", "")
    models.create_session(db, "s2", "")
    models.create_session(db, "s3", "")
    result = models.list_sessions(db)
    assert len(result) == 3
    names = {s["name"] for s in result}
    assert names == {"s1", "s2", "s3"}


def test_delete_session_removes_row(db):
    """delete_session removes the session."""
    created = models.create_session(db, "to-delete", "")
    assert models.get_session_by_name(db, "to-delete") is not None
    models.delete_session(db, created["id"])
    assert models.get_session_by_name(db, "to-delete") is None


def test_delete_session_cascades_to_entries(db):
    """Deleting a session also deletes all its entries."""
    session = models.create_session(db, "cascade-test", "")
    models.create_entry(db, session["id"], "Some content")
    assert len(models.list_entries(db, session["id"])) == 1
    models.delete_session(db, session["id"])
    # Session gone
    assert models.get_session_by_name(db, "cascade-test") is None


# ── Entries ────────────────────────────────────────────────────────────────────


def test_create_entry_with_all_fields(db, sample_session):
    """create_entry returns dict with content, priority, and tags."""
    entry = models.create_entry(
        db,
        sample_session["id"],
        "Test content",
        priority=8,
        tags=["t1", "t2"],
    )
    assert entry["id"] is not None
    assert entry["content"] == "Test content"
    assert entry["priority"] == 8
    assert entry["tags"] == ["t1", "t2"]


def test_create_entry_default_priority(db, sample_session):
    """create_entry defaults to priority 5."""
    entry = models.create_entry(db, sample_session["id"], "No priority")
    assert entry["priority"] == 5


def test_create_entry_default_tags(db, sample_session):
    """create_entry defaults to empty tags list."""
    entry = models.create_entry(db, sample_session["id"], "No tags")
    assert entry["tags"] == []


def test_create_entry_invalid_priority_raises(db, sample_session):
    """Priority must be 0-10 per CHECK constraint."""
    with pytest.raises((sqlite3.IntegrityError, ValueError)):
        models.create_entry(db, sample_session["id"], "Bad priority", priority=11)


def test_get_entry_found(db, sample_entries):
    """get_entry returns the correct entry dict."""
    entry = models.get_entry(db, sample_entries[0]["id"])
    assert entry is not None
    assert entry["id"] == sample_entries[0]["id"]


def test_get_entry_missing(db):
    """get_entry returns None for unknown ID."""
    assert models.get_entry(db, 99999) is None


def test_list_entries_returns_newest_first(db, sample_entries):
    """list_entries returns entries ordered by created_at DESC."""
    entries = models.list_entries(db, sample_entries[0]["session_id"])
    assert len(entries) == 5
    # IDs should be descending (newest first)
    ids = [e["id"] for e in entries]
    assert ids == sorted(ids, reverse=True)


def test_list_entries_respects_limit(db, sample_entries):
    """list_entries caps results at limit."""
    entries = models.list_entries(
        db, sample_entries[0]["session_id"], limit=2
    )
    assert len(entries) == 2


def test_list_entries_cursor_pagination(db, sample_entries):
    """Cursor pagination returns entries after the given ID (ascending)."""
    sid = sample_entries[0]["session_id"]
    all_entries = models.list_entries(db, sid, limit=100)
    all_ids = [e["id"] for e in all_entries]
    middle_id = all_ids[2]  # 3rd from top

    page = models.list_entries_cursor(db, sid, after_id=middle_id, limit=2)
    assert len(page) <= 2
    # Cursor pagination returns IDs > after_id, ordered ascending
    for entry in page:
        assert entry["id"] > middle_id


def test_get_entries_batch_returns_requested(db, sample_entries):
    """get_entries_batch returns only requested IDs."""
    ids = [sample_entries[0]["id"], sample_entries[2]["id"]]
    result = models.get_entries_batch(db, ids)
    assert len(result) == 2
    result_ids = {e["id"] for e in result}
    assert result_ids == set(ids)


def test_get_entries_batch_partial_missing(db, sample_entries):
    """get_entries_batch silently omits missing IDs."""
    ids = [sample_entries[0]["id"], 99999]
    result = models.get_entries_batch(db, ids)
    assert len(result) == 1
    assert result[0]["id"] == sample_entries[0]["id"]


def test_update_entry_changes_fields(db, sample_entries):
    """update_entry modifies content, priority, and tags."""
    entry = sample_entries[0]
    updated = models.update_entry(
        db,
        entry["id"],
        content="New content",
        priority=9,
        tags=["updated"],
    )
    assert updated["content"] == "New content"
    assert updated["priority"] == 9
    assert updated["tags"] == ["updated"]


def test_update_entry_partial(db, sample_entries):
    """update_entry allows partial updates (only content changed)."""
    entry = sample_entries[0]
    original_priority = entry["priority"]
    updated = models.update_entry(db, entry["id"], content="Partial update")
    assert updated["content"] == "Partial update"
    assert updated["priority"] == original_priority


def test_update_entry_bumps_updated_at(db, sample_entries):
    """update_entry changes the updated_at timestamp."""
    import time

    entry = sample_entries[0]
    original_time = entry["updated_at"]
    # Ensure at least 1 second passes so the timestamp changes
    time.sleep(1.1)
    updated = models.update_entry(db, entry["id"], content="Changed")
    assert updated["updated_at"] != original_time


def test_update_entry_missing(db):
    """update_entry returns None for nonexistent entry."""
    result = models.update_entry(db, 99999, content="Nope")
    assert result is None


def test_delete_entry_removes_row(db, sample_entries):
    """delete_entry removes the entry."""
    entry_id = sample_entries[0]["id"]
    assert models.get_entry(db, entry_id) is not None
    models.delete_entry(db, entry_id)
    assert models.get_entry(db, entry_id) is None


# ── Search ─────────────────────────────────────────────────────────────────────


def test_search_entries_returns_ranked_results(db, sample_entries):
    """search_entries returns results with rank and snippet."""
    sid = sample_entries[0]["session_id"]
    results = models.search_entries(db, sid, "sample content", limit=10)
    assert len(results) > 0
    assert "rank" in results[0]
    assert "snippet" in results[0]


def test_search_entries_empty_query_returns_recent(db, sample_entries):
    """Empty query returns recent entries for the session."""
    sid = sample_entries[0]["session_id"]
    results = models.search_entries(db, sid, "", limit=10)
    assert len(results) > 0


def test_search_entries_prefix_query(db, sample_entries):
    """Prefix queries (with *) match partial words."""
    sid = sample_entries[0]["session_id"]
    results = models.search_entries(db, sid, "sampl*", limit=10)
    assert len(results) > 0


# ── Tags ───────────────────────────────────────────────────────────────────────


def test_get_all_tags_returns_unique(db, sample_entries):
    """get_all_tags returns unique tags across all entries in the session."""
    sid = sample_entries[0]["session_id"]
    tags = models.get_all_tags(db, sid)
    assert "common" in tags
    assert "tag0" in tags
    assert len(tags) == 6  # tag0-4 + "common"


def test_get_all_tags_empty_session(db, sample_session):
    """get_all_tags returns empty list when no entries exist."""
    tags = models.get_all_tags(db, sample_session["id"])
    assert tags == []
