"""Unit tests for MCP bridge — HTTP client and JSON-RPC handling.

Tests use mock responses to avoid requiring a running server.
"""

import json

import pytest
import requests


# ── Bridge Client ──────────────────────────────────────────────────────────────

def test_client_list_sessions(monkeypatch):
    """list_sessions returns a list of session dicts."""
    import thread_bridge.client as client_mod

    class MockResp:
        status_code = 200
        ok = True
        def json(self): return [{"id": 1, "name": "test"}]
        def raise_for_status(self): pass

    class MockSession:
        def get(self, url, timeout=None):
            return MockResp()

    monkeypatch.setattr(client_mod, "_get_session", lambda: MockSession())
    result = client_mod.list_sessions()
    assert isinstance(result, list)
    assert result[0]["name"] == "test"


def test_client_create_entry(monkeypatch):
    """create_entry returns an entry dict."""
    import thread_bridge.client as client_mod

    class MockResp:
        status_code = 201
        ok = True
        def json(self): return {"id": 42, "content": "Hello"}
        def raise_for_status(self): pass

    class MockSession:
        def post(self, url, json=None, timeout=None):
            return MockResp()

    monkeypatch.setattr(client_mod, "_get_session", lambda: MockSession())
    result = client_mod.create_entry("test", "Hello", priority=5)
    assert result["id"] == 42


def test_client_search_entries(monkeypatch):
    """search_entries returns a list of result dicts."""
    import thread_bridge.client as client_mod

    class MockResp:
        status_code = 200
        ok = True
        def json(self): return {"results": [{"id": 1, "content": "Result"}], "count": 1}
        def raise_for_status(self): pass

    class MockSession:
        def get(self, url, params=None, timeout=None):
            return MockResp()

    monkeypatch.setattr(client_mod, "_get_session", lambda: MockSession())
    result = client_mod.search_entries("test", "query")
    assert isinstance(result, list)
    assert result[0]["content"] == "Result"


def test_client_get_tags(monkeypatch):
    """get_tags returns a list of tags."""
    import thread_bridge.client as client_mod

    class MockResp:
        status_code = 200
        ok = True
        def json(self): return {"tags": ["tag1", "tag2"]}
        def raise_for_status(self): pass

    class MockSession:
        def get(self, url, timeout=None):
            return MockResp()

    monkeypatch.setattr(client_mod, "_get_session", lambda: MockSession())
    result = client_mod.get_tags("test")
    assert "tag1" in result
    assert "tag2" in result


def test_client_handles_404(monkeypatch):
    """Client raises on 404 responses."""
    import thread_bridge.client as client_mod

    class MockResp:
        status_code = 404
        ok = False
        reason = "Not Found"
        def json(self): return {"error": {"code": "NOT_FOUND", "message": "Not found"}}
        def raise_for_status(self):
            raise requests.HTTPError("404 NOT_FOUND: Not found")

    class MockSession:
        def get(self, url, timeout=None):
            return MockResp()

    monkeypatch.setattr(client_mod, "_get_session", lambda: MockSession())
    with pytest.raises(requests.HTTPError):
        client_mod.list_sessions()


# ── Bridge JSON-RPC ────────────────────────────────────────────────────────────

def test_mcp_initialize():
    """The bridge responds to initialize with server capabilities."""
    from thread_bridge.bridge import handle_message

    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }
    result = handle_message(msg)
    assert result is not None
    assert "result" in result
    assert "capabilities" in result["result"]
    assert "serverInfo" in result["result"]


def test_mcp_tools_list():
    """The bridge responds to tools/list with 11 tool definitions."""
    from thread_bridge.bridge import handle_message

    msg = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    result = handle_message(msg)
    assert result is not None
    assert "tools" in result["result"]
    assert len(result["result"]["tools"]) == 12

    tool_names = [t["name"] for t in result["result"]["tools"]]
    assert "thread_create_entry" in tool_names
    assert "thread_create_session" in tool_names
    assert "thread_search" in tool_names
    assert "thread_list_sessions" in tool_names
    assert "thread_bulk_create_entries" in tool_names
    assert "thread_upload_file" in tool_names


def test_mcp_tools_have_input_schema():
    """Every tool has a valid inputSchema."""
    from thread_bridge.bridge import handle_message

    msg = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/list",
        "params": {},
    }
    result = handle_message(msg)
    for tool in result["result"]["tools"]:
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"
        assert "properties" in tool["inputSchema"]
