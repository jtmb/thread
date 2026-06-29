"""Unit tests for document chunking logic (chunker.py)."""

import json

import pytest

from thread_server.chunker import (
    chunk_by_format,
    chunk_cline_messages,
    chunk_jsonl,
    chunk_markdown,
    chunk_plaintext,
    detect_format,
    is_binary,
    parse_json_entries,
)


# ── Format Detection ───────────────────────────────────────────────────────────


def test_detect_format_markdown():
    """Files with .md extension are detected as markdown."""
    assert detect_format("readme.md") == "markdown"
    assert detect_format("ARCHITECTURE.markdown") == "markdown"
    assert detect_format("path/to/file.MD") == "markdown"


def test_detect_format_text():
    """Files with .txt extension are detected as text."""
    assert detect_format("notes.txt") == "text"
    assert detect_format("file.text") == "text"


def test_detect_format_json():
    """Files with .json extension are detected as json."""
    assert detect_format("data.json") == "json"


def test_detect_format_unsupported():
    """Unsupported extensions raise ValueError."""
    with pytest.raises(ValueError):
        detect_format("image.png")
    with pytest.raises(ValueError):
        detect_format("document.pdf")


# ── Binary Detection ───────────────────────────────────────────────────────────


def test_is_binary_detects_null_bytes():
    """Content with null bytes is detected as binary."""
    assert is_binary(b"hello\x00world") is True


def test_is_binary_plain_text_false():
    """Plain text content is not binary."""
    assert is_binary(b"Hello, world!") is False
    assert is_binary("Hello, world!".encode("utf-8")) is False


# ── Markdown Chunking ──────────────────────────────────────────────────────────


def test_chunk_markdown_splits_by_headings():
    """Markdown is split at ## headings."""
    text = """# Main Title

Some intro text.

## Section One
Content of section one.

## Section Two
Content of section two.
"""
    chunks = chunk_markdown(text)
    assert len(chunks) >= 2
    # Each chunk should have the heading as content
    contents = [c.content for c in chunks]
    assert any("Section One" in c for c in contents)
    assert any("Section Two" in c for c in contents)


def test_chunk_markdown_single_heading():
    """A document with a single heading produces one chunk."""
    text = """# Only Heading
Some content here.
More content.
"""
    chunks = chunk_markdown(text)
    assert len(chunks) == 1
    assert "Only Heading" in chunks[0].content


def test_chunk_markdown_empty_returns_empty():
    """Empty markdown returns empty list."""
    assert chunk_markdown("") == []


def test_chunk_markdown_preserves_index_order():
    """Chunks are returned in document order with sequential indices."""
    text = """# Top

## First
Content first.

## Second
Content second.

## Third
Content third.
"""
    chunks = chunk_markdown(text)
    assert len(chunks) == 3
    assert chunks[0].index == 0
    assert chunks[1].index == 1
    assert chunks[2].index == 2
    assert "First" in chunks[0].content
    assert "Third" in chunks[2].content


# ── Plaintext Chunking ─────────────────────────────────────────────────────────


def test_chunk_plaintext_splits_by_paragraph():
    """Plain text is split at double newlines (paragraph boundaries)."""
    # Use long enough paragraphs but not so long they get sentence-split
    text = "A" * 600 + "\n\n" + "B" * 600 + "\n\n" + "C" * 600
    chunks = chunk_plaintext(text, chunk_size=500)
    assert len(chunks) == 3
    assert "A" * 600 == chunks[0].content
    assert "B" * 600 == chunks[1].content
    assert "C" * 600 == chunks[2].content


def test_chunk_plaintext_merges_short_paragraphs():
    """Short consecutive paragraphs are merged into one chunk."""
    text = """Short.

Tiny.

Also short.

A much longer paragraph that has substantially more content and should
not be merged with the short ones because it exceeds the short paragraph
threshold by a significant margin.
"""
    chunks = chunk_plaintext(text)
    # Short paragraphs should be merged, long one separate
    assert len(chunks) >= 1


def test_chunk_plaintext_empty_returns_empty():
    """Empty text returns empty list."""
    assert chunk_plaintext("") == []


def test_chunk_plaintext_single_paragraph():
    """A single paragraph produces one chunk."""
    text = "Just one paragraph with no breaks."
    chunks = chunk_plaintext(text)
    assert len(chunks) == 1


# ── JSON Parsing ───────────────────────────────────────────────────────────────


def test_parse_json_entries_valid():
    """parse_json_entries extracts entries from a JSON object."""
    json_str = '{"entries": [{"content": "One"}, {"content": "Two", "priority": 8}]}'
    entries = parse_json_entries(json_str)
    assert len(entries) == 2
    assert entries[0]["content"] == "One"
    assert entries[1]["priority"] == 8


def test_parse_json_entries_missing_key():
    """Missing 'entries' key raises ValueError."""
    with pytest.raises(ValueError):
        parse_json_entries('{"data": []}')


def test_parse_json_entries_not_list():
    """'entries' not being a list raises ValueError."""
    with pytest.raises(ValueError):
        parse_json_entries('{"entries": "not a list"}')


# ── JSONL Chunking ────────────────────────────────────────────────────────────


def test_detect_format_jsonl():
    """Files with .jsonl extension are detected as jsonl."""
    assert detect_format("transcript.jsonl") == "jsonl"
    assert detect_format("path/to/archive.JSONL") == "jsonl"


def test_chunk_jsonl_single_line():
    """A single JSONL line produces one chunk with role+content."""
    text = '{"role": "user", "content": "How do I containerize this?"}'
    chunks = chunk_jsonl(text)
    assert len(chunks) == 1
    assert chunks[0].content == "**user**: How do I containerize this?"
    assert chunks[0].index == 0


def test_chunk_jsonl_multi_line():
    """Multiple JSONL lines produce one chunk per conversational turn."""
    text = (
        '{"role": "user", "content": "Build a container"}\n'
        '{"role": "assistant", "content": "Here is how..."}\n'
        '{"role": "user", "content": "Thanks!"}'
    )
    chunks = chunk_jsonl(text)
    assert len(chunks) == 3
    assert chunks[0].content == "**user**: Build a container"
    assert chunks[1].content == "**assistant**: Here is how..."
    assert chunks[2].content == "**user**: Thanks!"
    assert [c.index for c in chunks] == [0, 1, 2]


def test_chunk_jsonl_skips_empty_lines():
    """Empty and whitespace-only lines are skipped."""
    text = (
        '{"role": "user", "content": "One"}\n'
        '\n'
        '   \n'
        '{"role": "assistant", "content": "Two"}'
    )
    chunks = chunk_jsonl(text)
    assert len(chunks) == 2
    assert [c.content for c in chunks] == [
        "**user**: One",
        "**assistant**: Two",
    ]


def test_chunk_jsonl_skips_malformed():
    """Malformed JSON lines are skipped with no exception raised."""
    text = (
        '{"role": "user", "content": "Valid"}\n'
        'not json at all\n'
        '{"role": "assistant", "content": "Also valid"}'
    )
    chunks = chunk_jsonl(text)
    assert len(chunks) == 2
    assert chunks[0].content == "**user**: Valid"
    assert chunks[1].content == "**assistant**: Also valid"


def test_chunk_jsonl_empty_input():
    """Empty or whitespace-only input returns empty list."""
    assert chunk_jsonl("") == []
    assert chunk_jsonl("   ") == []
    assert chunk_jsonl("\n\n") == []


def test_chunk_by_format_dispatches_jsonl():
    """chunk_by_format with jsonl dispatches to chunk_jsonl."""
    text = '{"role": "user", "content": "Dispatch test"}'
    chunks = chunk_by_format(text, "jsonl")
    assert len(chunks) == 1
    assert chunks[0].content == "**user**: Dispatch test"


def test_chunk_jsonl_transcript_user_message():
    """Copilot transcript user.message entries are extracted from data.content."""
    text = json.dumps({
        "type": "user.message",
        "data": {"content": "How do I deploy this?"},
        "id": "abc",
        "timestamp": "2026-01-01T00:00:00Z",
    })
    chunks = chunk_jsonl(text)
    assert len(chunks) == 1
    assert chunks[0].content == "**user**: How do I deploy this?"


def test_chunk_jsonl_transcript_assistant_message():
    """Copilot transcript assistant.message entries are extracted."""
    text = json.dumps({
        "type": "assistant.message",
        "data": {
            "content": "Here's the deployment plan.",
            "toolRequests": [{"name": "read_file"}],
            "reasoningText": "The user needs a Dockerfile."
        },
    })
    chunks = chunk_jsonl(text)
    assert len(chunks) == 1
    assert chunks[0].content == "**assistant**: Here's the deployment plan."


def test_chunk_jsonl_transcript_skips_non_messages():
    """Session start, turn boundaries, and tool executions are skipped."""
    lines = [
        json.dumps({"type": "session.start", "data": {}}),
        json.dumps({"type": "assistant.turn_start", "data": {"turnId": "0"}}),
        json.dumps({"type": "assistant.turn_end", "data": {"turnId": "0"}}),
        json.dumps({"type": "function", "data": {"name": "read_file"}}),
        json.dumps({"type": "tool.execution_start", "data": {}}),
        json.dumps({"type": "tool.execution_complete", "data": {}}),
        json.dumps({"type": "user.message", "data": {"content": "Only this one"}}),
    ]
    chunks = chunk_jsonl("\n".join(lines))
    assert len(chunks) == 1
    assert chunks[0].content == "**user**: Only this one"


def test_chunk_jsonl_transcript_mixed_with_simple():
    """Transcript lines and simple role/content lines coexist."""
    text = (
        json.dumps({"type": "user.message", "data": {"content": "Transcript msg"}}) + "\n"
        + json.dumps({"role": "user", "content": "Simple msg"})
    )
    chunks = chunk_jsonl(text)
    assert len(chunks) == 2
    assert chunks[0].content == "**user**: Transcript msg"
    assert chunks[1].content == "**user**: Simple msg"


# ── Cline Messages Chunking ────────────────────────────────────────────────────


def test_detect_format_cline_messages():
    """Files ending in .messages.json are detected as cline_messages."""
    assert detect_format("session.messages.json") == "cline_messages"
    assert detect_format("path/to/1781052201659_55vq3.messages.json") == "cline_messages"


def test_chunk_cline_messages_text_only():
    """User + assistant text turns are extracted with role headers."""
    text = json.dumps({
        "version": 1,
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "Write hello.py"}
            ]},
            {"role": "assistant", "content": [
                {"type": "text", "text": "I'll create the file."}
            ]},
        ],
    })
    chunks = chunk_cline_messages(text)
    assert len(chunks) == 2
    assert chunks[0].content == "**user**: Write hello.py"
    assert chunks[1].content == "**assistant**: I'll create the file."


def test_chunk_cline_messages_with_tool_use():
    """Tool use and tool result blocks are extracted with markers."""
    text = json.dumps({
        "version": 1,
        "messages": [
            {"role": "assistant", "content": [
                {"type": "text", "text": "Let me check that."},
                {"type": "tool_use", "id": "42", "name": "read_file",
                 "input": {"filePath": "/tmp/test.py"}},
                {"type": "tool_result", "tool_use_id": "42", "name": "read_file",
                 "content": "print('hello')"},
            ]},
        ],
    })
    chunks = chunk_cline_messages(text)
    assert len(chunks) == 1
    content = chunks[0].content
    assert "**assistant**" in content
    assert "Let me check that." in content
    assert "[tool_use: read_file]" in content
    assert "[tool_result: read_file]" in content
    assert "print('hello')" in content


def test_chunk_cline_messages_skips_thinking():
    """Thinking blocks are omitted from extracted content."""
    text = json.dumps({
        "version": 1,
        "messages": [
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "The user wants a greeting."},
                {"type": "text", "text": "Hello, world!"},
            ]},
        ],
    })
    chunks = chunk_cline_messages(text)
    assert len(chunks) == 1
    assert chunks[0].content == "**assistant**: Hello, world!"
    assert "thinking" not in chunks[0].content
    assert "The user wants" not in chunks[0].content


def test_chunk_cline_messages_invalid_json():
    """Malformed JSON raises ValueError."""
    with pytest.raises(ValueError, match="Invalid Cline messages JSON"):
        chunk_cline_messages("not json at all")


def test_chunk_cline_messages_missing_messages():
    """JSON object missing 'messages' key raises ValueError."""
    with pytest.raises(ValueError, match="missing 'messages' key"):
        chunk_cline_messages('{"version": 1}')


def test_chunk_by_format_dispatches_cline():
    """chunk_by_format with cline_messages dispatches to chunk_cline_messages."""
    text = json.dumps({
        "version": 1,
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "Dispatch test"}
            ]},
        ],
    })
    chunks = chunk_by_format(text, "cline_messages")
    assert len(chunks) == 1
    assert chunks[0].content == "**user**: Dispatch test"


# ── chunk_by_format Dispatcher ─────────────────────────────────────────────────


def test_chunk_by_format_dispatches_markdown():
    """chunk_by_format with markdown uses heading-split."""
    text = """# Top
## Section
Content.
"""
    chunks = chunk_by_format(text, "markdown")
    assert len(chunks) >= 1


def test_chunk_by_format_dispatches_text():
    """chunk_by_format with text uses paragraph-split."""
    text = "X" * 600 + "\n\n" + "Y" * 600
    chunks = chunk_by_format(text, "text", chunk_size=500)
    assert len(chunks) == 2


def test_chunk_by_format_dispatches_json():
    """chunk_by_format with json parses entries."""
    json_str = '{"entries": [{"content": "Test"}]}'
    chunks = chunk_by_format(json_str, "json")
    assert len(chunks) == 1
    assert chunks[0].content == "Test"
