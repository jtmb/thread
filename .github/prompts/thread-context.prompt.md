---
description: "Bootstrap context from Thread — pull recent session history, search for relevant past context, and load repo conventions. Use in Copilot Chat when starting a new conversation. (Cline gets equivalent behavior automatically via SKILL.md.)"
argument-hint: "What are you working on? (optional — describe your current task to search for related past context)"
---

# Thread Context Bootstrap

You are starting a fresh session. Before writing any code, load context from Thread to understand what's been happening in this project.


## Step 1: Determine Session Name

Run `basename "$PWD"` to get the workspace folder name. Use this as the `session` parameter for all Thread calls.

## Step 2: Pull Recent Context

Call these Thread tools (in parallel if possible):

```
thread_read_entries  → session: "<workspace>", sort: "desc", limit: 20
thread_get_tags      → session: "<workspace>"
```

The `thread_read_entries` call returns the 20 most recent entries. Look for:
- **Summary entries** (tagged `["summary"]`) — these are end-of-session wrap-ups that cover everything accomplished
- **Decision entries** (tagged `["decision"]`) — design choices, architecture decisions
- **Bug entries** (tagged `["bug"]`) — non-obvious fixes and lessons learned
- **Preference entries** (tagged `["preference"]`) — user-stated preferences and constraints

## Step 3: Search for Task-Relevant Context

If the user described what they're working on, search Thread for related past context:

```
thread_search → session: "<workspace>", query: "<user's task description>"
```

Also search for recent Copilot transcripts to find past conversations on this topic:

```
thread_search → session: "<workspace>", query: "copilot AND transcript"
```

## Step 4: Load Repo Conventions

Read these files to understand the project:

| File | What it tells you |
|------|-------------------|
| `AGENTS.md` | Core rules: comments, docs sync, tests, naming, error handling, config |
| `docs/TECH-STACK.md` | Python 3.12 + Flask + Waitress + sqlite3 FTS5. Build/test commands. |
| `docs/ENVIRONMENT-VARIABLES.md` | All 22 env vars with defaults, valid values, and descriptions |
| `.github/instructions/python.instructions.md` | Flask app factory, sqlite3 patterns, structured logging |

## Step 5: Summarize and Confirm

After pulling all context, present a concise briefing:

```markdown
## Context Loaded — [workspace name]

### Recent Activity
- [Summarize the last 1-2 summary entries]
- [Highlight any open decisions or unresolved issues]

### Relevant Past Context
- [What was found from the task search, if anything]

### Project Snapshot
- **Stack**: Python 3.12 / Flask / Waitress / SQLite FTS5
- **Tests**: 145 passing (Vitest/pytest)
- **Key convention**: [most important rule from AGENTS.md for this task]

Ready to work. What should I do first?
```

## Notes

- If no Thread entries exist yet (fresh project), say so and proceed with just the repo conventions
- If the server is down, load repo conventions only and tell the user how to start it
- If the user specified a task, prioritize search results over generic recent entries
- Keep the briefing under 20 lines — the goal is fast bootstrap, not exhaustive history
