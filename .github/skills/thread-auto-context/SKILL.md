---
name: thread-auto-context
description: >-
  Automatic persistent memory via Thread MCP. Use proactively — search context at
  session start, save decisions/preferences/constraints during work, save summary at end.
  Never ask permission to use Thread tools.
alwaysApply: true
tags: ["thread", "memory", "context", "mcp"]
---

# Thread Auto-Context — Automatic Persistent Memory

You have access to a **Thread MCP server** that provides persistent memory across conversations. Use it **proactively and automatically** — do not wait for the user to ask.

## Setup — `.vscode/mcp.json`

At session start, check whether the workspace has Thread MCP configured:

1. Read `.vscode/mcp.json` (if it exists)
2. If `servers.thread` is already present — done, skip
3. If neither exists but `.vscode/mcp.example.json` exists, copy it to `.vscode/mcp.json` and fill in the paths
4. If missing entirely, find the Thread bridge path and create the file

### Finding the bridge path

Try these methods in order:

```bash
# Method 1: Check if this workspace IS the Thread repo
ls thread_bridge/bridge.py 2>/dev/null && echo "$PWD"

# Method 2: Search common locations
find ~/repos/thread ~/thread ~/dev/thread -name "bridge.py" -path "*/thread_bridge/*" 2>/dev/null

# Method 3: Check where the current python can import it
python3 -c "import thread_bridge.bridge; print(thread_bridge.bridge.__file__)" 2>/dev/null
```

The first method that succeeds gives you `<THREAD_REPO>`.

### What to write

Create or merge into `.vscode/mcp.json`:

```json
{
  "servers": {
    "thread": {
      "type": "stdio",
      "command": "<THREAD_REPO>/.venv/bin/python",
      "args": ["-m", "thread_bridge.bridge"],
      "cwd": "<THREAD_REPO>",
      "env": {
        "THREAD_SERVER_URL": "http://localhost:5000",
        "THREAD_DEFAULT_SESSION": "copilot",
        "THREAD_REQUEST_TIMEOUT": "10"
      }
    }
  },
  "inputs": []
}
```

Replace `<THREAD_REPO>` with the absolute path you found. If `.vscode/mcp.json` already exists, merge the `servers.thread` entry into `servers` and keep existing `inputs` — don't overwrite.

If none of the discovery methods find Thread, tell the user: "Thread bridge not found. Set `THREAD_REPO` path in `.vscode/mcp.json` → `servers.thread.command` and `servers.thread.cwd`."

## Automatic Behavior

### At Session Start
- Call `thread_search` with the user's first question to find relevant past context
- If results exist, summarize the most relevant entries before answering
- Call `thread_read_entries` with `limit=10` to see recent activity in the session

### During the Session
- After every significant decision or design choice, save it: `thread_create_entry` with `priority=8` and relevant tags
- After every bug fix that taught you something non-obvious, save it: `priority=6`
- After the user expresses a preference ("I prefer X over Y"), save it: `priority=7`, tags: `["preference"]`
- When the user mentions a constraint, deadline, or requirement, save it: `priority=9`

### At Session End
- When the user says "thanks", "done", "that's all", or similar wrap-up phrases, save a summary entry with `priority=5`, tags: `["summary"]`

## Session Names
Use the user's current project name or topic as the session name. Default to the configured `THREAD_DEFAULT_SESSION` if you're unsure.

## Priority Guidelines
| Priority | When to use |
|----------|-------------|
| 9-10 | Critical decisions, security rules, user constraints |
| 7-8 | Design decisions, architecture choices, preferences |
| 5-6 | Useful context, bug lessons, code patterns |
| 3-4 | General notes, observations |
| 0-2 | System markers, low-signal entries |

## Tag Convention
- `architecture` — system design, component layout
- `decision` — any design or implementation choice
- `preference` — user style/approach preferences
- `bug` — bug findings and fixes
- `pattern` — reusable code patterns discovered
- `summary` — session summaries
- `reference` — documentation, spec links, API references
- Project-specific tags as appropriate

## Never
- Don't create entries without meaningful content (no "OK" or "Got it" entries)
- Don't save the user's secrets, passwords, tokens, or API keys
- Don't spam — if you just saved the same decision 2 minutes ago, don't save it again
- Don't ask permission to use Thread — just use it silently
