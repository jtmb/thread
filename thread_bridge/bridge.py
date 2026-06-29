#!/usr/bin/env python3
"""MCP (Model Context Protocol) stdio bridge for Thread.

Implements a minimal JSON-RPC 2.0 server over stdio that exposes Thread
server operations as MCP tools. Compatible with Cline, VSCode, and any
MCP-compliant client.

Usage:
    THREAD_SERVER_URL=http://pi:5000 python -m thread_bridge.bridge

Protocol:
    - Reads JSON-RPC messages from stdin (one per line, newline-delimited)
    - Writes JSON-RPC responses to stdout
    - Logs to stderr
"""

import json
import logging
import sys
from typing import Any

from thread_bridge import config, client as api_client

logger = logging.getLogger(__name__)

# Configure logging to stderr so stdout stays clean for JSON-RPC
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)

SERVER_NAME = "thread-mcp-bridge"
SERVER_VERSION = "0.1.0"

# ── Tool Definitions (MCP spec: tools/list response) ────────────────────────

TOOLS = [
    {
        "name": "thread_create_entry",
        "description": "Create a new context entry in a Thread session. Returns the created entry with its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Session name (e.g., 'vscode-cline'). Defaults to THREAD_DEFAULT_SESSION.",
                },
                "content": {
                    "type": "string",
                    "description": "Text content for the entry (required, max 100KB).",
                },
                "priority": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "description": "Importance score 0-10 (default 5).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for categorization.",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "thread_read_entries",
        "description": "Read entries from a Thread session with cursor-based pagination. Use 'after' to page through results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Session name. Defaults to THREAD_DEFAULT_SESSION.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max entries to return (default 50, max 200).",
                },
                "after": {
                    "type": "integer",
                    "description": "Cursor — return entries with id > this value.",
                },
            },
        },
    },
    {
        "name": "thread_read_entries_batch",
        "description": "Fetch multiple entries by ID in a single round-trip. Efficient batch reads.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Session name. Defaults to THREAD_DEFAULT_SESSION.",
                },
                "ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of entry IDs to fetch (max 100).",
                },
            },
            "required": ["ids"],
        },
    },
    {
        "name": "thread_update_entry",
        "description": "Update an existing entry. Only provided fields are changed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Session name. Defaults to THREAD_DEFAULT_SESSION.",
                },
                "entry_id": {
                    "type": "integer",
                    "description": "ID of the entry to update.",
                },
                "content": {
                    "type": "string",
                    "description": "New content (leave unset to keep existing).",
                },
                "priority": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "description": "New priority (leave unset to keep existing).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New tags (leave unset to keep existing).",
                },
            },
            "required": ["entry_id"],
        },
    },
    {
        "name": "thread_delete_entry",
        "description": "Delete an entry by ID. Returns true if deleted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Session name. Defaults to THREAD_DEFAULT_SESSION.",
                },
                "entry_id": {
                    "type": "integer",
                    "description": "ID of the entry to delete.",
                },
            },
            "required": ["entry_id"],
        },
    },
    {
        "name": "thread_search",
        "description": "Full-text search across entries using FTS5 with BM25 ranking. Supports prefix (pyth*), phrase (\"context server\"), and negation (-java). Returns ranked results with highlighted snippets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Session name. Defaults to THREAD_DEFAULT_SESSION.",
                },
                "query": {
                    "type": "string",
                    "description": "FTS5 search query string.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 100).",
                },
                "use_cache": {
                    "type": "boolean",
                    "description": "Use server-side cache (default true). Set false for fresh results.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "thread_create_session",
        "description": "Create a new Thread session. Sessions are containers for context entries — create one per project, conversation, or topic. Use this before creating entries if the session doesn't already exist.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique session name (e.g., 'my-project', 'q4-planning').",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of what this session tracks.",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "thread_list_sessions",
        "description": "List all sessions on the Thread server.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "thread_get_tags",
        "description": "Get all unique tags used in a session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Session name. Defaults to THREAD_DEFAULT_SESSION.",
                },
            },
        },
    },
    {
        "name": "thread_get_stats",
        "description": "Get server performance metrics: uptime, DB size, pool utilization, cache stats, request latency.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "thread_bulk_create_entries",
        "description": "Create multiple entries at once (up to 100). Returns created/failed counts with per-entry details.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Session name. Defaults to THREAD_DEFAULT_SESSION.",
                },
                "entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "Entry text content."},
                            "priority": {"type": "integer", "minimum": 0, "maximum": 10},
                            "tags": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["content"],
                    },
                    "description": "Array of entry objects (max 100).",
                },
            },
            "required": ["entries"],
        },
    },
    {
        "name": "thread_upload_file",
        "description": "Upload and auto-chunk a local document file (.md, .txt, .json, .jsonl, .messages.json) into entries. Markdown is split by ## headings, plaintext by paragraphs, JSON passthrough, JSONL split one entry per line with role+content extracted, Cline .messages.json split one entry per conversational turn (text + tool_use + tool_result; thinking blocks skipped).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Session name. Defaults to THREAD_DEFAULT_SESSION.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file on the local workstation.",
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags applied to all chunks.",
                },
                "priority": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "description": "Priority for all created entries (default 5).",
                },
            },
            "required": ["file_path"],
        },
    },
]

# ── Session Warmup ────────────────────────────────────────────────────────

_WARMED_UP = False


def _warmup_default_session() -> None:
    """Ensure the default session exists and has a startup marker entry.

    Called once on client initialization so the session appears
    immediately in listings without the user needing to write first.
    Errors are logged but never propagated — warmup is best-effort.
    """
    global _WARMED_UP
    if _WARMED_UP:
        return
    _WARMED_UP = True

    session_name = config.THREAD_DEFAULT_SESSION
    try:
        # Check if session already exists
        existing = api_client.get_session(session_name)
        if existing is not None:
            logger.info("Default session '%s' already exists (id=%d)", session_name, existing["id"])
        else:
            api_client.create_session(
                session_name,
                description=f"Auto-created context session for {session_name}",
            )
            logger.info("Auto-created default session '%s'", session_name)

        # Seed with a startup marker so the session is non-empty
        from datetime import datetime

        marker = (
            f"MCP bridge started — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "This session automatically collects context from your Copilot/Cline conversations.\n"
            "Use 'Search Thread for X' to find relevant entries, or 'Save this to Thread' to persist decisions."
        )
        api_client.create_entry(
            session_name,
            content=marker,
            priority=0,
            tags=["system", "startup"],
        )
        logger.info("Seeded session '%s' with startup marker", session_name)
    except Exception:
        logger.warning("Session warmup failed (server may be unreachable)", exc_info=True)


# ── Tool Dispatch ──────────────────────────────────────────────────────────


def _session(args: dict) -> str:
    """Extract the session name from tool args, falling back to default."""
    return args.get("session", config.THREAD_DEFAULT_SESSION)


def handle_tool_call(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a tool call to the HTTP client and return the result.

    Args:
        name: The tool name (must match a key in TOOLS).
        args: The tool arguments dict.

    Returns:
        The tool result (dict, list, or scalar).

    Raises:
        ValueError: If the tool name is unknown.
    """
    logger.info("Tool call: %s(%s)", name, json.dumps(args, default=str))

    try:
        if name == "thread_create_entry":
            return api_client.create_entry(
                _session(args),
                content=args["content"],
                priority=args.get("priority", 5),
                tags=args.get("tags"),
            )
        elif name == "thread_read_entries":
            return api_client.read_entries(
                _session(args),
                limit=args.get("limit", 50),
                after=args.get("after"),
            )
        elif name == "thread_read_entries_batch":
            return api_client.read_entries_batch(
                _session(args),
                entry_ids=args["ids"],
            )
        elif name == "thread_update_entry":
            return api_client.update_entry(
                _session(args),
                entry_id=args["entry_id"],
                content=args.get("content"),
                priority=args.get("priority"),
                tags=args.get("tags"),
            )
        elif name == "thread_delete_entry":
            return api_client.delete_entry(
                _session(args),
                entry_id=args["entry_id"],
            )
        elif name == "thread_search":
            return api_client.search_entries(
                _session(args),
                query=args["query"],
                limit=args.get("limit", 100),
                use_cache=args.get("use_cache", True),
            )
        elif name == "thread_create_session":
            return api_client.create_session(
                name=args["name"],
                description=args.get("description", ""),
            )
        elif name == "thread_list_sessions":
            return api_client.list_sessions()
        elif name == "thread_get_tags":
            return api_client.get_tags(_session(args))
        elif name == "thread_get_stats":
            return api_client.get_stats()
        elif name == "thread_bulk_create_entries":
            return api_client.bulk_create_entries(
                _session(args),
                entries=args["entries"],
            )
        elif name == "thread_upload_file":
            return api_client.upload_file(
                _session(args),
                file_path=args["file_path"],
                tags=args.get("tags", ""),
                priority=args.get("priority", 5),
            )
        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        logger.error("Tool call failed: %s — %s", name, e)
        return {"error": str(e)}


# ── JSON-RPC Handlers ──────────────────────────────────────────────────────


def handle_message(msg: dict) -> dict | None:
    """Process a single JSON-RPC message and return a response (or None for notifications).

    Args:
        msg: Parsed JSON-RPC request dict.

    Returns:
        JSON-RPC response dict, or None if the message is a notification.
    """
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params", {})

    logger.debug("Received: method=%s id=%s", method, msg_id)

    # ── Lifecycle ──
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
                "capabilities": {
                    "tools": {},  # We support tools
                },
            },
        }

    elif method == "notifications/initialized":
        logger.info("Client initialized — auto-creating default session")
        _warmup_default_session()
        return None  # Notification — no response

    # ── Tools ──
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS},
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        result = handle_tool_call(tool_name, tool_args)

        # Format as text content (MCP requires content array)
        content_text = json.dumps(result, indent=2, default=str) if not isinstance(result, str) else result

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": content_text,
                    }
                ]
            },
        }

    else:
        logger.warning("Unknown method: %s", method)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}",
            },
        }


# ── Main Loop ──────────────────────────────────────────────────────────────


def main() -> None:
    """Run the MCP bridge main loop: read JSON-RPC from stdin, write responses to stdout.

    One JSON-RPC message per line. Fatal errors are logged and the process exits.
    """
    config.validate()
    logger.info("Thread MCP bridge starting (server=%s)", config.THREAD_SERVER_URL)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON on stdin: %s", e)
            continue

        try:
            response = handle_message(msg)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except Exception:
            logger.exception("Unhandled error processing message: %s", line)


if __name__ == "__main__":
    main()
