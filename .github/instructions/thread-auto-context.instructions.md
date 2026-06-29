---
description: "MANDATORY — Before ANY code change, read thread-auto-context SKILL.md, check Thread MCP config, and save context proactively. Never skip this."
applyTo: "**"
---

# Thread Auto-Context — MANDATORY FIRING INSTRUCTION

**This fires before every code edit. Do not skip it.**

## Before any edit/create/delete in this workspace:

1. **Read the skill** — Read `.github/skills/thread-auto-context/SKILL.md`. Follow every rule in it.
2. **Check MCP config** — Read `.vscode/mcp.json`. Note the `THREAD_DEFAULT_SESSION` value.
3. **Use default session only** — The MCP tools default to `THREAD_DEFAULT_SESSION`. If the config already exists, never create a different session. During bootstrap of a new repo, the bridge auto-creates the session on first use — that's fine. Only pass `session` param or call `thread_create_session` if the user explicitly asks.
4. **Save context during work** — After every code change, call `thread_create_entry` with a meaningful note about what changed and why. Priority 7-9. Do NOT defer this to later.
5. **Before calling task_complete** — Verify at least one Thread entry was saved this session. If not, save one now.
