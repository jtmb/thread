"""In-process metrics collector — lock-free counters for stats endpoint.

Separated from app.py to avoid circular imports: app → routes/stats → app.
All data is approximate (no locks) — precision is secondary to zero overhead.
"""

import time

# Simple in-memory stats ring buffer (shared across threads — approximate)
# Track the last 1000 request durations for p99 calculation
_request_durations: list[float] = []
_MAX_DURATIONS = 1000
_total_requests = 0

# Server start time for uptime calculation
_start_time: float = 0.0


def record_request_start() -> None:
    """Mark the server start time. Called once from app factory."""
    global _start_time
    _start_time = time.monotonic()


def record_request_duration(duration_ms: float) -> None:
    """Record a single request duration in the ring buffer."""
    global _total_requests, _request_durations

    _total_requests += 1
    if len(_request_durations) >= _MAX_DURATIONS:
        _request_durations.pop(0)
    _request_durations.append(duration_ms)


def get_uptime_seconds() -> float:
    """Return seconds since server start. Returns 0 if server hasn't started yet."""
    if _start_time == 0:
        return 0.0
    return time.monotonic() - _start_time


def get_request_stats() -> dict:
    """Return current request statistics: counts, latency percentiles."""
    durations = list(_request_durations)  # Snapshot

    if not durations:
        return {
            "total_requests": _total_requests,
            "average_ms": 0,
            "p50_ms": 0,
            "p95_ms": 0,
            "p99_ms": 0,
        }

    sorted_ms = sorted(durations)
    n = len(sorted_ms)

    return {
        "total_requests": _total_requests,
        "average_ms": round(sum(sorted_ms) / n, 2),
        "p50_ms": sorted_ms[int(n * 0.50)],
        "p95_ms": sorted_ms[int(n * 0.95)],
        "p99_ms": sorted_ms[int(n * 0.99)],
    }
