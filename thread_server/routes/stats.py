"""Server performance metrics endpoint.

Blueprint: stats_bp
URL prefix: /api/v1

Exposes memory-safe in-process counters: uptime, DB size, pool utilization,
cache hit/miss, and request latency stats. All data is approximate (lock-free
counters) — precision is secondary to zero-overhead instrumentation.
"""

import logging
import os

from flask import Blueprint, jsonify

from thread_server import config, stats_collector
from thread_server.stats_collector import get_request_stats, get_uptime_seconds
from thread_server.cache import search_cache, tag_cache
from thread_server import database as db_module

logger = logging.getLogger(__name__)

stats_bp = Blueprint("stats", __name__)

VERSION = "0.1.0"


@stats_bp.route("/api/v1/stats", methods=["GET"])
def server_stats():
    """Return server performance metrics.

    Includes:
    - Server: uptime, version
    - Database: file size, total entries/sessions, WAL size
    - Pool: active/total connections, utilization %
    - Cache: search/tag hit and miss counts
    - Requests: total count, avg latency, p99 latency
    """
    stats = {
        "server": {
            "uptime_seconds": round(get_uptime_seconds(), 1),
            "version": VERSION,
        },
        "db": _get_db_stats(),
        "pool": _get_pool_stats(),
        "cache": _get_cache_stats(),
        "requests": get_request_stats(),
    }
    return jsonify(stats)


def _get_db_stats() -> dict:
    """Gather database file stats from the filesystem + live query."""
    stats = {
        "size_bytes": 0,
        "total_entries": 0,
        "total_sessions": 0,
        "wal_size_bytes": 0,
    }

    db_path = config.DB_PATH
    if os.path.exists(db_path):
        stats["size_bytes"] = os.path.getsize(db_path)

    wal_path = db_path + "-wal"
    if os.path.exists(wal_path):
        stats["wal_size_bytes"] = os.path.getsize(wal_path)

    # Live counts (fast — just table scans of small metadata)
    if db_module.pool:
        try:
            db = db_module.pool.get()
            total_entries = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            total_sessions = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            stats["total_entries"] = total_entries
            stats["total_sessions"] = total_sessions
        except Exception as e:
            logger.warning("Failed to query DB stats: %s", e)

    return stats


def _get_pool_stats() -> dict:
    """Get connection pool utilization stats."""
    if db_module.pool is None:
        return {
            "active_connections": 0,
            "total_connections": 0,
            "max_connections": 0,
            "utilization_pct": 0,
        }

    total = db_module.pool.total_connections
    active = db_module.pool.active_count
    return {
        "active_connections": active,
        "total_connections": total,
        "max_connections": total,
        "utilization_pct": round((active / total * 100) if total > 0 else 0),
    }


def _get_cache_stats() -> dict:
    """Get cache hit/miss counts and sizes."""
    stats = {
        "search_entries": search_cache.size if search_cache else 0,
        "search_max": config.SEARCH_CACHE_SIZE,
        "search_hits": search_cache.hits if search_cache else 0,
        "search_misses": search_cache.misses if search_cache else 0,
    }
    return stats
