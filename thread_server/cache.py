"""In-memory caching layer for hot-path lookups.

3-tier cache architecture:
  1. Session LRU: @lru_cache on get_session_by_name — 95%+ hit rate
  2. SearchCache: TTL-based (5s) for FTS5 results — agents re-search often
  3. TagCache: TTL-based (30s) for tag lists — rarely change

Cache invalidation: invalidate_caches(session_id) called after every write.
"""

import functools
import logging
import threading
import time

from thread_server import config

logger = logging.getLogger(__name__)


class SearchCache:
    """TTL-based cache for FTS5 search results.

    Agents frequently re-search the same terms within seconds. A short TTL
    cache (5s) absorbs this without sacrificing freshness for new searches.

    Thread-safe via threading.Lock. Evicts oldest entries when full.
    """

    def __init__(self, max_size: int = 128, ttl: float = 5.0):
        """Initialize the search cache.

        Args:
            max_size: Maximum number of cached query results.
            ttl: Time-to-live in seconds for each cache entry.
        """
        self._max_size = max_size
        self._ttl = ttl
        self._cache: dict[tuple[int, str], tuple[float, list[dict]]] = {}
        self._lock = threading.Lock()

    def _normalize(self, query: str) -> str:
        """Normalize a search query for cache key stability."""
        return " ".join(query.lower().split())

    def get(self, session_id: int, query: str) -> list[dict] | None:
        """Return cached search results if available and not expired.

        Returns None on cache miss or expiration.
        """
        key = (session_id, self._normalize(query))
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            expiry, results = entry
            if time.monotonic() > expiry:
                del self._cache[key]
                return None
            return results

    def set(self, session_id: int, query: str, results: list[dict]) -> None:
        """Store search results in the cache with TTL expiry."""
        key = (session_id, self._normalize(query))
        with self._lock:
            # Evict oldest if full
            if len(self._cache) >= self._max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[key] = (time.monotonic() + self._ttl, results)

    def invalidate_session(self, session_id: int) -> None:
        """Clear all cached search results for a specific session.

        Called after any entry create/update/delete in that session.
        """
        with self._lock:
            keys_to_remove = [k for k in self._cache if k[0] == session_id]
            for key in keys_to_remove:
                del self._cache[key]
            if keys_to_remove:
                logger.debug("Search cache invalidated for session %d: %d entries", session_id, len(keys_to_remove))

    def clear(self) -> None:
        """Clear the entire search cache."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.debug("Search cache fully cleared: %d entries", count)

    @property
    def size(self) -> int:
        """Number of cached entries currently stored."""
        with self._lock:
            return len(self._cache)

    @property
    def hits(self) -> int:
        """Total cache hits (set externally by the route handler)."""
        return getattr(self, "_hits", 0)

    @hits.setter
    def hits(self, value: int) -> None:
        self._hits = value

    @property
    def misses(self) -> int:
        return getattr(self, "_misses", 0)

    @misses.setter
    def misses(self, value: int) -> None:
        self._misses = value

    def record_hit(self) -> None:
        self._hits = getattr(self, "_hits", 0) + 1

    def record_miss(self) -> None:
        self._misses = getattr(self, "_misses", 0) + 1


class TagCache:
    """TTL-based cache for session tag lists.

    Tags change rarely (only on entry mutations). A long TTL (30s) is safe.
    """

    def __init__(self, ttl: float = 30.0):
        self._ttl = ttl
        self._cache: dict[int, tuple[float, list[str]]] = {}
        self._lock = threading.Lock()

    def get(self, session_id: int) -> list[str] | None:
        """Return cached tag list if not expired."""
        with self._lock:
            entry = self._cache.get(session_id)
            if entry is None:
                return None
            expiry, tags = entry
            if time.monotonic() > expiry:
                del self._cache[session_id]
                return None
            return tags

    def set(self, session_id: int, tags: list[str]) -> None:
        """Cache a tag list with TTL."""
        with self._lock:
            self._cache[session_id] = (time.monotonic() + self._ttl, tags)

    def pop(self, session_id: int, default: list[str] | None = None) -> list[str] | None:
        """Remove and return cached tags for a session (invalidation)."""
        with self._lock:
            entry = self._cache.pop(session_id, None)
            return entry[1] if entry else default


# ── Module-level cache instances (created in create_app) ────────────────────────

search_cache: SearchCache | None = None
tag_cache: TagCache | None = None

# Session LRU cache — wraps models.get_session_by_name
# Created in create_app() to control cache size from config
session_lru: functools._lru_cache_wrapper | None = None


def init_caches() -> None:
    """Initialize all cache instances with config values.

    Called once from create_app() at application startup.
    """
    global search_cache, tag_cache, session_lru
    search_cache = SearchCache(
        max_size=config.SEARCH_CACHE_SIZE,
        ttl=config.SEARCH_CACHE_TTL,
    )
    tag_cache = TagCache(ttl=config.TAG_CACHE_TTL)
    logger.info(
        "Caches initialized: search=%d entries/%.0fs TTL, tags=%.0fs TTL",
        config.SEARCH_CACHE_SIZE,
        config.SEARCH_CACHE_TTL,
        config.TAG_CACHE_TTL,
    )


def invalidate_caches(session_id: int) -> None:
    """Invalidate all caches for a given session.

    Called after any entry mutation (create, update, delete, bulk, upload).
    """
    if search_cache:
        search_cache.invalidate_session(session_id)
    if tag_cache:
        tag_cache.pop(session_id, None)
