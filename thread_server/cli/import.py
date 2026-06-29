#!/usr/bin/env python3
"""CLI tool for bulk document ingestion into a Thread session.

Two modes:
  1. HTTP mode (--url): Pushes chunks via the Thread server API.
     Run from a workstation — the Pi handles chunking & DB.
  2. Direct mode (--db): Writes directly to the SQLite database.
     Run on the Pi itself — much faster, bypasses HTTP entirely.

Usage:
    # Workstation mode — push via HTTP API
    python -m thread_server.cli.import \\
        --url http://pi:5000 \\
        --session my-docs \\
        --dir ./documentation/ \\
        --tags "reference,manual" \\
        --priority 8

    # Pi direct mode — write directly to the database
    python -m thread_server.cli.import \\
        --db data/thread.db \\
        --session my-docs \\
        --dir ./docs/

Behavior:
    - Walks --dir recursively for .md, .txt, .json files
    - Chunks each file via chunker.py (reuses upload endpoint logic)
    - HTTP mode: pushes chunks in batches of 50 via /bulk endpoint
    - DB mode: uses models.create_entry() directly
    - Skips binary files, reports unsupported formats, shows progress
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Setup logging before importing project modules
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Parse CLI args and dispatch to the correct import mode."""
    parser = argparse.ArgumentParser(
        description="Import documents into a Thread context session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # HTTP mode (from workstation to Pi)
  python -m thread_server.cli.import --url http://192.168.1.50:5000 --session docs --dir ./notes/ 

  # Direct mode (on the Pi itself — fastest)
  python -m thread_server.cli.import --db data/thread.db --session docs --dir ./data/imports/
        """,
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--url",
        help="Thread server URL for HTTP mode (e.g., http://pi:5000)",
    )
    mode_group.add_argument(
        "--db",
        help="Path to SQLite database for direct mode (e.g., data/thread.db)",
    )

    parser.add_argument(
        "--session",
        required=True,
        help="Target session name",
    )
    parser.add_argument(
        "--dir",
        required=True,
        help="Directory to scan for documents (.md, .txt, .json)",
    )
    parser.add_argument(
        "--tags",
        default="",
        help="Comma-separated tags applied to all entries",
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=5,
        help="Priority 0-10 for all entries (default: 5)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=2048,
        help="Target chunk size for .txt files (default: 2048)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for HTTP bulk creation (default: 50)",
    )

    args = parser.parse_args()

    if args.url:
        _import_via_http(args)
    else:
        _import_via_db(args)


# ── HTTP Mode ───────────────────────────────────────────────────────────────


def _import_via_http(args) -> None:
    """Import via the Thread server HTTP API. Runs from a workstation.

    Walks --dir, chunks files via chunker.py, then pushes chunks
    in batches via the /bulk endpoint and file uploads.
    """
    import requests

    from thread_server.chunker import chunk_by_format, detect_format, is_binary

    logger.info("HTTP mode: server=%s, session=%s, dir=%s", args.url, args.session, args.dir)

    base_url = args.url.rstrip("/")
    session_url = f"{base_url}/api/v1/sessions/{args.session}"
    bulk_url = f"{session_url}/entries/bulk"

    # Ensure the session exists (create if needed)
    try:
        resp = requests.get(session_url, timeout=10)
        if resp.status_code == 404:
            logger.info("Session '%s' does not exist — creating it", args.session)
            resp = requests.post(
                f"{base_url}/api/v1/sessions",
                json={"name": args.session},
                timeout=10,
            )
            if not resp.ok:
                logger.error("Failed to create session: %s", resp.text)
                sys.exit(1)
            logger.info("Session created")
        elif not resp.ok:
            logger.error("Failed to check session: %s", resp.text)
            sys.exit(1)
    except requests.RequestException as e:
        logger.error("Connection error: %s", e)
        sys.exit(1)

    # Collect files
    src_dir = Path(args.dir)
    if not src_dir.is_dir():
        logger.error("Directory not found: %s", args.dir)
        sys.exit(1)

    files = _collect_files(src_dir)
    logger.info("Found %d files to import", len(files))

    total_entries = 0
    total_errors = 0

    for file_path in files:
        rel_path = file_path.relative_to(src_dir)
        logger.info("Processing: %s", rel_path)

        # Read the file
        try:
            with open(file_path, "rb") as f:
                data = f.read()

            # Skip binary files
            if is_binary(data):
                logger.warning("Skipping binary file: %s", rel_path)
                continue

            text = data.decode("utf-8")
        except (UnicodeDecodeError, OSError) as e:
            logger.warning("Skipping unreadable file: %s — %s", rel_path, e)
            total_errors += 1
            continue

        # Detect format
        try:
            fmt = detect_format(str(file_path))
        except ValueError:
            logger.warning("Skipping unsupported format: %s", rel_path)
            total_errors += 1
            continue

        # Chunk the document
        try:
            chunks = chunk_by_format(text, fmt, chunk_size=args.chunk_size)
        except ValueError as e:
            logger.warning("Chunking failed for %s: %s", rel_path, e)
            total_errors += 1
            continue

        if not chunks:
            logger.warning("No content extracted from %s", rel_path)
            continue

        # Build entries array from chunks
        tags_list = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None

        entries_payload = [
            {
                "content": chunk.content,
                "priority": args.priority,
                "tags": tags_list,
            }
            for chunk in chunks
        ]

        # Push in batches
        for batch_start in range(0, len(entries_payload), args.batch_size):
            batch = entries_payload[batch_start : batch_start + args.batch_size]
            try:
                resp = requests.post(
                    bulk_url,
                    json={"entries": batch},
                    timeout=30,
                )
                result = resp.json()
                created = result.get("created", 0)
                failed = result.get("failed", 0)
                total_entries += created
                total_errors += failed

                logger.info(
                    "  %s: %d entries, %d chunks → %d created, %d failed",
                    rel_path,
                    len(entries_payload),
                    len(batch),
                    created,
                    failed,
                )

                if failed:
                    for err in result.get("errors", []):
                        logger.warning("    Chunk %d: %s", err.get("index", "?"), err.get("message", "unknown"))
            except requests.RequestException as e:
                logger.error("Batch push failed: %s", e)
                total_errors += len(batch)

    logger.info(
        "Import complete: %d entries created, %d errors",
        total_entries,
        total_errors,
    )


# ── Direct DB Mode ──────────────────────────────────────────────────────────


def _import_via_db(args) -> None:
    """Import directly into the SQLite database. Runs on the Pi.

    Much faster than HTTP mode (no network overhead, no JSON serialization).
    Uses the same chunker.py module as the upload endpoint.
    """
    import sqlite3

    from thread_server import config as server_config, models
    from thread_server.chunker import chunk_by_format, detect_format, is_binary

    logger.info("Direct DB mode: db=%s, session=%s, dir=%s", args.db, args.session, args.dir)

    # Connect to the database
    db_path = Path(args.db)
    if not db_path.exists():
        logger.error("Database not found: %s", args.db)
        sys.exit(1)

    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row

    # Apply pragmas for fast writes
    for pragma in server_config.PRAGMAS:
        try:
            db.execute(pragma)
        except sqlite3.OperationalError:
            pass  # Some pragmas may not apply to an already-open DB

    # Ensure the session exists
    session = models.get_session_by_name(db, args.session)
    if session is None:
        logger.info("Session '%s' does not exist — creating it", args.session)
        session = models.create_session(db, args.session)
    session_id = session["id"]

    # Collect files
    src_dir = Path(args.dir)
    if not src_dir.is_dir():
        logger.error("Directory not found: %s", args.dir)
        db.close()
        sys.exit(1)

    files = _collect_files(src_dir)
    logger.info("Found %d files to import", len(files))

    total_entries = 0
    total_errors = 0
    tags_list = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None

    for file_path in files:
        rel_path = file_path.relative_to(src_dir)
        logger.info("Processing: %s", rel_path)

        # Read the file
        try:
            with open(file_path, "rb") as f:
                data = f.read()

            # Skip binary files
            if is_binary(data):
                logger.warning("Skipping binary file: %s", rel_path)
                continue

            text = data.decode("utf-8")
        except (UnicodeDecodeError, OSError) as e:
            logger.warning("Skipping unreadable file: %s — %s", rel_path, e)
            total_errors += 1
            continue

        # Detect format
        try:
            fmt = detect_format(str(file_path))
        except ValueError:
            logger.warning("Skipping unsupported format: %s", rel_path)
            total_errors += 1
            continue

        # Chunk the document
        try:
            chunks = chunk_by_format(text, fmt, chunk_size=args.chunk_size)
        except ValueError as e:
            logger.warning("Chunking failed for %s: %s", rel_path, e)
            total_errors += 1
            continue

        if not chunks:
            logger.warning("No content extracted from %s", rel_path)
            continue

        # Insert entries directly into the database
        file_created = 0
        file_errors = 0

        for chunk in chunks:
            try:
                models.create_entry(
                    db,
                    session_id,
                    chunk.content,
                    priority=args.priority,
                    tags=tags_list,
                )
                file_created += 1
            except ValueError as e:
                logger.warning("  Chunk %d: %s", chunk.index, e)
                file_errors += 1

        total_entries += file_created
        total_errors += file_errors

        logger.info(
            "  %s: %d entries created, %d errors",
            rel_path,
            file_created,
            file_errors,
        )

    db.close()
    logger.info(
        "Import complete: %d entries created, %d errors",
        total_entries,
        total_errors,
    )


# ── Helpers ─────────────────────────────────────────────────────────────────


def _collect_files(src_dir: Path) -> list[Path]:
    """Recursively collect supported document files from a directory.

    Returns a sorted list of .md, .txt, and .json file paths.

    Args:
        src_dir: The directory to walk.

    Returns:
        Sorted list of matching Path objects.
    """
    extensions = {".md", ".markdown", ".txt", ".text", ".json"}
    files: list[Path] = []

    for root, _dirs, filenames in os.walk(src_dir):
        for filename in filenames:
            file_path = Path(root) / filename
            if file_path.suffix.lower() in extensions:
                files.append(file_path)

    files.sort(key=lambda p: (p.suffix, str(p)))
    return files


if __name__ == "__main__":
    main()
