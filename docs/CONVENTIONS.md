# Thread — Conventions

## Python

### Project Structure
- `thread_server/` — Pi server package. `__init__.py` is empty (package marker only).
- `thread_bridge/` — Workstation MCP bridge. Separate package, separate `requirements.txt`.
- `thread_server/routes/` — Flask blueprints. One file per resource.
- `tests/` — Parallel to source. `conftest.py` for shared fixtures.

### Docstrings
Google-style docstrings on all public functions:
```python
def get_session_by_name(db: sqlite3.Connection, name: str) -> dict | None:
    """Returns the session dict for the given name, or None if not found.

    Uses the covering index idx_sessions_name for index-only lookup.
    Result is cached via @lru_cache at the route level.

    Args:
        db: An active sqlite3.Connection with row_factory=sqlite3.Row.
        name: The session name to look up (case-sensitive).

    Returns:
        A dict with keys id, name, description, created_at, updated_at,
        or None if no session matches.
    """
```

### Type Hints
Mandatory on all public functions. Use `list[dict]`, `dict[str, int]`, `str | None` (Python 3.10+ syntax). No `Optional[...]` — use `| None`.

### Imports
- stdlib first, then third-party, then local.
- No `from module import *`. Explicit imports only.
- `import sqlite3` (not `from sqlite3 import connect` — clarity over brevity).

### Configuration
Single source of truth: `thread_server/config.py`. All env vars read here. No `os.environ.get(...)` anywhere else. Validate at startup — fail fast if required values are missing or invalid.

### Database Access
- Always go through `g.db` (set by `before_request` hook from the connection pool).
- Never open/close connections in route handlers.
- Use parameterized queries — never string-format SQL with user input.
- Write operations hold the write lock; read operations are lock-free (WAL mode).

### Logging
- Structured NDJSON via `logging_config.py`: every line is `{"timestamp":"...","level":"...","message":"...","requestId":"..."}`.
- Never `print()`, `console.log()`, or raw `logging.info()` without the JSON formatter.
- Log levels: `DEBUG` = developer details, `INFO` = key events, `WARNING` = recoverable problems, `ERROR` = needs attention.

### Error Handling
- Routes return standardized error dicts: `{"error": {"code": "...", "message": "...", "details": [], "requestId": "..."}}`.
- HTTP status codes: 400 (validation), 404 (not found), 409 (conflict), 413 (too large), 415 (unsupported), 500 (internal).
- Never expose stack traces or internal paths in API responses.

## Git

### Commit Messages
Format: `session(<name>): <action> entry(<id>)`
- `session(demo): added entry(42)`
- `session(project-alpha): updated entry(17)`
- `session(demo): deleted entry(3)`
- `session(demo): session created`
- `session(demo): session deleted`

Commits are best-effort — git failures are logged but never block the API response.

### Branch Naming
Conventional: `feat/description`, `fix/description`, `refactor/description`, `docs/description`, `test/description`.

### Atomic Commits
One logical change per commit. Don't bundle unrelated fixes.

## Testing

### Framework
`pytest` with fixtures in `tests/conftest.py`. No classes needed — use plain functions.

### Test File Naming
`tests/test_<module>.py` — mirrors source module names: `test_database.py`, `test_models.py`, `test_routes.py`.

### Test Structure
```python
def test_create_session_returns_dict_with_all_fields(db):
    """A session dict includes id, name, description, and timestamps."""
    session = models.create_session(db, "test", "desc")
    assert session["id"] is not None
    assert session["name"] == "test"

def test_create_session_duplicate_name_raises(db):
    """Creating a session with an existing name raises IntegrityError."""
    models.create_session(db, "test", "desc")
    with pytest.raises(sqlite3.IntegrityError):
        models.create_session(db, "test", "desc again")
```

### Test Coverage
- Every public function needs at least one test.
- Happy path + error path + edge cases (empty, null, boundary).
- Concurrency tests verify thread safety under load.

## Naming

| Category | Convention | Example |
|----------|-----------|---------|
| Modules | `snake_case.py` | `git_manager.py` |
| Classes | `PascalCase` | `ConnectionPool` |
| Functions | `snake_case` | `get_session_by_name()` |
| Variables | `snake_case` | `request_id` |
| Constants | `UPPER_CASE` | `MAX_PAGE_SIZE` |
| Blueprints | `{name}_bp` | `sessions_bp` |
| SQL Tables | `snake_case` | `entries_fts` |
| SQL Indexes | `idx_{table}_{columns}` | `idx_entries_session` |

## API Design

- **JSON only**: `Content-Type: application/json` for requests, all responses are JSON.
- **Standard error shape**: `{"error": {"code": "...", "message": "...", "details": [], "requestId": "..."}}`.
- **Cursor pagination**: `?after=<id>&limit=<n>` (not offset-based).
- **201 with Location header**: On resource creation.
- **204 No Content**: On successful deletes.
- **207 Multi-Status**: For partial-success bulk operations.

## VS Code & GitHub Metadata

### Directory Layout
```
.github/
├── copilot-instructions.md   # Stub: tells Copilot to load skills
├── skills/                   # Portable skill definitions
│   └── thread-auto-context/  # Thread auto-context saving rules
│       └── SKILL.md
├── instructions/             # Framework/language overlays (applyTo globs)
├── prompts/                  # Reusable prompt templates
└── agents/                   # Custom agent definitions
.vscode/
├── mcp.example.json          # Template — copy to mcp.json and fill paths
└── mcp.json                  # Actual MCP config (gitignored — has absolute paths)
```

### `.github/skills/` — Copilot Skills
- Each skill is a directory under `.github/skills/` containing a `SKILL.md` with YAML frontmatter
- Skills are portable — copy the directory to any project's `.github/skills/` to use it there
- `alwaysApply: true` in frontmatter means Copilot loads the skill automatically without explicit request
- **`thread-auto-context`** — The auto-context skill. Tells Copilot to search/save Thread entries proactively

### `.github/copilot-instructions.md` — Skill Loader Stub
- Minimal file (5 lines) that tells Copilot to load and follow skills
- Does NOT contain the full rules — those live in `SKILL.md` files
- Pattern: "Always load and follow the **X** skill (`.github/skills/X/SKILL.md`)."

### `.vscode/mcp.json` — MCP Server Config
- Workspace-level MCP server configuration (VS Code 1.99+)
- Auto-created by the `thread-auto-context` skill if missing
- Contains `servers.thread` entry with `type: "stdio"`, bridge path, env vars
- Format: `{"servers": {...}, "inputs": []}` — `servers` is a map, not `mcpServers`
- If the file already exists, merge `servers.thread` — don't overwrite existing servers or inputs
