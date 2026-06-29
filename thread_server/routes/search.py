"""Search routes — FTS5 full-text search with caching and tag listing.

Blueprint: search_bp
URL prefix: /api/v1/sessions/<session_name>

Search reads directly from entries_fts (external content table) for
zero-JOIN performance. Results cached for 5s to absorb agent re-searches.
"""

import logging

from flask import Blueprint, g, jsonify, request

from thread_server import config, models, cache


logger = logging.getLogger(__name__)

search_bp = Blueprint("search", __name__)


def _resolve_session(name: str) -> dict | None:
    """Resolve a session name before each request. Returns None if not found."""
    db = g.db
    session = models.get_session_by_name(db, name)
    if session is None:
        return None
    g.session_id = session["id"]
    g.session_name = name
    return session


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


@search_bp.route("/api/v1/sessions/<name>/search", methods=["GET"])
def search_entries(name: str):
    """Full-text search entries using FTS5 with BM25 ranking.

    Query params:
        q: Search query (FTS5 syntax: plain terms, pyth*, "context server", -java)
        limit: Max results (default 100)
        cache: Set to 'false' to bypass the 5s TTL cache

    Response includes rank scores and highlighted snippets.
    """
    if not _resolve_session(name):
        return _error(404, "NOT_FOUND", f"Session '{name}' not found")

    db = g.db
    query = request.args.get("q", "").strip()
    limit = request.args.get("limit", config.MAX_SEARCH_RESULTS, type=int)
    limit = min(limit, config.MAX_SEARCH_RESULTS)
    use_cache = request.args.get("cache", "true").lower() != "false"

    cached = False

    # Check the search cache
    if use_cache and cache.search_cache and query:
        cached_results = cache.search_cache.get(g.session_id, query)
        if cached_results is not None:
            cached = True
            if cache.search_cache:
                cache.search_cache.record_hit()
            return jsonify({
                "results": cached_results,
                "query": query,
                "count": len(cached_results),
                "session": name,
                "cached": True,
            })

    if cache.search_cache:
        cache.search_cache.record_miss()

    # Execute the search
    results = models.search_entries(db, g.session_id, query, limit=limit)

    # Cache the results (even empty results are cached to absorb hammering)
    if use_cache and cache.search_cache and query:
        cache.search_cache.set(g.session_id, query, results)

    return jsonify({
        "results": results,
        "query": query,
        "count": len(results),
        "session": name,
        "cached": cached,
    })


@search_bp.route("/api/v1/sessions/<name>/tags", methods=["GET"])
def get_tags(name: str):
    """Return all unique tags used in a session.

    Cached for 30s (TTL) since tags change infrequently.
    """
    if not _resolve_session(name):
        return _error(404, "NOT_FOUND", f"Session '{name}' not found")

    db = g.db

    # Check tag cache
    if cache.tag_cache:
        cached_tags = cache.tag_cache.get(g.session_id)
        if cached_tags is not None:
            return jsonify({"tags": cached_tags, "session": name, "cached": True})

    tags = models.get_all_tags(db, g.session_id)

    if cache.tag_cache:
        cache.tag_cache.set(g.session_id, tags)

    return jsonify({"tags": tags, "session": name, "cached": False})
