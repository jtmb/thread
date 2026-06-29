#!/usr/bin/env python3
"""Thread server entry point — dev (Flask threaded) or production (Waitress).

Usage:
    # Development (debug mode, auto-reload, Flask threaded server):
    THREAD_DEBUG=true python thread_server/server.py

    # Production (Waitress multi-threaded WSGI):
    python thread_server/server.py

Configuration from environment variables (see config.py for all options):
    THREAD_HOST=0.0.0.0
    THREAD_PORT=5000
    THREAD_DEBUG=false
    THREAD_POOL_SIZE=12
    THREAD_DB_PATH=data/thread.db
    THREAD_LOG_LEVEL=INFO
"""

import logging
import sys

from thread_server import config
from thread_server.app import create_app

logger = logging.getLogger(__name__)


def main() -> None:
    """Create the app and start the server.

    Development mode (THREAD_DEBUG=true): Flask's built-in threaded WSGI server.
        - Auto-reload on code changes
        - Debug toolbar enabled
        - Verbose logging

    Production mode (THREAD_DEBUG=false, the default):
        - Waitress WSGI server with 12 threads
        - Connection limit: 24
        - Single write() per response (send_bytes=1)
        - Graceful shutdown on SIGTERM/SIGINT
    """
    app = create_app()

    if config.DEBUG:
        _run_dev(app)
    else:
        _run_prod(app)


def _run_dev(app) -> None:
    """Run the Flask development server with threading enabled."""
    logger.info(
        "Starting development server on %s:%s (threaded, debug=True)",
        config.HOST,
        config.PORT,
    )
    app.run(
        host=config.HOST,
        port=config.PORT,
        threaded=True,
        debug=True,
    )


def _run_prod(app) -> None:
    """Run the Waitress production WSGI server.

    Waitress is a pure-Python WSGI server with native threading — far lighter
    on a Raspberry Pi than Gunicorn (no master/worker fork overhead).
    """
    from waitress import serve

    logger.info(
        "Starting production server on %s:%s (Waitress, %d threads)",
        config.HOST,
        config.PORT,
        config.POOL_SIZE,
    )
    serve(
        app,
        host=config.HOST,
        port=config.PORT,
        threads=config.POOL_SIZE,
        connection_limit=24,
        channel_timeout=30,
        cleanup_interval=30,
        send_bytes=1,
        url_scheme="http",
    )


if __name__ == "__main__":
    main()
