# Thread — API Reference

> Base URL: `http://<pi-ip>:5000/api/v1`

All responses are JSON. All errors follow the standard shape:
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description",
    "details": [],
    "requestId": "req_abc123"
  }
}
```

---

## Health & Stats

### `GET /api/v1/health`

Health check. Returns 200 if the server is operational.

**Response (200):**
```json
{
  "status": "ok",
  "timestamp": "2025-01-15T10:30:00Z",
  "version": "0.1.0"
}
```

When `THREAD_DEBUG=true`, includes diagnostics:
```json
{
  "status": "ok",
  "timestamp": "2025-01-15T10:30:00Z",
  "version": "0.1.0",
  "debug": {
    "pool": {"active": 3, "total": 12, "max": 12},
    "db_size_bytes": 2048000,
    "uptime_seconds": 3600
  }
}
```

### `GET /api/v1/stats`

Server performance metrics.

**Response (200):**
```json
{
  "server": {"uptime_seconds": 3600, "version": "0.1.0"},
  "db": {
    "size_bytes": 2048000,
    "total_entries": 15420,
    "total_sessions": 12,
    "wal_size_bytes": 4096
  },
  "pool": {
    "active_connections": 8,
    "total_connections": 12,
    "max_connections": 12,
    "utilization_pct": 66
  },
  "cache": {
    "session_hits": 1450, "session_misses": 12,
    "search_hits": 320, "search_misses": 45,
    "search_entries": 128, "search_max": 128
  },
  "requests": {
    "total": 5000,
    "avg_latency_ms": 8.5,
    "p99_latency_ms": 45
  }
}
```

---

## Sessions

### `GET /api/v1/sessions`

List all sessions.

**Response (200):**
```json
[
  {"id": 1, "name": "demo", "description": "...", "created_at": "...", "updated_at": "..."},
  {"id": 2, "name": "project-alpha", "description": "...", "created_at": "...", "updated_at": "..."}
]
```

### `POST /api/v1/sessions`

Create a new session.

**Request:**
```json
{
  "name": "my-session",
  "description": "Optional description"
}
```

**Response (201):**
```json
{
  "id": 1,
  "name": "my-session",
  "description": "Optional description",
  "created_at": "2025-01-15T10:30:00",
  "updated_at": "2025-01-15T10:30:00"
}
```
Includes `Location: /api/v1/sessions/my-session` header.

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 400 | `VALIDATION` | `name` is missing or empty |
| 409 | `CONFLICT` | Session with this name already exists |

### `GET /api/v1/sessions/<name>`

Get a session by name.

**Response (200):** Same shape as POST response.

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `NOT_FOUND` | No session with this name |

### `DELETE /api/v1/sessions/<name>`

Delete a session and all its entries (cascading).

**Response (204):** Empty body.

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `NOT_FOUND` | No session with this name |

---

## Entries

All entry endpoints are scoped to a session: `/api/v1/sessions/<name>/entries`

### `GET /api/v1/sessions/<name>/entries`

List entries with cursor-based pagination. Returns newest first.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `after` | int | none | Return entries with id less than this value (for cursor pagination) |
| `limit` | int | `50` | Max entries to return (capped at `THREAD_MAX_PAGE_SIZE`, default 200) |

**Response (200):**
```json
[
  {
    "id": 42,
    "session_id": 1,
    "content": "Entry content here...",
    "priority": 7,
    "tags": ["python", "api"],
    "created_at": "2025-01-15T10:30:00",
    "updated_at": "2025-01-15T10:30:00"
  }
]
```

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `NOT_FOUND` | Session not found |

**Pagination:** Clients should use the smallest `id` from the current page as `after` for the next page. Example: `GET /entries?limit=50` → gets ids 100-51; `GET /entries?limit=50&after=51` → gets ids 50-1.

### `POST /api/v1/sessions/<name>/entries`

Create a single entry.

**Request:**
```json
{
  "content": "This is the entry text",
  "priority": 7,
  "tags": ["python", "reference"]
}
```

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `content` | string | yes | — | Non-empty |
| `priority` | integer | no | `5` | 0–10 |
| `tags` | array of strings | no | `[]` | — |

**Response (201):**
```json
{
  "id": 1,
  "session_id": 1,
  "content": "This is the entry text",
  "priority": 7,
  "tags": ["python", "reference"],
  "created_at": "2025-01-15T10:30:00",
  "updated_at": "2025-01-15T10:30:00"
}
```
Includes `Location: /api/v1/sessions/<name>/entries/1` header.

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 400 | `VALIDATION` | `content` missing/empty, priority out of range, tags not an array |
| 404 | `NOT_FOUND` | Session not found |

### `GET /api/v1/sessions/<name>/entries/<id>`

Get a single entry by ID.

**Response (200):** Same shape as POST response.

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `NOT_FOUND` | Session or entry not found |

### `PUT /api/v1/sessions/<name>/entries/<id>`

Update an entry. Partial updates supported — only include fields you want to change.

**Request:**
```json
{
  "content": "Updated content",
  "priority": 9
}
```

**Response (200):** Updated entry dict.

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 400 | `VALIDATION` | Invalid field values |
| 404 | `NOT_FOUND` | Session or entry not found |

### `DELETE /api/v1/sessions/<name>/entries/<id>`

Delete an entry.

**Response (204):** Empty body.

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `NOT_FOUND` | Session or entry not found |

### `POST /api/v1/sessions/<name>/entries/batch`

Batch read — fetch multiple entries by ID in a single request.

**Request:**
```json
{
  "ids": [1, 5, 12, 42]
}
```

**Response (200):**
```json
[
  {"id": 1, "content": "...", "priority": 7, ...},
  {"id": 5, "content": "...", "priority": 3, ...}
]
```
Missing IDs are silently omitted. Up to `THREAD_MAX_PAGE_SIZE` IDs.

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 400 | `VALIDATION` | `ids` missing or not an array of integers |
| 404 | `NOT_FOUND` | Session not found |

### `POST /api/v1/sessions/<name>/entries/bulk`

Bulk create — create up to 100 entries in a single request.

**Request:**
```json
{
  "entries": [
    {"content": "First entry", "priority": 8, "tags": ["tag1"]},
    {"content": "Second entry", "priority": 5},
    {"content": ""}
  ]
}
```

**Response (207 Multi-Status):**
```json
{
  "created": 2,
  "failed": 1,
  "entries": [
    {"id": 101, "content": "First entry", ...},
    {"id": 102, "content": "Second entry", ...}
  ],
  "errors": [
    {"index": 2, "code": "VALIDATION", "message": "content is required"}
  ]
}
```

| Field | Type | Required | Default | Max |
|-------|------|----------|---------|-----|
| `entries` | array | yes | — | 100 |

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 400 | `VALIDATION` | `entries` missing/empty or exceeds 100 |
| 404 | `NOT_FOUND` | Session not found |

### `POST /api/v1/sessions/<name>/entries/upload`

Upload and chunk a file into entries. Supports Markdown (`.md`), plain text (`.txt`), and JSON (`.json`).

**Request:** `multipart/form-data`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `file` | file | yes | — | File to upload (max 4MB) |
| `tags` | string | no | `""` | Comma-separated tags applied to all created entries |
| `priority` | integer | no | `5` | Priority 0-10 for all created entries |
| `chunk_size` | integer | no | `2048` | Target chunk size in chars (plain text only) |

**Chunking by format:**
| Format | Strategy |
|--------|----------|
| Markdown | Split at `##` headings; each section = one entry |
| Plain text | Split at paragraph boundaries; merge short paragraphs |
| JSON | Expects `{"entries": [...]}` — imported as-is |

**Response (201):**
```json
{
  "filename": "architecture.md",
  "format": "markdown",
  "chunks": 12,
  "entries_created": 12,
  "entries": [
    {"id": 1, "content": "# Architecture\n\n...", "tags": ["architecture.md"], ...}
  ]
}
```
The source filename is automatically added as a tag to every created entry.

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 400 | `VALIDATION` | No file provided |
| 404 | `NOT_FOUND` | Session not found |
| 413 | `TOO_LARGE` | File exceeds 4MB limit |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Binary content or unsupported extension |

---

## Search & Tags

### `GET /api/v1/sessions/<name>/search`

Full-text search across entries using SQLite FTS5.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | string | `""` | Search query (required) |
| `limit` | int | `100` | Max results (capped at `THREAD_MAX_SEARCH_RESULTS`) |
| `cache` | bool | `true` | Set to `false` to bypass the 5s TTL search cache |

**FTS5 Query Syntax:**
| Pattern | Example | Meaning |
|---------|---------|---------|
| Plain terms | `python api` | AND match (both terms must appear) |
| Prefix | `pyth*` | Prefix match (via `prefix='2 3 4'` tokenizer) |
| Phrase | `"context server"` | Exact phrase match |
| Negation | `python -java` | Must have `python`, must NOT have `java` |

**Response (200):**
```json
{
  "results": [
    {
      "id": 42,
      "content": "Python is a programming language...",
      "rank": -1.523,
      "snippet": "...Python is a <mark>programming</mark> language...",
      "tags": ["python", "language"],
      "priority": 8,
      "created_at": "2025-01-15T10:30:00"
    }
  ],
  "query": "python",
  "count": 3,
  "session": "my-session",
  "cached": false
}
```

| Field | Description |
|-------|-------------|
| `rank` | BM25 relevance score (lower = more relevant, negative values) |
| `snippet` | Context window around the match with `<mark>` highlights |
| `cached` | `true` if result came from the 5s TTL cache |

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 400 | `VALIDATION` | `q` is empty |
| 404 | `NOT_FOUND` | Session not found |

### `GET /api/v1/sessions/<name>/tags`

List all unique tags across all entries in a session.

**Response (200):**
```json
{
  "tags": ["api", "architecture", "python", "reference", "testing"],
  "count": 5,
  "session": "my-session"
}
```

Cached for 30 seconds (TTL). Cache is invalidated on any entry mutation.

**Errors:**
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `NOT_FOUND` | Session not found |

---

## Standard Error Codes

| Code | HTTP Status | Meaning |
|------|-------------|---------|
| `NOT_FOUND` | 404 | Resource (session or entry) does not exist |
| `VALIDATION` | 400 | Request body failed validation |
| `CONFLICT` | 409 | Duplicate resource (e.g., session name) |
| `TOO_LARGE` | 413 | File upload exceeds max size |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Binary file or unsupported format |
| `INTERNAL` | 500 | Unexpected server error |

## Response Headers

All responses include:
- `X-Request-Id: req_<uuid4>` — unique request ID for log correlation
- `X-Duration-Ms: <float>` — request processing time in milliseconds

## curl Examples

```bash
# Health check
curl http://localhost:5000/api/v1/health

# Create a session
curl -X POST http://localhost:5000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"name":"demo","description":"Demo session"}'

# Create an entry
curl -X POST http://localhost:5000/api/v1/sessions/demo/entries \
  -H "Content-Type: application/json" \
  -d '{"content":"Python is a programming language","priority":8,"tags":["python","language"]}'

# List entries (cursor pagination)
curl "http://localhost:5000/api/v1/sessions/demo/entries?limit=50"

# Get next page
curl "http://localhost:5000/api/v1/sessions/demo/entries?limit=50&after=51"

# Batch read entries
curl -X POST http://localhost:5000/api/v1/sessions/demo/entries/batch \
  -H "Content-Type: application/json" \
  -d '{"ids":[1,5,12]}'

# Bulk create entries
curl -X POST http://localhost:5000/api/v1/sessions/demo/entries/bulk \
  -H "Content-Type: application/json" \
  -d '{"entries":[{"content":"One","priority":8},{"content":"Two"}]}'

# Upload a file
curl -X POST http://localhost:5000/api/v1/sessions/demo/entries/upload \
  -F "file=@architecture.md" \
  -F "tags=reference,architecture" \
  -F "priority=8"

# Search
curl "http://localhost:5000/api/v1/sessions/demo/search?q=python&limit=20"

# Search (bypass cache)
curl "http://localhost:5000/api/v1/sessions/demo/search?q=python&cache=false"

# List tags
curl "http://localhost:5000/api/v1/sessions/demo/tags"

# Stats
curl http://localhost:5000/api/v1/stats

# Update entry
curl -X PUT http://localhost:5000/api/v1/sessions/demo/entries/1 \
  -H "Content-Type: application/json" \
  -d '{"content":"Updated content","priority":9}'

# Delete entry
curl -X DELETE http://localhost:5000/api/v1/sessions/demo/entries/1

# Delete session
curl -X DELETE http://localhost:5000/api/v1/sessions/demo
```
