"""Server-Sent Events endpoint — pushes dashboard metrics in real-time.

Blueprint: events_bp
URL: /api/v1/events

Uses a background thread that polls storage + entry counts every 30 seconds
and pushes to all connected subscribers. Thread-safe subscriber list with
threading.Lock. Subscribers are cleaned up on disconnect.

EventSource doesn't support custom headers, so auth is via ?token= query param.
"""

import json
import logging
import os
import queue
import sqlite3
import threading
import time

from flask import Blueprint, Response, g, request, stream_with_context

from thread_server import config, models, auth as auth_module
from thread_server import database as db_module

logger = logging.getLogger(__name__)

events_bp = Blueprint("events", __name__)

# Subscriber queues — each connected client gets its own queue.
# Protected by _subscribers_lock.
_subscribers: list[queue.Queue] = []
_subscribers_lock = threading.Lock()
_poller_started = False


def _poll_loop():
    """Background thread: poll DB stats every 30s, push to all subscribers.

    Runs until the server shuts down. Subscriber queues are bounded (max 32
    events) — if a client can't keep up, old events are silently dropped.
    """
    logger.info("SSE poller started (interval=%ds)", config.SSE_POLL_INTERVAL)

    while True:
        try:
            _push_stats()
        except Exception:
            logger.exception("SSE poller iteration failed — will retry")

        time.sleep(config.SSE_POLL_INTERVAL)


def _push_stats():
    """Query current stats and push to all connected subscribers."""
    if not db_module.pool:
        return

    # Use a dedicated connection outside the pool — the SSE poller daemon
    # runs in a background thread that outlives the main Waitress thread pool,
    # and the semaphore-based pool only has enough slots for WSGI workers.
    db = None
    try:
        db = _get_dedicated_connection()
        sessions = models.list_sessions(db)
        total_entries = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        total_sessions = len(sessions)

        # Storage size
        db_size = os.path.getsize(config.DB_PATH) if os.path.exists(config.DB_PATH) else 0
        wal_path = config.DB_PATH + "-wal"
        wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0

        event = {
            "db_size_bytes": db_size,
            "wal_size_bytes": wal_size,
            "total_entries": total_entries,
            "total_sessions": total_sessions,
            "sessions": sessions,
            "timestamp": _iso_now(),
        }

        _broadcast("stats_update", event)
    except Exception:
        logger.exception("Error building SSE stats payload")
    # Dedicated connection — not from pool, so no put() needed


def _broadcast(event_type: str, data: dict):
    """Push an event to all connected subscriber queues."""
    payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    with _subscribers_lock:
        dead = []
        for q in _subscribers:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)

        for q in dead:
            _subscribers.remove(q)


def _iso_now() -> str:
    """Current UTC timestamp in ISO-8601 format."""
    import os
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# Dedicated SQLite connection for the SSE poller daemon thread.
# The poller runs in a background thread that outlives Waitress worker threads,
# so it can't use the semaphore-based connection pool (which has fixed slots).
_poller_conn: sqlite3.Connection | None = None
_poller_conn_lock = threading.Lock()


def _get_dedicated_connection():
    """Return a dedicated SQLite connection for the SSE poller daemon thread.

    Opens the connection on first call and caches it for reuse. This connection
    lives outside the main connection pool so it doesn't consume a semaphore slot.
    """
    global _poller_conn
    if _poller_conn is not None:
        return _poller_conn
    with _poller_conn_lock:
        if _poller_conn is not None:
            return _poller_conn
        import sqlite3
        _poller_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _poller_conn.row_factory = sqlite3.Row
        for pragma in config.PRAGMAS:
            _poller_conn.execute(pragma)
        logger.info("SSE poller: dedicated DB connection opened")
    return _poller_conn


@events_bp.route("/api/v1/events", methods=["GET"])
def stream_events():
    """SSE endpoint — streams stats updates every 30s.

    Auth: token via ?token= query param (EventSource can't set headers).
    When auth is disabled, no token is required.

    Response: text/event-stream with events:
      - stats_update: full stats snapshot (db size, sessions, entry counts)
      - heartbeat: every 15s to keep connection alive
    """
    # Auth via query param (EventSource limitation)
    token = request.args.get("token", "")
    if config.AUTH_ENABLED:
        if not token:
            return Response(
                "event: error\ndata: {\"error\":\"Authentication required — add ?token=\"}\n\n",
                status=401,
                mimetype="text/event-stream",
            )
        payload = auth_module.verify_token(token)
        if not payload:
            return Response(
                "event: error\ndata: {\"error\":\"Invalid token\"}\n\n",
                status=401,
                mimetype="text/event-stream",
            )

    # Start the poller thread on first connection
    _ensure_poller()

    client_queue: queue.Queue = queue.Queue(maxsize=32)
    with _subscribers_lock:
        _subscribers.append(client_queue)

    logger.debug("SSE client connected (total subscribers: %d)", len(_subscribers))

    def generate():
        """Generator that yields SSE events for this client."""
        try:
            # Send initial stats immediately
            try:
                db = db_module.pool.get()
                sessions = models.list_sessions(db)
                total_entries = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
                total_sessions = len(sessions)
                db_size = os.path.getsize(config.DB_PATH) if os.path.exists(config.DB_PATH) else 0
                wal_path = config.DB_PATH + "-wal"
                wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
                init_event = {
                    "db_size_bytes": db_size,
                    "wal_size_bytes": wal_size,
                    "total_entries": total_entries,
                    "total_sessions": total_sessions,
                    "sessions": sessions,
                    "timestamp": _iso_now(),
                }
                yield f"event: stats_update\ndata: {json.dumps(init_event)}\n\n"
            except Exception:
                logger.exception("Error sending initial SSE stats")

            # Maintain heartbeat every 15s while subscribed
            last_heartbeat = time.time()
            while True:
                try:
                    msg = client_queue.get(timeout=15)
                    yield msg
                    last_heartbeat = time.time()
                except queue.Empty:
                    # No data in 15s — send heartbeat
                    yield f": heartbeat {_iso_now()}\n\n"
        except GeneratorExit:
            pass
        finally:
            _unsubscribe(client_queue)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


def _ensure_poller():
    """Start the background poller thread if not already running."""
    global _poller_started
    if _poller_started:
        return
    _poller_started = True
    t = threading.Thread(target=_poll_loop, daemon=True, name="sse-poller")
    t.start()


def _unsubscribe(q: queue.Queue):
    """Remove a subscriber queue on disconnect."""
    with _subscribers_lock:
        if q in _subscribers:
            _subscribers.remove(q)
    logger.debug("SSE client disconnected (total subscribers: %d)", len(_subscribers))
