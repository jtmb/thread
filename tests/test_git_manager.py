"""Unit tests for GitManager — per-session git versioning."""

import os
import subprocess

import pytest

from thread_server.git_manager import GitManager


def _git_init(path):
    """Helper: initialize a bare git repo for testing."""
    subprocess.run(
        ["git", "init", path],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", path, "config", "user.email", "test@thread.local"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", path, "config", "user.name", "Thread Test"],
        capture_output=True,
        check=True,
    )


def test_ensure_repo_creates_directory(git_manager_path):
    """ensure_repo creates the git directory if missing."""
    mgr = GitManager(git_manager_path)
    repo = mgr.ensure_repo("test-session")
    assert repo.exists()
    assert (repo / ".git").is_dir()


def test_ensure_repo_is_idempotent(git_manager_path):
    """Calling ensure_repo twice doesn't error."""
    mgr = GitManager(git_manager_path)
    mgr.ensure_repo("test-session")
    mgr.ensure_repo("test-session")  # Should not raise


def test_commit_entry_added_creates_commit(git_manager_path):
    """commit_entry_added creates a git commit with the correct message."""
    mgr = GitManager(git_manager_path)
    mgr.ensure_repo("test-session")

    # Create a file so there's something to commit
    entry_file = mgr.ensure_repo("test-session") / "entries.jsonl"
    entry_file.write_text('{"id": 1, "content": "test"}\n')

    mgr.commit_entry_added("test-session", 42)

    result = subprocess.run(
        ["git", "-C", str(mgr.ensure_repo("test-session")), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "added entry(42)" in result.stdout
    assert "session(test-session)" in result.stdout


def test_commit_entry_updated_creates_commit(git_manager_path):
    """commit_entry_updated creates a commit with update message."""
    mgr = GitManager(git_manager_path)
    mgr.ensure_repo("test-session")

    entry_file = mgr.ensure_repo("test-session") / "entries.jsonl"
    entry_file.write_text('{"id": 1, "content": "updated"}\n')

    mgr.commit_entry_updated("test-session", 17)

    result = subprocess.run(
        ["git", "-C", str(mgr.ensure_repo("test-session")), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "updated entry(17)" in result.stdout


def test_commit_entry_deleted_creates_commit(git_manager_path):
    """commit_entry_deleted creates a commit with delete message."""
    mgr = GitManager(git_manager_path)
    mgr.ensure_repo("test-session")

    entry_file = mgr.ensure_repo("test-session") / "entries.jsonl"
    entry_file.write_text('{"id": 1, "content": "deleted"}\n')

    mgr.commit_entry_deleted("test-session", 3)

    result = subprocess.run(
        ["git", "-C", str(mgr.ensure_repo("test-session")), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "deleted entry(3)" in result.stdout


def test_commit_session_created(git_manager_path):
    """commit_session_created creates a session creation commit."""
    mgr = GitManager(git_manager_path)
    mgr.commit_session_created("new-session")

    repo = mgr.ensure_repo("new-session")
    result = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "session(new-session): created" in result.stdout


def test_commit_format_is_standard(git_manager_path):
    """All commit messages follow the session(name): action entry(id) format."""
    mgr = GitManager(git_manager_path)
    mgr.ensure_repo("format-test")

    entry_file = mgr.ensure_repo("format-test") / "entries.jsonl"
    entry_file.write_text('{"id": 1, "content": "x"}\n')

    mgr.commit_entry_added("format-test", 1)

    result = subprocess.run(
        ["git", "-C", str(mgr.ensure_repo("format-test")), "log", "--format=%s"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "session(format-test): added entry(1)"


def test_git_failures_dont_raise(git_manager_path):
    """Git failures are best-effort and don't propagate exceptions."""
    mgr = GitManager(git_manager_path)
    # No repo created — commit should fail silently
    # This should not raise
    mgr.commit_entry_added("nonexistent-session", 99)
