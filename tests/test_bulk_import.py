"""Integration tests for document ingestion — upload endpoint and CLI import."""

import io
import json
import os
import tempfile

import pytest


def _setup_session(client, name="import-test"):
    """Helper: create a session and return its name."""
    client.post("/api/v1/sessions", json={"name": name, "description": ""})
    return name


# ── File Upload Endpoint ──────────────────────────────────────────────────────


def test_upload_markdown_file(client):
    """Uploading a .md file chunks by headings and creates entries."""
    name = _setup_session(client)
    data = {
        "file": (io.BytesIO(b"# Title\n\n## Section 1\nContent one.\n\n## Section 2\nContent two.\n"), "test.md"),
        "tags": "docs,reference",
        "priority": "7",
    }
    resp = client.post(
        f"/api/v1/sessions/{name}/entries/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    result = resp.get_json()
    assert result["filename"] == "test.md"
    assert result["format"] == "markdown"
    assert result["chunks"] >= 2
    assert result["entries_created"] == result["chunks"]

    # Verify filename is auto-tagged
    for entry in result["entries"]:
        assert "test.md" in entry["tags"]


def test_upload_plaintext_file(client):
    """Uploading a .txt file chunks by paragraphs."""
    name = _setup_session(client)
    data = {
        "file": (io.BytesIO(b"Paragraph one.\n\nParagraph two.\n\nParagraph three.\n"), "notes.txt"),
    }
    resp = client.post(
        f"/api/v1/sessions/{name}/entries/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    result = resp.get_json()
    assert result["format"] == "text"
    assert result["entries_created"] >= 1


def test_upload_json_file(client):
    """Uploading a .json file with entries imports them."""
    name = _setup_session(client)
    json_data = json.dumps({
        "entries": [
            {"content": "JSON entry 1", "priority": 8, "tags": ["json"]},
            {"content": "JSON entry 2", "priority": 6},
        ]
    })
    data = {
        "file": (io.BytesIO(json_data.encode()), "data.json"),
    }
    resp = client.post(
        f"/api/v1/sessions/{name}/entries/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    result = resp.get_json()
    assert result["format"] == "json"
    assert result["entries_created"] == 2


def test_upload_binary_file_returns_415(client):
    """Uploading binary content returns 415 Unsupported Media Type."""
    name = _setup_session(client)
    data = {
        "file": (io.BytesIO(b"\x00\x01\x02\x03"), "binary.bin"),
    }
    resp = client.post(
        f"/api/v1/sessions/{name}/entries/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 415


def test_upload_no_file_returns_400(client):
    """Missing file field returns 400."""
    name = _setup_session(client)
    resp = client.post(
        f"/api/v1/sessions/{name}/entries/upload",
        data={"tags": "test"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_upload_auto_creates_session(client):
    """Upload to nonexistent session auto-creates it and returns 201."""
    data = {
        "file": (io.BytesIO(b"Test content"), "test.txt"),
    }
    resp = client.post(
        "/api/v1/sessions/nonexistent/entries/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["entries_created"] == 1
    assert data["entries"][0]["content"] == "Test content"


# ── Bulk Create Endpoint ──────────────────────────────────────────────────────


def test_bulk_create_all_valid(client):
    """Bulk create with all valid entries succeeds."""
    name = _setup_session(client, "bulk-ok")
    resp = client.post(
        f"/api/v1/sessions/{name}/entries/bulk",
        json={
            "entries": [
                {"content": f"Bulk entry {i}", "priority": min(i + 5, 10)}
                for i in range(5)
            ]
        },
    )
    assert resp.status_code == 201
    result = resp.get_json()
    assert result["created"] == 5
    assert result["failed"] == 0


def test_bulk_create_exceeds_limit_returns_400(client):
    """Bulk create with more than 100 entries returns 400."""
    name = _setup_session(client, "bulk-limit")
    resp = client.post(
        f"/api/v1/sessions/{name}/entries/bulk",
        json={"entries": [{"content": "x"}] * 101},
    )
    assert resp.status_code == 400


def test_bulk_create_partial_invalid(client):
    """Bulk create with some invalid entries reports errors."""
    name = _setup_session(client, "bulk-partial")
    resp = client.post(
        f"/api/v1/sessions/{name}/entries/bulk",
        json={
            "entries": [
                {"content": "Valid 1"},
                {},  # No content
                {"content": "Valid 2", "priority": 9},
            ]
        },
    )
    assert resp.status_code == 207
    result = resp.get_json()
    assert result["created"] == 2
    assert result["failed"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["index"] == 1


# ── CLI Import Tool ────────────────────────────────────────────────────────────


def test_cli_collect_files_finds_markdown():
    """The CLI file collector finds .md, .txt, and .json files."""
    import importlib
    import sys
    import os as _os

    # We need to add the thread_server parent to path
    sys.path.insert(0, _os.path.dirname(_os.path.dirname(__file__)))

    # 'import' is a keyword — use importlib for thread_server.cli.import
    cli_import = importlib.import_module("thread_server.cli.import")
    _collect_files = cli_import._collect_files

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test files
        with open(_os.path.join(tmpdir, "readme.md"), "w") as f:
            f.write("# Test")
        with open(_os.path.join(tmpdir, "notes.txt"), "w") as f:
            f.write("Notes")
        with open(_os.path.join(tmpdir, "data.json"), "w") as f:
            f.write('{"entries":[]}')
        with open(_os.path.join(tmpdir, "image.png"), "w") as f:
            f.write("PNG")

        files = _collect_files(tmpdir)
        paths = [str(f) for f in files]
        assert any("readme.md" in p for p in paths)
        assert any("notes.txt" in p for p in paths)
        assert any("data.json" in p for p in paths)
        assert not any("image.png" in p for p in paths)
