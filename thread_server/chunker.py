"""Document chunking for file upload and CLI import.

Splits incoming documents into entry-sized pieces (~2KB target) using
format-aware strategies. Shared by the POST /upload endpoint and the
CLI import tool.
"""

from dataclasses import dataclass, field
import json
import logging
import re

logger = logging.getLogger(__name__)

# File format constants
FORMAT_MARKDOWN = "markdown"
FORMAT_TEXT = "text"
FORMAT_JSON = "json"

# Binary detection: reject files with null bytes in the first 1024 bytes
_BINARY_THRESHOLD = 1024

# Chunk size target for plaintext splitting
DEFAULT_CHUNK_SIZE = 2048

# Short paragraph threshold — paragraphs below this get merged with neighbors
SHORT_PARAGRAPH_THRESHOLD = 500

# Markdown heading pattern: ## Title or # Title
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class Chunk:
    """A single chunk of document content ready to become an entry.

    Attributes:
        content: The chunked text content.
        index: 0-based position in the original document.
        heading: Parent heading for context (markdown only, None for text).
    """
    content: str
    index: int
    heading: str | None = None


# ── Public API ──────────────────────────────────────────────────────────────────


def detect_format(filename: str) -> str:
    """Detect the document format from the file extension.

    Args:
        filename: The uploaded filename or file path.

    Returns:
        One of FORMAT_MARKDOWN, FORMAT_TEXT, or FORMAT_JSON.

    Raises:
        ValueError: If the format is not supported.
    """
    lower = filename.lower()
    if lower.endswith(".md") or lower.endswith(".markdown"):
        return FORMAT_MARKDOWN
    if lower.endswith(".txt") or lower.endswith(".text"):
        return FORMAT_TEXT
    if lower.endswith(".json"):
        return FORMAT_JSON
    raise ValueError(f"Unsupported file format: {filename}")


def chunk_by_format(
    text: str,
    fmt: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[Chunk]:
    """Dispatch chunking to the appropriate strategy based on format.

    Args:
        text: The full file content as a string.
        fmt: One of FORMAT_MARKDOWN, FORMAT_TEXT, FORMAT_JSON.
        chunk_size: Target chunk size in characters (plaintext only).

    Returns:
        List of Chunk objects. Empty list for empty files.

    Raises:
        ValueError: If the format is unknown.
    """
    if fmt == FORMAT_MARKDOWN:
        return chunk_markdown(text)
    elif fmt == FORMAT_TEXT:
        return chunk_plaintext(text, chunk_size)
    elif fmt == FORMAT_JSON:
        chunks = parse_json_entries(text)
        return [Chunk(content=c["content"], index=i) for i, c in enumerate(chunks)]
    raise ValueError(f"Unknown format: {fmt}")


def is_binary(data: bytes) -> bool:
    """Detect binary content by checking for null bytes in the first 1KB.

    Args:
        data: First chunk of file bytes (up to 1024 bytes).

    Returns:
        True if the content appears to be binary.
    """
    return b"\x00" in data[: _BINARY_THRESHOLD]


# ── Markdown Chunking ───────────────────────────────────────────────────────────


def chunk_markdown(text: str) -> list[Chunk]:
    """Split markdown by ## headings (fallback to # if no subheadings).

    Each heading section becomes one entry. The heading is prepended to the
    chunk content for context. Very long sections (>10KB) are further split
    at paragraph boundaries within the section.

    Args:
        text: Full markdown document text.

    Returns:
        List of Chunk objects. Empty list for empty documents.
    """
    if not text.strip():
        return []

    # Find all heading positions
    headings = list(_MD_HEADING_RE.finditer(text))
    if not headings:
        # No headings at all — treat entire document as one chunk
        return _chunk_long_text(text, heading=None)

    # Try ## first, fall back to # if no ## headings exist
    h2_headings = [(m, m.group(1), m.group(2)) for m in headings if len(m.group(1)) == 2]
    if h2_headings:
        split_headings = h2_headings
    else:
        split_headings = [(m, m.group(1), m.group(2)) for m in headings]

    chunks: list[Chunk] = []
    current_heading: str | None = None

    for i, (match, level, title) in enumerate(split_headings):
        heading_text = f"{'#' * len(level)} {title}"
        # Determine section boundaries
        start = match.end() + 1  # +1 to skip newline after heading
        if i + 1 < len(split_headings):
            end = split_headings[i + 1][0].start()
        else:
            end = len(text)

        section = text[start:end].strip()

        if len(level) <= 2:
            # ## or # → new major section
            current_heading = heading_text
            for chunk in _chunk_long_text(section, heading=current_heading):
                chunk.index = len(chunks)
                chunks.append(chunk)
        else:
            # ### or deeper → subsection of current heading
            for chunk in _chunk_long_text(section, heading=current_heading):
                chunk.index = len(chunks)
                chunks.append(chunk)

    # If no headings were used for splitting, treat whole doc as one section
    if not chunks and text.strip():
        for chunk in _chunk_long_text(text.strip(), heading=None):
            chunk.index = len(chunks)
            chunks.append(chunk)

    return chunks


def _chunk_long_text(text: str, heading: str | None = None) -> list[Chunk]:
    """Split long text at paragraph boundaries, merging short paragraphs.

    Sections longer than ~10KB are split further to keep entries manageable.
    Short consecutive paragraphs (<500 chars) are merged into one chunk.

    Args:
        text: The text to potentially split.
        heading: The parent heading context.

    Returns:
        List of Chunk objects.
    """
    if len(text) <= DEFAULT_CHUNK_SIZE * 2:
        # Short enough — keep as single chunk
        content = f"{heading}\n\n{text}" if heading else text
        return [Chunk(content=content, index=0, heading=heading)]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    merged: list[str] = []
    chunks: list[Chunk] = []

    for para in paragraphs:
        merged.append(para)
        combined = "\n\n".join(merged)
        if len(combined) >= DEFAULT_CHUNK_SIZE:
            content = f"{heading}\n\n{combined}" if heading else combined
            chunks.append(Chunk(content=content, index=len(chunks), heading=heading))
            merged = []

    # Don't forget the tail
    if merged:
        combined = "\n\n".join(merged)
        content = f"{heading}\n\n{combined}" if heading else combined
        chunks.append(Chunk(content=content, index=len(chunks), heading=heading))

    return chunks


# ── Plaintext Chunking ──────────────────────────────────────────────────────────


def chunk_plaintext(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[Chunk]:
    """Split plain text at paragraph boundaries, merging short paragraphs.

    Strategy:
    1. Split on double newline (paragraph boundaries)
    2. Merge consecutive short paragraphs (<500 chars) until chunk_size is reached
    3. If a single paragraph exceeds 2x chunk_size, split at sentence boundaries
    4. If no paragraph breaks exist, split at ~chunk_size character boundaries
       at sentence endings

    Args:
        text: Full plaintext document.
        chunk_size: Target chunk size in characters.

    Returns:
        List of Chunk objects. Empty list for empty input.
    """
    if not text.strip():
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    if len(paragraphs) == 1:
        # Single paragraph — split by sentences if long
        return _chunk_by_sentences(paragraphs[0], chunk_size)

    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_len = 0

    for para in paragraphs:
        if len(para) > chunk_size * 2:
            # Flush buffer first
            if buffer:
                chunks.append(Chunk(content="\n\n".join(buffer), index=len(chunks)))
                buffer = []
                buffer_len = 0
            # Split this long paragraph
            for sub in _chunk_by_sentences(para, chunk_size):
                sub.index = len(chunks)
                chunks.append(sub)
            continue

        para_len = len(para)
        if buffer_len + para_len >= chunk_size and buffer:
            chunks.append(Chunk(content="\n\n".join(buffer), index=len(chunks)))
            buffer = [para]
            buffer_len = para_len
        else:
            buffer.append(para)
            buffer_len += para_len

    if buffer:
        chunks.append(Chunk(content="\n\n".join(buffer), index=len(chunks)))

    return chunks


def _chunk_by_sentences(text: str, chunk_size: int) -> list[Chunk]:
    """Split text at sentence boundaries (~. ! ? followed by space/newline).

    Falls back to character-limit splitting if no sentence boundaries found.
    """
    # Find sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) <= 1:
        # No sentence boundaries — split by character count
        return [
            Chunk(content=text[i : i + chunk_size], index=j)
            for j, i in enumerate(range(0, len(text), chunk_size))
        ]

    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_len = 0

    for sent in sentences:
        sent_len = len(sent)
        if buffer_len + sent_len >= chunk_size and buffer:
            chunks.append(Chunk(content=" ".join(buffer), index=len(chunks)))
            buffer = [sent]
            buffer_len = sent_len
        else:
            buffer.append(sent)
            buffer_len += sent_len

    if buffer:
        chunks.append(Chunk(content=" ".join(buffer), index=len(chunks)))

    return chunks


# ── JSON Parsing ────────────────────────────────────────────────────────────────


def parse_json_entries(text: str) -> list[dict]:
    """Parse a JSON import file into entry dicts.

    Expected format: {"entries": [{"content": "...", "priority": 5, "tags": [...]}, ...]}

    Args:
        text: Raw JSON string.

    Returns:
        List of entry dicts ready for bulk creation.

    Raises:
        ValueError: If JSON is malformed or missing the 'entries' key.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object with an 'entries' key")

    entries = data.get("entries")
    if entries is None:
        raise ValueError("JSON must contain an 'entries' key")

    if not isinstance(entries, list):
        raise ValueError("'entries' must be a list")

    return entries
