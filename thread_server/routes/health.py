"""Health check endpoint — for load balancers, monitoring, and debug info.

Blueprint: health_bp, URL prefix: none (registered at root)
Route: GET /api/v1/health
"""

import logging
import os

from flask import Blueprint, jsonify, request

from thread_server import config
from thread_server import database as db_module
from thread_server.stats_collector import get_uptime_seconds

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__)

VERSION = "0.1.0"


@health_bp.route("/api/v1/health", methods=["GET"])
def health_check():
    """Return server health status.

    In debug mode, includes extra diagnostics: pool usage, database file size.
    Production responses are minimal to avoid leaking internal state.
    """
    response = {
        "status": "ok",
        "timestamp": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "version": VERSION,
    }

    if config.DEBUG:
        response["debug"] = _get_debug_info()

    return jsonify(response)


def _get_debug_info() -> dict:
    """Collect debug diagnostics for the health endpoint.

    Only included when THREAD_DEBUG=true — never in production.
    """
    info: dict = {}

    # Pool stats
    if db_module.pool:
        info["pool"] = {
            "active_connections": db_module.pool.active_count,
            "total_connections": db_module.pool.total_connections,
        }

    # Database file size
    db_path = config.DB_PATH
    if os.path.exists(db_path):
        info["db_size_bytes"] = os.path.getsize(db_path)

    # Uptime
    info["uptime_seconds"] = round(get_uptime_seconds(), 1)

    return info
