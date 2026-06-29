"""Tests for the Server-Sent Events endpoint.

Tests the /api/v1/events SSE route: content-type, initial event push,
subscriber management, and auth bypass when auth is disabled.

SSE endpoints yield forever — tests consume just the first few chunks
to verify the initial stats_update event and entry_count fields.
"""

import json
import pytest


class TestSSEEndpoint:
    """Integration tests for the SSE /api/v1/events route."""

    def _read_first_event(self, response):
        """Read only the first SSE event from a streaming response.

        The endpoint sends an immediate stats_update on connect.
        After reading it, we close the generator to avoid blocking
        on subsequent queue.get() calls in the event loop.
        """
        chunks = []
        try:
            for chunk in response.response:
                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8")
                chunks.append(chunk)
                break  # Only one chunk needed — immediate stats_update
        finally:
            # Close generator to avoid blocking on client_queue.get()
            response.response.close()
        return "".join(chunks)

    def test_events_returns_text_event_stream(self, client):
        """GET /api/v1/events returns Content-Type: text/event-stream."""
        res = client.get("/api/v1/events")
        assert res.status_code == 200
        assert res.content_type.startswith("text/event-stream")

    def test_events_pushes_initial_stats(self, client):
        """First event sent is a stats_update with session data."""
        res = client.get("/api/v1/events")
        body = self._read_first_event(res)

        assert "event: stats_update" in body, (
            f"Expected stats_update event, got: {body[:300]}"
        )
        assert "data:" in body

        data_line = next(
            line for line in body.split("\n") if line.startswith("data:")
        )
        raw = data_line[5:].strip()
        assert raw, f"Empty data payload. Full body: {body[:300]}"
        stats = json.loads(raw)

        assert "total_entries" in stats
        assert "total_sessions" in stats
        assert "sessions" in stats
        assert isinstance(stats["sessions"], list)
        assert "db_size_bytes" in stats

    def test_events_includes_entry_count_in_sessions(self, client):
        """Session objects in the stats_update include entry_count field."""
        res = client.get("/api/v1/events")
        body = self._read_first_event(res)

        data_line = next(
            line for line in body.split("\n") if line.startswith("data:")
        )
        stats = json.loads(data_line[5:].strip())

        for session in stats["sessions"]:
            assert "entry_count" in session, (
                f"Session {session.get('name')} missing entry_count"
            )
            assert isinstance(session["entry_count"], int)

    def test_events_auth_bypass_when_disabled(self, client):
        """When AUTH_ENABLED is false, events work without token."""
        res = client.get("/api/v1/events")
        body = self._read_first_event(res)
        assert "event: stats_update" in body

    def test_events_cache_headers_set(self, client):
        """SSE response has no-cache headers for proxy compatibility."""
        res = client.get("/api/v1/events")

        cache_control = res.headers.get("Cache-Control", "")
        assert "no-cache" in cache_control

        assert res.headers.get("X-Accel-Buffering") == "no"


class TestSessionEntryCount:
    """Verify the entry_count subquery in models.list_sessions()."""

    def test_entry_count_zero_for_empty_session(self, client):
        """A session with no entries has entry_count = 0."""
        client.post(
            "/api/v1/sessions",
            json={"name": "empty-test-session"},
        )
        res = client.get("/api/v1/sessions")
        sessions = res.get_json()
        test_session = next(
            s for s in sessions if s["name"] == "empty-test-session"
        )
        assert test_session["entry_count"] == 0

    def test_entry_count_increments_with_entries(self, client):
        """Creating entries increases the session's entry_count."""
        client.post(
            "/api/v1/sessions",
            json={"name": "count-test-session"},
        )

        for i in range(3):
            client.post(
                "/api/v1/sessions/count-test-session/entries",
                json={"content": f"Entry {i + 1}"},
            )

        res = client.get("/api/v1/sessions")
        sessions = res.get_json()
        test_session = next(
            s for s in sessions if s["name"] == "count-test-session"
        )
        assert test_session["entry_count"] == 3
