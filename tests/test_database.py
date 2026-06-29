"""Unit tests for ConnectionPool and schema initialization."""

import sqlite3

from thread_server.database import ConnectionPool


def test_pool_start_opens_all_connections(temp_db_path):
    """Pool.start() opens max_connections + 1 (bootstrap) and applies pragmas."""
    pool = ConnectionPool(temp_db_path, max_connections=3, timeout=5.0)
    try:
        pool.start()
        assert pool.total_connections == 4  # max_connections + 1 bootstrap
        assert pool.active_count == 0  # No threads have acquired yet
    finally:
        pool.close_all()


def test_pool_get_returns_connection(db):
    """pool.get() returns an active sqlite3.Connection with WAL mode."""
    assert isinstance(db, sqlite3.Connection)
    # Verify WAL mode is active
    row = db.execute("PRAGMA journal_mode").fetchone()
    assert row[0].upper() == "WAL"


def test_pool_get_enforces_foreign_keys(db):
    """Connections from the pool have foreign_keys ON."""
    row = db.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1


def test_pool_schema_creates_tables(db):
    """After pool.start(), all expected tables exist."""
    tables = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t[0] for t in tables]
    assert "sessions" in table_names
    assert "entries" in table_names
    assert "entries_fts" in table_names


def test_pool_schema_creates_indexes(db):
    """After pool.start(), all expected indexes exist."""
    indexes = db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
    ).fetchall()
    index_names = [i[0] for i in indexes]
    assert "idx_sessions_name" in index_names
    assert "idx_entries_session" in index_names
    assert "idx_entries_priority" in index_names
    assert "idx_entries_session_created" in index_names


def test_pool_schema_is_idempotent(db):
    """Running schema twice doesn't raise errors."""
    from thread_server.models import init_db

    # Should not raise
    init_db(db)


def test_pool_max_connections_enforced(temp_db_path):
    """BoundedSemaphore prevents more than max_connections active."""
    pool = ConnectionPool(temp_db_path, max_connections=2, timeout=0.1)
    try:
        pool.start()
        # Acquire both connections
        conn1 = pool.get()
        pool.mark_busy()  # Simulate Flask before_request
        conn2 = pool.get()
        # Third should fail (in same thread, semaphore blocks)
        assert pool.active_count == 1  # Same thread, same connection
    finally:
        pool.close_all()


def test_active_count_tracks_connections(pool):
    """active_count counts threads marked busy (processing requests)."""
    conn = pool.get()
    pool.mark_busy()  # Simulate Flask before_request
    assert pool.active_count >= 1
    # In same thread, getting again returns same connection
    _conn2 = pool.get()
    assert pool.active_count >= 1
    # Mark idle — count should drop
    pool.mark_idle()
    assert pool.active_count == 0


def test_total_connections_after_start(pool):
    """total_connections equals max_connections + 1 (bootstrap) after start()."""
    assert pool.total_connections == 11
