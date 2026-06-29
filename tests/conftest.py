"""Shared pytest fixtures for Thread test suite.

Provides:
  temp_db_path — temporary SQLite database file path (auto-cleaned up)
  pool — ConnectionPool with small max_connections for testing
  db — convenience fixture: acquires a connection from pool
  app — Flask app created with test config overrides
  client — Flask test client
  git_manager — GitManager pointed at temp directory
  sample_session — pre-created session in test DB
  sample_entries — pre-created 5 entries in test DB
  search_cache — small SearchCache for unit tests
  tag_cache — TagCache for unit tests
"""

import os
import shutil
import tempfile

import pytest

# Override config before importing app
os.environ["THREAD_DB_PATH"] = ""  # Set dynamically per test
os.environ["THREAD_GIT_BASE"] = ""
os.environ["THREAD_DEBUG"] = "true"
os.environ["THREAD_LOG_LEVEL"] = "ERROR"
os.environ["THREAD_POOL_SIZE"] = "3"
os.environ["THREAD_SEARCH_CACHE_SIZE"] = "8"
os.environ["THREAD_SEARCH_CACHE_TTL"] = "1"
os.environ["THREAD_TAG_CACHE_TTL"] = "1"


@pytest.fixture
def temp_db_path():
    """Creates a temporary file path for a SQLite database.

    The file is deleted after the test (function-scoped).
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # Remove — sqlite3 will create it
    yield path
    # Clean up database + WAL/SHM files
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


@pytest.fixture
def pool(temp_db_path):
    """Pre-warmed ConnectionPool with 3 connections and initialized schema."""
    from thread_server.database import ConnectionPool
    from thread_server.models import init_db

    pool = ConnectionPool(temp_db_path, max_connections=10, timeout=5.0)
    pool.start()
    conn = pool.get()
    init_db(conn)
    yield pool
    pool.close_all()


@pytest.fixture
def db(pool):
    """Returns the current thread's database connection from a pre-warmed pool."""
    return pool.get()


@pytest.fixture
def app(temp_db_path, tmp_path):
    """Flask application with test configuration overrides.

    Uses a temp DB path and temp git base directory. All caches are
    sized small for test isolation.
    """
    os.environ["THREAD_DB_PATH"] = temp_db_path
    os.environ["THREAD_GIT_BASE"] = str(tmp_path / "git")
    os.environ["THREAD_DEBUG"] = "true"
    os.environ["THREAD_LOG_LEVEL"] = "ERROR"
    os.environ["THREAD_POOL_SIZE"] = "3"
    os.environ["THREAD_SEARCH_CACHE_SIZE"] = "8"
    os.environ["THREAD_SEARCH_CACHE_TTL"] = "1"
    os.environ["THREAD_TAG_CACHE_TTL"] = "1"

    from thread_server.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    yield app


@pytest.fixture
def client(app):
    """Flask test client for integration testing."""
    return app.test_client()


@pytest.fixture
def git_manager_path(tmp_path):
    """Temporary directory for GitManager testing."""
    git_path = tmp_path / "git"
    git_path.mkdir(parents=True)
    return str(git_path)


@pytest.fixture
def sample_session(db):
    """Pre-creates a session named 'test-session' and returns it."""
    from thread_server.models import create_session

    return create_session(db, "test-session", "Test session for fixtures")


@pytest.fixture
def sample_entries(db, sample_session):
    """Pre-creates 5 entries in 'test-session' with varying priorities and tags."""
    from thread_server.models import create_entry

    entries = []
    for i in range(5):
        entry = create_entry(
            db,
            sample_session["id"],
            f"Entry {i + 1} — sample content for testing purposes.",
            priority=min(i + 5, 10),
            tags=[f"tag{i}", "common"],
        )
        entries.append(entry)
    return entries


@pytest.fixture
def search_cache():
    """Small SearchCache for unit testing (8 entries, 1s TTL)."""
    from thread_server.cache import SearchCache

    return SearchCache(max_size=8, ttl=1.0)


@pytest.fixture
def tag_cache():
    """TagCache for unit testing (1s TTL)."""
    from thread_server.cache import TagCache

    return TagCache(ttl=1.0)


@pytest.fixture(autouse=True)
def clear_caches():
    """Reset module-level caches before each test for isolation."""
    from thread_server.cache import init_caches

    init_caches()
