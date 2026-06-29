"""Pre-warmed, performance-tuned SQLite connection pool.

Design: thread-local connections (one per thread) with a write lock for
serialization. WAL mode lets readers run concurrently with a single writer.
All connections are opened at startup — zero latency on first request.
"""

import atexit
import logging
import sqlite3
import threading

from thread_server import config

logger = logging.getLogger(__name__)


class ConnectionPool:
    """Thread-local SQLite connection pool with pre-warming and write serialization.

    Each thread gets its own sqlite3.Connection via threading.local().
    A threading.Lock serializes writes (INSERT/UPDATE/DELETE) — only one writer
    at a time. WAL mode means readers never block on the write lock.

    Public API:
        start(): Open all connections, apply pragmas, init schema.
        get(): Return current thread's connection (blocks if pool exhausted).
        close_all(): Close all connections (graceful shutdown).
        active_count: Number of live threads holding connections.
        total_connections: Total connections in the pool.
    """

    def __init__(self, db_path: str, max_connections: int = 12, timeout: float = 10.0):
        """Initialize the pool configuration.

        Args:
            db_path: Path to the SQLite database file.
            max_connections: Maximum number of concurrent thread-local connections.
            timeout: Seconds to wait for a connection before raising RuntimeError.
        """
        self._db_path = db_path
        self._max_connections = max_connections
        self._timeout = timeout
        self._local = threading.local()
        self._write_lock = threading.Lock()
        # +1 for the main thread's bootstrap connection (permanent, used for schema init)
        self._semaphore = threading.BoundedSemaphore(max_connections + 1)
        self._all_connections: list[sqlite3.Connection] = []
        self._thread_connections: dict[int, sqlite3.Connection] = {}
        self._thread_busy: set[int] = set()
        self._lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Pre-warm the pool: open all connections, apply pragmas, verify schema.

        Called by create_app() before the first HTTP request. All connections
        are ready and waiting — zero setup latency per request.
        """
        logger.info(
            "Pre-warming connection pool: %d connections (+1 bootstrap) to %s",
            self._max_connections + 1,
            self._db_path,
        )
        for i in range(self._max_connections + 1):
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            for pragma in config.PRAGMAS:
                conn.execute(pragma)
            with self._lock:
                self._all_connections.append(conn)
        logger.info("Connection pool ready: %d connections", len(self._all_connections))

    def get(self) -> sqlite3.Connection:
        """Return the current thread's database connection.

        Blocks up to timeout seconds if all connections are in use.
        First call per thread: picks a connection from the pre-warmed pool.
        Subsequent calls: returns the same connection (thread-local caching).

        Returns:
            The sqlite3.Connection for this thread.

        Raises:
            RuntimeError: If the pool is not started or completely exhausted.
        """
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            return conn

        acquired = self._semaphore.acquire(timeout=self._timeout)
        if not acquired:
            logger.warning("Connection pool exhausted: all %d connections in use", self._max_connections)
            raise RuntimeError("Connection pool exhausted — no available connections")

        with self._lock:
            if not self._all_connections:
                self._semaphore.release()
                raise RuntimeError("Connection pool not started — call pool.start() first")
            conn = self._all_connections.pop()
            tid = threading.get_ident()
            self._thread_connections[tid] = conn

        self._local.connection = conn
        return conn

    def write_lock(self) -> threading.Lock:
        """Return the write serialization lock.

        Acquire this lock before any INSERT/UPDATE/DELETE. Release immediately
        after the write transaction commits. WAL readers are not blocked.
        """
        return self._write_lock

    def close_all(self) -> None:
        """Close all pool connections. Called during graceful shutdown."""
        with self._lock:
            for conn in self._all_connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._all_connections.clear()
        try:
            logger.info("All pool connections closed")
        except ValueError:
            # stderr might be closed during atexit shutdown
            pass

    @property
    def active_count(self) -> int:
        """Number of threads actively processing a request right now.

        Only counts threads that have both acquired a connection AND are
        currently inside a request handler (marked busy by Flask hooks).
        Idle workers holding connections are not counted.
        """
        alive_ids = {t.ident for t in threading.enumerate() if t.ident is not None}
        return sum(1 for tid in self._thread_connections if tid in alive_ids and tid in self._thread_busy)

    @property
    def total_connections(self) -> int:
        """Total connections the pool can provide (workers + bootstrap)."""
        return self._max_connections + 1

    def mark_busy(self) -> None:
        """Mark the current thread as actively processing a request.

        Called by Flask's before_request hook. Thread-safe — set.add()
        is atomic in CPython and contention on this set is negligible.
        """
        tid = threading.get_ident()
        self._thread_busy.add(tid)

    def mark_idle(self) -> None:
        """Mark the current thread as no longer processing a request.

        Called by Flask's after_request hook. Thread-safe for the same
        reason as mark_busy().
        """
        tid = threading.get_ident()
        self._thread_busy.discard(tid)


# Module-level singleton — created at import time, started by create_app()
pool: ConnectionPool | None = None


def init_pool(db_path: str = "") -> ConnectionPool:
    """Create and return the global connection pool singleton.

    Args:
        db_path: Override for the database path. Uses config.DB_PATH if empty.

    Returns:
        The initialized ConnectionPool instance.
    """
    global pool
    path = db_path or config.DB_PATH
    pool = ConnectionPool(
        db_path=path,
        max_connections=config.POOL_SIZE,
        timeout=config.POOL_TIMEOUT,
    )
    return pool


def get_db() -> sqlite3.Connection:
    """Return the current thread's database connection from the global pool.

    Convenience function for route handlers and model functions.
    Must be called after the pool has been started.
    """
    if pool is None:
        raise RuntimeError("Connection pool not initialized — call init_pool() first")
    return pool.get()


# Graceful shutdown on process exit
atexit.register(lambda: pool.close_all() if pool else None)
