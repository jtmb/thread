"""Multi-threaded concurrency tests for Thread.

Verifies thread safety of ConnectionPool, write serialization, git lock isolation,
and concurrent FTS5 searches under WAL mode.
"""

import threading
import time


from thread_server import models


def test_concurrent_reads_different_entries(pool, sample_entries):
    """Multiple threads reading different entries all return correct data."""
    errors = []
    entry_ids = [e["id"] for e in sample_entries]

    def read_entry(eid, expected_content):
        try:
            conn = pool.get()
            entry = models.get_entry(conn, eid)
            if entry is None:
                errors.append(f"Entry {eid} not found")
            elif expected_content not in entry["content"]:
                errors.append(f"Entry {eid} content mismatch")
        except Exception as exc:
            errors.append(f"Entry {eid}: {exc}")

    threads = []
    for i, eid in enumerate(entry_ids):
        t = threading.Thread(
            target=read_entry,
            args=(eid, f"Entry {i + 1}"),
        )
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Read errors: {errors}"


def test_concurrent_writes_to_same_session(pool, sample_session):
    """Multiple threads writing to the same session serialize via write lock.

    Each thread gets its own connection from the pool. All entries should
    be persisted without race conditions.
    """
    errors = []
    sid = sample_session["id"]
    lock = pool.write_lock()

    def write_entry(index):
        try:
            conn = pool.get()
            with lock:
                models.create_entry(
                    conn,
                    sid,
                    f"Concurrent write {index} from thread",
                    priority=5,
                )
        except Exception as exc:
            errors.append(f"Writer {index}: {exc}")

    threads = []
    for i in range(5):
        t = threading.Thread(target=write_entry, args=(i,))
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Write errors: {errors}"

    # Verify all 5 entries were created
    conn = pool.get()
    entries = models.list_entries(conn, sid, limit=10)
    concurrent_entries = [
        e for e in entries if "Concurrent write" in e["content"]
    ]
    assert len(concurrent_entries) == 5


def test_concurrent_search_and_insert(pool, sample_entries):
    """Simultaneous FTS5 searches and inserts don't interfere (WAL mode isolation)."""
    sid = sample_entries[0]["session_id"]
    search_results = []
    errors = []
    write_lock = pool.write_lock()

    def search_entries():
        try:
            conn = pool.get()
            results = models.search_entries(conn, sid, "sample", limit=10)
            search_results.append(len(results))
        except Exception as exc:
            errors.append(f"Search error: {exc}")

    def insert_entry():
        try:
            conn = pool.get()
            with write_lock:
                models.create_entry(conn, sid, "New entry for concurrent test", priority=5)
        except Exception as exc:
            errors.append(f"Insert error: {exc}")

    threads = []
    for _ in range(3):
        threads.append(threading.Thread(target=search_entries))
    threads.append(threading.Thread(target=insert_entry))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors: {errors}"
    assert all(r > 0 for r in search_results), "All searches should return results"


def test_git_lock_isolation(git_manager_path):
    """Commits to different sessions run in parallel (separate locks).

    Two threads committing to different repos should both complete quickly.
    """
    from thread_server.git_manager import GitManager

    mgr = GitManager(git_manager_path)
    mgr.ensure_repo("session-a")
    mgr.ensure_repo("session-b")

    # Create files so commits have content
    (mgr.ensure_repo("session-a") / "entries.jsonl").write_text('{"id":1}\n')
    (mgr.ensure_repo("session-b") / "entries.jsonl").write_text('{"id":2}\n')

    durations = []

    def commit_a():
        start = time.monotonic()
        mgr.commit_entry_added("session-a", 1)
        durations.append(("a", time.monotonic() - start))

    def commit_b():
        start = time.monotonic()
        mgr.commit_entry_added("session-b", 2)
        durations.append(("b", time.monotonic() - start))

    t_a = threading.Thread(target=commit_a)
    t_b = threading.Thread(target=commit_b)

    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join()

    # Both should complete in under 5 seconds (separate locks, no contention)
    for name, dur in durations:
        assert dur < 5.0, f"Commit {name} took {dur:.2f}s — expected <5s"
