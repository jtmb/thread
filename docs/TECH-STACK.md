# Thread — Tech Stack

## Runtime

| Component | Version | Purpose | Why |
|-----------|---------|---------|-----|
| **Python** | 3.11+ (Bookworm default) | Language runtime | Available on Pi OS, fast enough for I/O-bound workload, zero build dependencies |
| **Flask** | 3.x | Web framework | Lightweight, app factory pattern, no ORM opinion, mature ecosystem |
| **Waitress** | 3.x | Production WSGI server | Pure Python (no C extensions), single-process multi-threaded, no master/worker fork overhead — saves 20-25MB per worker vs Gunicorn |
| **sqlite3** | stdlib (3.40+) | Database | Built-in, no install needed, FTS5 + JSON1 extensions included in Pi OS Bookworm's Python. `cache_size=-100000` (100MB page cache), `mmap_size=268435456` (256MB memory-mapped I/O), `synchronous=NORMAL`, `temp_store=MEMORY`, `journal_mode=WAL` |
| **subprocess** | stdlib | Git operations | Runs `git` binary, no persistent memory overhead (~50-100ms per operation) |

## Libraries (pip)

### Server (`thread_server/requirements.txt`)
```
flask>=3.0,<4.0
waitress>=3.0,<4.0
```
Total installed size: ~3MB. Flask for routing/middleware, Waitress for production threading.

### Bridge (`thread_bridge/requirements.txt`)
```
requests>=2.31,<3.0
```
Total installed size: ~500KB. `requests.Session()` for HTTP keep-alive connection reuse.

## Caching (stdlib, no pip)

| Cache | Implementation | Purpose |
|-------|---------------|---------|
| **Session LRU** | `functools.lru_cache(maxsize=512)` | Session name→id is the hottest path — 95%+ hit rate. No TTL needed (sessions change rarely) |
| **SearchCache** | Custom class (`dict` + `threading.Lock` + per-entry expiry) | FTS5 results cached 5s — agents re-search same terms within seconds. Max 128 entries |
| **TagCache** | Custom class (`dict` + expiry) | Tag lists cached 30s — tags change only on entry mutations |

## Dev Tools

| Tool | Purpose |
|------|---------|
| **pytest** 9.1.1 | Test runner (test discovery, fixtures, parametrize). 124 tests across 10 files |
| **pytest-cov** 7.1.0 | Code coverage (v8 provider). Report: 71% overall |
| **ruff** | Linter + formatter (replaces black + isort + flake8, single binary, fast) |

### Test Coverage by Module (target: >80% for core)

| Module | Coverage | Notes |
|--------|----------|-------|
| `models.py` | **94%** | CRUD + search + batch — core data layer |
| `app.py` | **94%** | Flask factory + middleware — integration tested |
| `routes/health.py` | **96%** | Health + debug endpoints |
| `routes/sessions.py` | **92%** | Session CRUD routes |
| `routes/entries.py` | **79%** | Entry CRUD + bulk + upload + cursor pagination |
| `routes/search.py` | **89%** | FTS5 search + tags with caching |
| `routes/stats.py` | **87%** | Performance metrics endpoint |
| `routes/errors.py` | **100%** | Error handler registration |
| `database.py` | **85%** | Connection pool + pragmas |
| `config.py` | **88%** | Environment config loading |
| `logging_config.py` | **89%** | Structured JSON logging |
| `cache.py` | **79%** | 3-tier caching layer |
| `chunker.py` | **68%** | Document chunking (complex edge cases) |
| `git_manager.py` | **76%** | Subprocess git wrapper |
| `cli/import.py` | **11%** | CLI import tool (tested indirectly via HTTP) |
| `server.py` | **0%** | Entry point (tested via app) |

## What We Don't Use (and Why)

| Not Using | Replaced By | Reason |
|-----------|-------------|--------|
| SQLAlchemy ORM | Direct `sqlite3` | ORM adds 10-15MB RSS + 2-5ms per query for object mapping overhead |
| Gunicorn | Waitress | Master+worker fork adds 20-25MB per worker; single-process threads save memory |
| aiosqlite / asyncpg | Synchronous `sqlite3` | SQLite is synchronous at C level — async wrappers add complexity without throughput gain |
| Alembic | Static schema + `IF NOT EXISTS` | Schema is simple and static; no migration framework overhead needed |
| Docker | systemd (bare metal) | No container overhead (~50-100MB) on a 1GB Pi; native systemd is more memory-efficient |
| GitPython | `subprocess.run(['git', ...])` | No persistent in-process memory; process spawns/exits per git operation |
| Redis / memcached | In-process Python caches | External cache adds network latency + process; in-process is faster for single-server |
| Poetry / Pipenv | `pip` + `requirements.txt` | Fewer dependencies on Pi; pip is already installed |

## Memory Budget

| Component | RSS at Idle | RSS Under Load |
|-----------|-----------|----------------|
| Python + Flask + Waitress | ~25 MB | ~25 MB |
| 12 SQLite connections (page cache) | ~60-80 MB | ~120-150 MB |
| 256MB mmap (OS cache, not RSS) | ~0 MB (OS) | ~0 MB (OS) |
| Caches (Search + Tags + LRU) | ~3-5 MB | ~5-10 MB |
| Git subprocess (transient) | ~0 MB | ~10 MB per process |
| **Total** | **~90-110 MB** | **~160-195 MB** |

systemd `MemoryMax=800M`, `MemoryHigh=600M` — ample headroom for speed-first configuration.
