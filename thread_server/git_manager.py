"""Git integration for per-session versioning — audit trail for context mutations.

Design:
- One git repo per session at data/git/<session_name>/
- Lazy initialization: repos are created on first mutation
- Thread-safe: per-repo threading.Lock prevents git race conditions
- Best-effort: git failures are logged but never block API responses

The DB transaction is the source of truth; git is an audit trail.
"""

import logging
import subprocess
import threading
from pathlib import Path

from thread_server import config

logger = logging.getLogger(__name__)

# Shared lock dict — one lock per repo path
_repo_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


class GitManager:
    """Per-session git repository manager with thread-safe commits.

    Each session gets its own git repo under data/git/<session_name>/.
    Commits happen after every entry CRUD operation with meaningful messages.
    """

    def __init__(self, base_path: str = ""):
        """Initialize the git manager.

        Args:
            base_path: Root directory for git repos. Uses config.GIT_BASE if empty.
        """
        self._base_path = Path(base_path or config.GIT_BASE)
        self._base_path.mkdir(parents=True, exist_ok=True)
        logger.info("Git manager initialized at %s", self._base_path)

    def ensure_repo(self, session_name: str) -> Path:
        """Ensure a git repository exists for the given session.

        Creates the repo if needed. Configures git user if not already set.
        Thread-safe: only one thread can initialize a given repo.

        Args:
            session_name: The normalized session name (directory-safe).

        Returns:
            Path to the repository directory.
        """
        repo_path = self._base_path / session_name
        lock = self._get_repo_lock(str(repo_path))

        with lock:
            if not (repo_path / ".git").exists():
                repo_path.mkdir(parents=True, exist_ok=True)
                self._git(repo_path, "init")
                # Configure git identity for commits
                self._git(repo_path, "config", "user.email", "thread@localhost")
                self._git(repo_path, "config", "user.name", "Thread Server")
                logger.info("Initialized git repo for session '%s'", session_name)

            return repo_path

    def _get_repo_lock(self, repo_path_str: str) -> threading.Lock:
        """Get or create a per-repo threading.Lock.

        Separate locks per repo so different sessions can commit in parallel.
        """
        with _locks_lock:
            if repo_path_str not in _repo_locks:
                _repo_locks[repo_path_str] = threading.Lock()
            return _repo_locks[repo_path_str]

    def _git(self, repo_path: Path, *args: str) -> subprocess.CompletedProcess:
        """Run a git command in the given repository.

        Args:
            repo_path: Path to the git repository.
            *args: Git subcommand and arguments.

        Returns:
            The completed subprocess result.

        Raises:
            subprocess.CalledProcessError: If git exits non-zero.
        """
        cmd = ["git", "-C", str(repo_path)] + list(args)
        logger.debug("Running: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            if result.stdout.strip():
                logger.debug("git output: %s", result.stdout.strip())
            return result
        except subprocess.CalledProcessError as e:
            logger.error(
                "git command failed: %s\nstdout: %s\nstderr: %s",
                " ".join(cmd),
                e.stdout.strip() if e.stdout else "",
                e.stderr.strip() if e.stderr else "",
            )
            raise

    def _commit(self, session_name: str, message: str) -> None:
        """Stage all changes and commit. Best-effort — failures are logged.

        Args:
            session_name: The session name (used for the commit message).
            message: Commit message (description of what changed).
        """
        try:
            repo_path = self._base_path / session_name
            if not (repo_path / ".git").exists():
                logger.debug("Repo not yet initialized for session '%s'", session_name)
                return

            lock = self._get_repo_lock(str(repo_path))
            with lock:
                # Check if there's anything to commit
                status = subprocess.run(
                    ["git", "-C", str(repo_path), "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if not status.stdout.strip():
                    logger.debug("No changes to commit in session '%s'", session_name)
                    return

                self._git(repo_path, "add", ".")
                self._git(repo_path, "commit", "-m", message)
                logger.info("Committed: %s", message)

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            logger.warning("Git commit failed (non-fatal): %s — %s", message, e)

    # ── Public commit methods ──────────────────────────────────────────────

    def commit_session_created(self, session_name: str) -> None:
        """Commit after a new session is created."""
        repo_path = self.ensure_repo(session_name)
        # Create a placeholder file so there's something to commit
        (repo_path / "session.json").write_text('{"name": "' + session_name + '"}')
        self._commit(session_name, f"session({session_name}): created")

    def commit_session_deleted(self, session_name: str) -> None:
        """Commit after a session is deleted.

        In practice this may not be useful since the repo is typically removed,
        but we record it for completeness.
        """
        self._commit(session_name, f"session({session_name}): deleted")

    def commit_entry_added(self, session_name: str, entry_id: int) -> None:
        """Commit after an entry is created."""
        self.ensure_repo(session_name)
        self._commit(session_name, f"session({session_name}): added entry({entry_id})")

    def commit_entry_updated(self, session_name: str, entry_id: int) -> None:
        """Commit after an entry is updated."""
        self._commit(session_name, f"session({session_name}): updated entry({entry_id})")

    def commit_entry_deleted(self, session_name: str, entry_id: int) -> None:
        """Commit after an entry is deleted."""
        self._commit(session_name, f"session({session_name}): deleted entry({entry_id})")


# Module-level singleton — created in create_app()
git_manager: GitManager | None = None


def init_git_manager() -> GitManager:
    """Create and return the global git manager singleton."""
    global git_manager
    git_manager = GitManager()
    return git_manager
