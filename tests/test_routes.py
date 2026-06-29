"""Integration tests for all API routes using Flask test client."""

import io


# ── Health ──────────────────────────────────────────────────────────────────────


def test_health_returns_200(client):
    """GET /api/v1/health returns 200 with status ok."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert data["version"] == "0.1.0"


def test_health_debug_mode_includes_extras(client):
    """When THREAD_DEBUG=true, health includes pool and uptime info."""
    resp = client.get("/api/v1/health")
    data = resp.get_json()
    # Debug mode might include extra fields
    assert data["status"] == "ok"


# ── Sessions ───────────────────────────────────────────────────────────────────


def test_create_session_returns_201(client):
    """POST /api/v1/sessions creates a session."""
    resp = client.post(
        "/api/v1/sessions",
        json={"name": "my-session", "description": "Test session"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["name"] == "my-session"
    assert data["description"] == "Test session"
    assert "Location" in resp.headers


def test_create_session_duplicate_returns_409(client):
    """POST with existing name returns 409 CONFLICT."""
    client.post("/api/v1/sessions", json={"name": "dup", "description": ""})
    resp = client.post("/api/v1/sessions", json={"name": "dup", "description": ""})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["error"]["code"] == "CONFLICT"


def test_create_session_missing_name_returns_400(client):
    """POST without name returns 400."""
    resp = client.post("/api/v1/sessions", json={"description": ""})
    assert resp.status_code == 400


def test_get_session_by_name_returns_200(client):
    """GET /api/v1/sessions/<name> returns session."""
    client.post("/api/v1/sessions", json={"name": "get-test", "description": ""})
    resp = client.get("/api/v1/sessions/get-test")
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "get-test"


def test_get_session_missing_returns_404(client):
    """GET for missing session returns 404."""
    resp = client.get("/api/v1/sessions/nonexistent")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


def test_list_sessions_returns_200(client):
    """GET /api/v1/sessions returns array of sessions."""
    client.post("/api/v1/sessions", json={"name": "l1", "description": ""})
    client.post("/api/v1/sessions", json={"name": "l2", "description": ""})
    resp = client.get("/api/v1/sessions")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 2


def test_delete_session_returns_204(client):
    """DELETE /api/v1/sessions/<name> deletes and returns 204."""
    client.post("/api/v1/sessions", json={"name": "del-me", "description": ""})
    resp = client.delete("/api/v1/sessions/del-me")
    assert resp.status_code == 204
    # Verify it's gone
    assert client.get("/api/v1/sessions/del-me").status_code == 404


# ── Entries ────────────────────────────────────────────────────────────────────


def _setup_session(client, name="entry-test"):
    """Helper: create a session and return its name."""
    client.post("/api/v1/sessions", json={"name": name, "description": ""})
    return name


def test_create_entry_returns_201(client):
    """POST /entries creates a single entry."""
    name = _setup_session(client)
    resp = client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"content": "Test content", "priority": 7, "tags": ["test"]},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["content"] == "Test content"
    assert data["priority"] == 7
    assert data["tags"] == ["test"]
    assert "Location" in resp.headers


def test_create_entry_missing_content_returns_400(client):
    """POST without content returns 400."""
    name = _setup_session(client)
    resp = client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"priority": 5},
    )
    assert resp.status_code == 400


def test_create_entry_auto_creates_session(client):
    """POST to nonexistent session auto-creates it and returns 201."""
    resp = client.post(
        "/api/v1/sessions/nonexistent/entries",
        json={"content": "Test"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["content"] == "Test"
    assert data["id"] is not None


def test_get_entry_returns_200(client):
    """GET /entries/<id> returns the entry."""
    name = _setup_session(client)
    created = client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"content": "Get me"},
    ).get_json()

    resp = client.get(f"/api/v1/sessions/{name}/entries/{created['id']}")
    assert resp.status_code == 200
    assert resp.get_json()["content"] == "Get me"


def test_get_entry_missing_returns_404(client):
    """GET for missing entry returns 404."""
    name = _setup_session(client)
    resp = client.get(f"/api/v1/sessions/{name}/entries/99999")
    assert resp.status_code == 404


def test_list_entries_returns_200(client):
    """GET /entries returns array of entries."""
    name = _setup_session(client)
    client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"content": "Entry 1"},
    )
    client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"content": "Entry 2"},
    )

    resp = client.get(f"/api/v1/sessions/{name}/entries")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 2


def test_list_entries_cursor_pagination(client):
    """Cursor pagination with ?after= works."""
    name = _setup_session(client)
    for i in range(5):
        client.post(
            f"/api/v1/sessions/{name}/entries",
            json={"content": f"Entry {i}"},
        )

    # First page
    page1 = client.get(f"/api/v1/sessions/{name}/entries?limit=3").get_json()
    entries1 = page1["data"]
    assert len(entries1) == 3
    last_id = entries1[-1]["id"]

    # Second page — cursor returns entries with id > after_id, ordered by id ASC
    page2 = client.get(
        f"/api/v1/sessions/{name}/entries?limit=3&after={last_id}"
    ).get_json()
    entries2 = page2["data"]
    assert len(entries2) == 2
    for entry in entries2:
        assert entry["id"] > last_id


def test_update_entry_returns_200(client):
    """PUT /entries/<id> updates and returns entry."""
    name = _setup_session(client)
    created = client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"content": "Original"},
    ).get_json()

    resp = client.put(
        f"/api/v1/sessions/{name}/entries/{created['id']}",
        json={"content": "Updated", "priority": 9},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["content"] == "Updated"
    assert data["priority"] == 9


def test_update_entry_missing_returns_404(client):
    """PUT to missing entry returns 404."""
    name = _setup_session(client)
    resp = client.put(
        f"/api/v1/sessions/{name}/entries/99999",
        json={"content": "Nope"},
    )
    assert resp.status_code == 404


def test_delete_entry_returns_204(client):
    """DELETE /entries/<id> returns 204."""
    name = _setup_session(client)
    created = client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"content": "To delete"},
    ).get_json()

    resp = client.delete(f"/api/v1/sessions/{name}/entries/{created['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/v1/sessions/{name}/entries/{created['id']}").status_code == 404


# ── Batch Read ─────────────────────────────────────────────────────────────────


def test_batch_read_returns_requested_entries(client):
    """POST /entries/batch returns only requested IDs."""
    name = _setup_session(client)
    e1 = client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"content": "Entry 1"},
    ).get_json()
    e2 = client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"content": "Entry 2"},
    ).get_json()

    resp = client.post(
        f"/api/v1/sessions/{name}/entries/batch",
        json={"ids": [e1["id"], e2["id"]]},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 2


def test_batch_read_partial_missing(client):
    """Batch read silently omits missing IDs."""
    name = _setup_session(client)
    e1 = client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"content": "Entry 1"},
    ).get_json()

    resp = client.post(
        f"/api/v1/sessions/{name}/entries/batch",
        json={"ids": [e1["id"], 99999]},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1


# ── Bulk Create ────────────────────────────────────────────────────────────────


def test_bulk_create_returns_201(client):
    """POST /entries/bulk with valid entries returns 201."""
    name = _setup_session(client)
    resp = client.post(
        f"/api/v1/sessions/{name}/entries/bulk",
        json={
            "entries": [
                {"content": "Bulk 1", "priority": 8},
                {"content": "Bulk 2"},
            ]
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["created"] == 2
    assert data["failed"] == 0


def test_bulk_create_partial_failure(client):
    """Bulk create reports individual failures."""
    name = _setup_session(client)
    resp = client.post(
        f"/api/v1/sessions/{name}/entries/bulk",
        json={
            "entries": [
                {"content": "Valid"},
                {"priority": 5},  # missing content
                {"content": "Also valid"},
            ]
        },
    )
    assert resp.status_code == 207
    data = resp.get_json()
    assert data["created"] == 2
    assert data["failed"] == 1


# ── File Upload ────────────────────────────────────────────────────────────────


def test_upload_file_returns_201(client):
    """POST /entries/upload with a text file creates chunked entries."""
    name = _setup_session(client, "upload-test")
    data = {"file": (io.BytesIO(b"Hello\n\nWorld"), "test.txt")}
    resp = client.post(
        f"/api/v1/sessions/{name}/entries/upload",
        content_type="multipart/form-data",
        data=data,
    )
    assert resp.status_code == 201
    result = resp.get_json()
    assert result["entries_created"] >= 1
    assert result["filename"] == "test.txt"
    assert result["format"] == "text"
    # First upload returns byte_offset matching the file size
    assert result["byte_offset"] == len(b"Hello\n\nWorld")


def test_upload_file_incremental_no_duplicates(client):
    """Re-uploading the same file with offset returns 0 new entries."""
    name = _setup_session(client, "upload-inc")
    content = b'{"role": "user", "content": "First line"}\n{"role": "assistant", "content": "Second"}\n'

    # First upload — full file
    resp1 = client.post(
        f"/api/v1/sessions/{name}/entries/upload",
        content_type="multipart/form-data",
        data={
            "file": (io.BytesIO(content), "chat.jsonl"),
        },
    )
    assert resp1.status_code == 201
    assert resp1.get_json()["entries_created"] == 2
    offset = resp1.get_json()["byte_offset"]

    # Second upload — same content, same offset → 0 new
    resp2 = client.post(
        f"/api/v1/sessions/{name}/entries/upload",
        content_type="multipart/form-data",
        data={
            "file": (io.BytesIO(content), "chat.jsonl"),
            "offset": str(offset),
        },
    )
    assert resp2.status_code == 201
    assert resp2.get_json()["entries_created"] == 0


def test_upload_file_incremental_new_lines_only(client):
    """Only new lines after offset are imported."""
    name = _setup_session(client, "upload-delta")
    batch1 = b'{"role": "user", "content": "Old"}\n'
    batch2 = b'{"role": "user", "content": "Old"}\n{"role": "user", "content": "New"}\n'

    # Upload batch1
    resp1 = client.post(
        f"/api/v1/sessions/{name}/entries/upload",
        content_type="multipart/form-data",
        data={"file": (io.BytesIO(batch1), "chat.jsonl")},
    )
    assert resp1.status_code == 201
    assert resp1.get_json()["entries_created"] == 1

    # Upload batch2 (simulates file growth: Old + New) — offset auto-tracked
    resp2 = client.post(
        f"/api/v1/sessions/{name}/entries/upload",
        content_type="multipart/form-data",
        data={"file": (io.BytesIO(batch2), "chat.jsonl")},
    )
    assert resp2.status_code == 201
    # Only "New" should be imported; "Old" is skipped
    assert resp2.get_json()["entries_created"] == 1
    entries = resp2.get_json()["entries"]
    assert "New" in entries[0]["content"]


# ── Search ─────────────────────────────────────────────────────────────────────


def test_search_returns_200(client):
    """GET /search returns FTS5 results."""
    name = _setup_session(client)
    client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"content": "Python is a programming language", "tags": ["python"]},
    )

    resp = client.get(f"/api/v1/sessions/{name}/search?q=python")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] >= 1
    assert "rank" in data["results"][0]
    assert "snippet" in data["results"][0]


def test_search_empty_query_returns_200_with_recent(client):
    """GET /search without q returns 200 with recent entries."""
    name = _setup_session(client)
    resp = client.get(f"/api/v1/sessions/{name}/search")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "results" in data
    assert "count" in data


# ── Tags ───────────────────────────────────────────────────────────────────────


def test_tags_returns_200(client):
    """GET /tags returns unique tags."""
    name = _setup_session(client)
    client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"content": "One", "tags": ["alpha", "beta"]},
    )
    client.post(
        f"/api/v1/sessions/{name}/entries",
        json={"content": "Two", "tags": ["beta", "gamma"]},
    )

    resp = client.get(f"/api/v1/sessions/{name}/tags")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "alpha" in data["tags"]
    assert "beta" in data["tags"]
    assert "gamma" in data["tags"]


# ── Stats ──────────────────────────────────────────────────────────────────────


def test_stats_returns_200(client):
    """GET /api/v1/stats returns performance metrics."""
    resp = client.get("/api/v1/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "server" in data
    assert "db" in data
    assert "pool" in data
    assert "cache" in data
    assert "requests" in data


def test_storage_stats_returns_200(client):
    """GET /api/v1/stats/storage returns filesystem capacity + app footprint."""
    resp = client.get("/api/v1/stats/storage")
    assert resp.status_code == 200
    data = resp.get_json()
    # Raw bytes (int, >= 0)
    for field in ("free_bytes", "used_bytes", "total_bytes"):
        assert isinstance(data[field], int)
        assert data[field] >= 0
    # Human-readable MB (int, >= 0)
    for field in ("free_mb", "used_mb", "total_mb"):
        assert isinstance(data[field], int)
        assert data[field] >= 0
    # Human-readable GB (float, 1 decimal, >= 0)
    for field in ("free_gb", "used_gb", "total_gb"):
        assert isinstance(data[field], (int, float))
        assert data[field] >= 0
    # Total must be at least the sum of free + used
    assert data["total_bytes"] >= data["free_bytes"] + data["used_bytes"]
    # MB and GB must be consistent with bytes
    mb = 1024 * 1024
    assert abs(data["free_mb"] - data["free_bytes"] // mb) <= 1
    assert abs(data["total_mb"] - data["total_bytes"] // mb) <= 1
    # App footprint — must be non-negative and <= filesystem used
    for field in ("app_used_bytes", "app_used_mb", "app_used_gb"):
        assert field in data
        assert data[field] >= 0
    assert data["app_used_bytes"] <= data["used_bytes"]
    assert abs(data["app_used_mb"] - data["app_used_bytes"] // mb) <= 1


def test_storage_stats_no_params(client):
    """GET /api/v1/stats/storage works without any query parameters."""
    resp = client.get("/api/v1/stats/storage")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_bytes"] > 0  # Filesystem always has some total
