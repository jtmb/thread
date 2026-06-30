# Thread Documentation

> AI Context Server for Raspberry Pi 3B — performance-optimized, multi-threaded, speed-first.

## Index

| Document | Purpose |
|----------|---------|
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | System design, component relationships, threading model, caching architecture, request lifecycle — with Mermaid diagrams |
| [`TECH-STACK.md`](./TECH-STACK.md) | Dependencies, versions, and rationale for every technology choice |
| [`FRONTEND.md`](./FRONTEND.md) | SPA architecture — hash router, view lifecycle, Chart.js dashboard, CSS conventions, API client, browser support |
| [`API-USAGE.md`](./API-USAGE.md) | Complete REST API reference — every endpoint, request/response shapes, error codes, curl examples |
| [`CONVENTIONS.md`](./CONVENTIONS.md) | Coding conventions: Python patterns, docstrings, type hints, git commits, naming |
| [`DEPLOYMENT.md`](./DEPLOYMENT.md) | Raspberry Pi setup, systemd service management, firewall, troubleshooting |
| [`MCP-VSCODE-COPILOT.md`](./MCP-VSCODE-COPILOT.md) | Add Thread as an MCP server in VS Code Copilot — settings, verification, usage tips |
| [`MCP-CLINE.md`](./MCP-CLINE.md) | Add Thread as an MCP server in Cline — config, auto-approve tools, usage patterns |

## Quick Links

- **Specification**: [`promp.md`](../promp.md) at repo root
- **Project conventions**: [`AGENTS.md`](../AGENTS.md) at repo root
- **Source code**: `thread_server/` (Pi server), `thread_frontend/` (SPA + static assets), `thread_bridge/` (workstation MCP bridge)
- **Tests**: `tests/`
