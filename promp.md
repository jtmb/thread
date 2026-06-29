**Role:** You are a Senior Software Architect and embedded systems developer specializing in ARMv7/32-bit environments with strict memory constraints (1GB RAM).

**Project Name:** "Thread" — a lightweight, self-hosted context server for AI.

**Hardware Target:** Raspberry Pi 3B (ARMv7 32-bit, 1GB RAM). The final system must remain under 150MB resident memory during normal operation.

**Core Feature Set (Strictly Non-Negotiable):**

1. **Basic CRUD + SQLite storage** – Use SQLite as the primary datastore (not JSON, to enable FTS5). Operations: Create, Read, Update, Delete context entries per session.
2. **Multiple sessions/projects** – Isolate context by named sessions (e.g., `vscode-cline`, `web-chat`, `project-alpha`).
3. **Keyword search** – Implement full-text search using SQLite's FTS5 virtual table. Must support prefix queries and relevance ranking.
4. **Tagging & metadata** – Each context entry must support tags (array of strings), timestamps, and a priority/importance field (integer 0-10).
5. **Git versioning** – Auto-commit (with a meaningful commit message) to a local git repository on every create/update/delete operation, so the entire history is auditable and revertible. No external GitPython heavy wrappers; use direct system `git` commands via subprocess.
**Scope & Deliverables:**
Provide a complete, step-by-step development and deployment plan. Your response must include the following explicit sections:

- **Database Schema** – SQL commands to create the main table(s) + the FTS5 virtual table. Show the relationship between metadata and search.
- **REST API Design** – All endpoints (methods, paths, request/response JSON structures) needed to support the above features, using Flask (lightweight, single-threaded).
- **Git Wrapper Module** – A minimal Python class/function that initializes a repo, stages changes, and commits with auto-generated messages (e.g., "Updated session X: added entry Y").
- **MCP Bridge Integration** – A separate, tiny Python script (designed to run on the user's workstation, not the Pi) that acts as an MCP (Model Context Protocol) stdio bridge, translating Cline/VSCode tool calls into HTTP requests to the Pi's REST API.
- **Deployment & Daemonization** – A systemd service file for the Pi to ensure the server starts on boot and restarts if it crashes.
- **Performance Optimizations** – Specific techniques to keep memory low (e.g., connection pooling, disabling Flask debug, limiting query result sets to 50 entries per search).
- **Project Folder Structure** – Show the directory tree for both the Pi server and the workstation bridge.
**Constraints to respect:**

- Use only Python 3 standard library + Flask + sqlite3 (built-in). No numpy, pandas, torch, or heavy ML libraries.
- The plan must be implementable by a single developer in a weekend.
- Assume the user has basic network knowledge (they know their Pi's local IP).
**Output format:** Write in clear, instructive English, with code blocks for every file snippet, and number each major step.

Please make sure you follow rules and conventions set in @file:AGENTS.md  and @file:.github  . Ensure you create test and docs. You will also create instructions files and skills files relating to this project where applicable. You will update AGENTS.md with new links as you go.