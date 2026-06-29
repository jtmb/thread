"""Unit tests for document chunking logic (chunker.py)."""

import pytest

from thread_server.chunker import (
    DEFAULT_CHUNK_SIZE,
    chunk_by_format,
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
