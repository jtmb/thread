"""Tests for structured JSON logging."""

import json
import logging
import re

from flask import Flask, g

from thread_server.logging_config import JsonFormatter


def test_json_formatter_outputs_valid_json():
    """JsonFormatter produces valid JSON with required keys."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    app = Flask(__name__)
    with app.app_context():
        g.request_id = "req_test123"
        output = formatter.format(record)

    data = json.loads(output)

    assert "timestamp" in data
    assert data["level"] == "INFO"
    assert data["message"] == "Test message"
    assert data["requestId"] == "req_test123"


def test_json_formatter_includes_trace_id_when_present():
    """JsonFormatter includes traceId when set on the record."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname="test.py",
        lineno=1,
        msg="Warning message",
        args=(),
        exc_info=None,
    )
    record.trace_id = "trace_abc"

    app = Flask(__name__)
    with app.app_context():
        g.request_id = "req_test456"
        output = formatter.format(record)

    data = json.loads(output)

    assert data["requestId"] == "req_test456"
    assert data["traceId"] == "trace_abc"


def test_json_formatter_handles_missing_request_id():
    """JsonFormatter works when request_id is not set on the record."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.DEBUG,
        pathname="test.py",
        lineno=1,
        msg="No request",
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert "timestamp" in data
    assert data["level"] == "DEBUG"
    assert data["message"] == "No request"


def test_json_formatter_format_types():
    """JsonFormatter correctly formats messages of different types."""
    formatter = JsonFormatter()

    # String message
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="t.py",
        lineno=1, msg="String %s", args=("interpolated",), exc_info=None,
    )

    app = Flask(__name__)
    with app.app_context():
        g.request_id = "req"
        output = formatter.format(record)

    data = json.loads(output)
    assert data["message"] == "String interpolated"


def test_request_id_header_set_on_response(client):
    """Every response includes X-Request-Id header."""
    resp = client.get("/api/v1/health")
    assert "X-Request-Id" in resp.headers
    assert resp.headers["X-Request-Id"].startswith("req_")


def test_response_includes_duration_header(client):
    """Every response includes X-Duration-Ms header."""
    resp = client.get("/api/v1/health")
    assert "X-Duration-Ms" in resp.headers
    duration = float(resp.headers["X-Duration-Ms"])
    assert duration > 0


def test_no_print_statements_in_production_code():
    """Verify that print() is absent from production source files.

    This test reads the source files and asserts there are no bare print()
    calls outside of comments/docstrings.
    """
    import os as _os

    source_dir = _os.path.join(
        _os.path.dirname(_os.path.dirname(__file__)),
        "thread_server",
    )

    violations = []
    for root, _dirs, files in _os.walk(source_dir):
        # Skip CLI tools — they legitimately use print() for user output
        _dirs[:] = [d for d in _dirs if d not in ("cli", "__pycache__")]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = _os.path.join(root, fname)
            with open(fpath) as f:
                for lineno, line in enumerate(f, 1):
                    stripped = line.strip()
                    # Skip comments and docstrings
                    if stripped.startswith("#") or stripped.startswith('"""'):
                        continue
                    if stripped.startswith("'''"):
                        continue
                    # Detect bare print() calls
                    if re.match(r"^print\s*\(", stripped):
                        violations.append(f"{fpath}:{lineno}: {stripped[:60]}")

    assert not violations, (
        f"Found {len(violations)} print() call(s) in production code:\n"
        + "\n".join(violations)
    )
