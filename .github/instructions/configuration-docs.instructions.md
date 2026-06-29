---
description: "Every config change MUST update docs/ENVIRONMENT-VARIABLES.md. No new env var goes undocumented."
applyTo: "**/{config,configs,settings,env}/**/*.{py,ts,js,go,rs,yaml,yml,toml,json,env}"
---

# Configuration Documentation — Mandatory

Every configuration value managed by this project must be documented in `docs/ENVIRONMENT-VARIABLES.md` at the repo root.

## When to Update

Update `docs/ENVIRONMENT-VARIABLES.md` whenever you:

- **Add a new environment variable** — add a row to the appropriate table with variable name, default, valid values, and description
- **Change a default value** — update the default in the table
- **Add or change validation rules** — update the Valid column
- **Remove an environment variable** — remove its row from the table
- **Add a new config module** — add the module's env vars to the "Full Reference" table at the bottom

## Checklist

Before committing a config change, verify:

- [ ] `docs/ENVIRONMENT-VARIABLES.md` is up to date (every env var appears)
- [ ] The quick-reference table at the bottom includes the new variable
- [ ] `.env.example` is updated with the new variable (commented out with its default)
- [ ] `docker-compose.yml` exposes the variable if it's relevant to containerized deployment
- [ ] Validation is added to `validate()` in the config module (fail fast on invalid values)
- [ ] Sensible defaults mean a new developer can run with zero configuration

## Format

Each variable row must include:

| Variable | Default | Valid | Description |
|----------|---------|-------|-------------|

Every section should have a brief description of what that category of config controls.

## Cross-Reference

- **Server config**: `thread_server/config.py` → documented under "Server Configuration" section
- **Bridge config**: `thread_bridge/config.py` → documented under "Bridge Configuration" section
- **Docker Compose**: `docker-compose.yml` → env vars should match what's documented
- **Local dev**: `.env.example` → commented-out defaults matching the documentation

> **This is not optional.** If a new env var is added without documentation, the PR is incomplete.
