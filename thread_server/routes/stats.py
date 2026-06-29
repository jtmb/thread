"""Server performance metrics and storage statistics endpoint.

Blueprint: stats_bp
URL prefix: /api/v1

Exposes memory-safe in-process counters: uptime, DB size, pool utilization,
cache hit/miss, and request latency stats. Also exposes filesystem-level
storage capacity via shutil.disk_usage on the data directory.

All data is approximate (lock-free counters) — precision is secondary
to zero-overhead instrumentation.
"""

import logging
import os
import shutil

from flask import Blueprint, jsonify

from thread_server import config, cache as cache_module
from thread_server.stats_collector import get_request_stats, get_uptime_seconds
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
    max_workers = db_module.pool._max_connections
    return {
        "active_connections": active,
        "total_connections": total,
        "max_connections": max_workers,
        "utilization_pct": round((active / max_workers * 100) if max_workers > 0 else 0),
    }


def _get_cache_stats() -> dict:
    """Get cache hit/miss counts and sizes."""
    stats = {
        "search_entries": cache_module.search_cache.size if cache_module.search_cache else 0,
        "search_max": config.SEARCH_CACHE_SIZE,
        "search_hits": cache_module.search_cache.hits if cache_module.search_cache else 0,
        "search_misses": cache_module.search_cache.misses if cache_module.search_cache else 0,
    }
    return stats


def _get_storage_stats() -> dict:
    """Get filesystem-level storage capacity and Thread's own footprint.

    Uses shutil.disk_usage() — a single statvfs syscall — for filesystem
    capacity. Thread's own usage is measured by summing the database file,
    WAL file, and git repos directory.

    Returns:
        Dict with filesystem-level free/used/total in bytes/MB/GB,
        plus app_used_bytes/MB/GB for Thread's specific footprint.
        All values are 0 if the data directory doesn't exist.
    """
    data_dir = os.path.dirname(os.path.abspath(config.DB_PATH))

    if not os.path.exists(data_dir):
        logger.warning("Data directory does not exist: %s", data_dir)
        return {
            "free_bytes": 0, "used_bytes": 0, "total_bytes": 0,
            "free_mb": 0, "used_mb": 0, "total_mb": 0,
            "free_gb": 0, "used_gb": 0, "total_gb": 0,
            "app_used_bytes": 0, "app_used_mb": 0, "app_used_gb": 0,
        }

    usage = shutil.disk_usage(data_dir)
    mb = 1024 * 1024
    gb = 1024 * 1024 * 1024

    # Thread's own footprint: database + WAL + git repos
    app_bytes = _sum_directory(data_dir)

    return {
        "free_bytes": usage.free,
        "used_bytes": usage.used,
        "total_bytes": usage.total,
        "free_mb": round(usage.free / mb),
        "used_mb": round(usage.used / mb),
        "total_mb": round(usage.total / mb),
        "free_gb": round(usage.free / gb, 1),
        "used_gb": round(usage.used / gb, 1),
        "total_gb": round(usage.total / gb, 1),
        "app_used_bytes": app_bytes,
        "app_used_mb": round(app_bytes / mb),
        "app_used_gb": round(app_bytes / gb, 1),
    }


def _sum_directory(path: str) -> int:
    """Recursively sum file sizes in a directory tree.

    Returns the total byte count of all regular files.
    Returns 0 if the path doesn't exist.
    """
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
            elif entry.is_dir(follow_symlinks=False):
                total += _sum_directory(entry.path)
    except OSError:
        pass
    return total


# ── Storage Stats Route ────────────────────────────────────────────────────


@stats_bp.route("/api/v1/stats/storage", methods=["GET"])
def storage_stats():
    """Return filesystem and Thread-specific storage statistics.

    Measures the filesystem hosting the database and git repos,
    plus Thread's own footprint (DB + WAL + git repos summed).

    No query parameters required.

    Filesystem fields: free_bytes, used_bytes, total_bytes (+ _mb, _gb)
    Thread footprint: app_used_bytes (+ _mb, _gb)
    """
    return jsonify(_get_storage_stats())
