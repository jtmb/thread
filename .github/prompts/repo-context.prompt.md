---
description: "Provide project context to the AI: identity, tech stack, docs map, and conventions overview. Use when starting a new coding session or refreshing context. For Thread-powered context with chat history, use /thread-context instead."
argument-hint: "Describe the project or ask about conventions"
---

# Project Context

You are working in this project. Before writing code, read the relevant docs to understand the codebase.

> **💡 For a full bootstrap with chat history**: use `/thread-context` — it pulls recent session summaries, searches past conversations, and loads all conventions in one shot.

## How to Use This Context

1. Read `AGENTS.md` for core rules (mandatory pre-read)
2. Read `docs/README.md` for the full docs map
3. Read the docs relevant to your current task
4. Follow framework conventions in `.github/instructions/`
5. After making changes, update the relevant docs

## Project Identity

- **Name**: Thread — persistent context memory for AI coding agents
- **Primary language**: Python 3.12+
- **Primary framework**: Flask 3.x + Waitress 3.x (production WSGI)
- **Database**: sqlite3 with FTS5 full-text search, WAL mode
- **Description**: A lightweight MCP server that gives Copilot and Cline persistent memory across conversations. Entries (text chunks) are stored in sessions with tags, priorities, FTS5 search, cursor pagination, file upload with auto-chunking, and per-session Git versioning.

## Key Docs

| Doc | Content |
|-----|---------|
| `AGENTS.md` | **Mandatory pre-read** — comments, docs sync, testing, naming, config, error handling |
| `docs/ARCHITECTURE.md` | System topology (Workstation → Bridge → Pi → Flask → SQLite), data flow, Mermaid diagrams |
| `docs/TECH-STACK.md` | Python 3.12 / Flask 3.x / Waitress 3.x / sqlite3 FTS5. Build/test/lint commands. |
| `docs/ENVIRONMENT-VARIABLES.md` | All 22 env vars (18 server + 4 bridge) with defaults, valid values, descriptions |
| `docs/CONVENTIONS.md` | Naming, file organization, error handling, git practices |
| `docs/DEPLOYMENT.md` | Docker, systemd, Pi bare-metal deployment |
| `docs/MCP-VSCODE-COPILOT.md` | VS Code MCP setup for Copilot Chat |
| `docs/MCP-CLINE.md` | Cline MCP setup |
| `.github/skills/thread-auto-context/SKILL.md` | Auto-bootstrap + automatic Thread usage rules |

## Framework Instructions

| File | Applies to | Content |
|------|-----------|---------|
| `.github/instructions/python.instructions.md` | `**/*.py` | Flask app factory, sqlite3 FTS5, Waitress, structured logging |
| `.github/instructions/api-design.instructions.md` | `**/{routes,handlers,api}/**/*.py` | Status codes, error shapes, pagination |
| `.github/instructions/configuration-docs.instructions.md` | `**/config/**/*` | Mandates `docs/ENVIRONMENT-VARIABLES.md` updates |
| `.github/instructions/test.instructions.md` | `**` | Tests for every feature, pytest patterns |

## Build & Test

```bash
# Run all tests (145 tests, Python/pytest)
.venv/bin/python -m pytest tests/ -v

# Run with coverage
.venv/bin/python -m pytest tests/ --cov=thread_server --cov-report=term

# Lint
ruff check thread_server/ thread_bridge/ tests/

# Start server (dev)
.venv/bin/python -m thread_server.server

# Health check
curl http://localhost:5000/api/v1/health
```

## Working in This Repo

When making changes:
1. Read `AGENTS.md` — it's the source of truth for all conventions
2. Check `.github/instructions/` for framework-specific rules
3. Every new env var goes in `docs/ENVIRONMENT-VARIABLES.md` (per `.github/instructions/configuration-docs.instructions.md`)
4. Update docs in the same turn as code changes
5. Run tests before declaring done (145 tests, all must pass)
6. Use Thread MCP tools to save decisions, preferences, and session summaries
