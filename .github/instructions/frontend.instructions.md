---
description: "Best practices for the Thread frontend — vanilla JS SPA with Pico.css + Chart.js + vis-network, served by Flask on a Raspberry Pi."
applyTo: "thread_frontend/**/*.{html,js,css}"
---

# Frontend Conventions — Thread Dashboard

The Thread frontend is a Single-Page Application served by Flask/Waitress running on a Raspberry Pi 3B. Zero npm, zero Node.js, zero build pipeline. All JS is vanilla (ES modules). All CSS extends Pico.css v2. All assets are vendored locally.

## SPA Architecture

- **Single HTML file**: `templates/index.html` — the entire shell. Flask serves this for every `/dashboard/*` path.
- **Hash router**: Hand-rolled in `static/js/router.js`. Reads `window.location.hash`, matches routes, mounts views into `#app-root`.
- **Views**: Each view is a class extending `BaseView` (`static/js/views/base.js`). Override `onMount()`, `onUnmount()`, `render()`.
- **No framework**: No React, Vue, Svelte, or jQuery. Raw DOM manipulation via `this.root.innerHTML = html` + event delegation.

## View Lifecycle

1. Router calls `new ViewClass({ params, query })`
2. Router calls `view.onMount()` — view fetches data, calls `this.render(data)`, binds event listeners
3. On navigation away: router calls `view.onUnmount()` — remove listeners, close SSE, destroy Chart.js/vis-network instances
4. View's `render(data)` method returns an HTML string, which is set as `#app-root.innerHTML`

## API Client

- **Zero-arg import**: `import { ThreadAPI } from "/dashboard/static/js/api.js"` — creates `api.js` (no class instantiation).
- **Auth token**: Automatically read from `localStorage` and attached as `Authorization: Bearer`.
- **401 handling**: Auto-clears token and redirects to `#login`.
- **SSE**: `api.connectSSE()` returns `new EventSource()` with `?token=` query param for auth.

## Auth

- Tokens stored in `localStorage` key `thread_auth_token`.
- `Auth.isAuthenticated()`, `Auth.getToken()`, `Auth.setToken(t)`, `Auth.clearToken()`.
- Auth disabled by default (`THREAD_AUTH_ENABLED=false`) — server ignores Bearer header.

## Vendored Assets Rule

All CSS/JS libraries **must** be downloaded and placed in `static/vendor/` — zero CDN references. This works on air-gapped Pi deployments.

| Asset | Version | File | Path |
|-------|---------|------|------|
| Pico.css | 2.0.6 | `pico.min.css` | `static/vendor/pico.min.css` |
| Chart.js | 4.4.7 | `chart.min.js` | `static/vendor/chart.min.js` |
| vis-network | 9.1.6 | `vis-network.min.js` | `static/vendor/vis-network.min.js` |

Download commands:
```bash
curl -sSLo thread_frontend/static/vendor/pico.min.css \
  https://cdn.jsdelivr.net/npm/@picocss/pico@2.0.6/css/pico.min.css

curl -sSLo thread_frontend/static/vendor/chart.min.js \
  https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js

curl -sSLo thread_frontend/static/vendor/vis-network.min.js \
  https://cdn.jsdelivr.net/npm/vis-network@9.1.6/dist/vis-network.min.js
```

## CSS Guidelines

- **Extend Pico.css, never override unless necessary.** Pico's classless variant handles typography, forms, tables, dark mode.
- **Custom styles in `app.css`**: entry cards, priority badges, tag chips, nav layout, git timeline, graph container, loading/error/empty states, responsive breakpoints.
- **Print styles in `print.css`**: `@media print` hides nav/buttons, full-width content, monospace font.
- **Dark mode**: Set via `<html data-theme="dark">`. Pico handles the rest.

## JS Guidelines

- **ES modules**: `export` / `import`. No bundler needed — browser native.
- **One concern per file**: `router.js`, `api.js`, `auth.js`, `utils.js`, `views/*.js`.
- **No jQuery**: Use `document.querySelector`, `addEventListener`, `fetch`, `EventSource`.
- **Memory conscious**: Destroy Chart.js / vis-network instances in `onUnmount()`. Close SSE connections. Pi has 1GB RAM.
- **Error handling**: Every `fetch()` call must have `.catch()`. Views show errors via `this.showError(msg)` from `BaseView`.

## Naming

| Thing | Convention |
|-------|-----------|
| Files | kebab-case: `router.js`, `app.css`, `print.css` |
| Classes | PascalCase: `DashboardView`, `ThreadAPI` |
| Functions/vars | camelCase: `formatBytes()`, `renderEntryCard()` |
| DOM IDs | kebab-case: `app-root`, `modal-root`, `search-input` |
| CSS classes | kebab-case: `entry-card`, `priority-high` |

## Testing

Frontend JS is tested **indirectly** via Flask route integration tests (supertest). No Vitest/jsdom — the repo has zero npm infrastructure. Manual smoke test checklist in `docs/FRONTEND.md`.

## Pi Constraints

- **ARMv7 32-bit, 1GB RAM**. Frontend RSS target: <20MB (static files are disk-served by Flask).
- **No build pipeline**: Browser-native ES modules, no TypeScript, no SCSS, no minification.
- **Offline-first**: All assets vendored locally. Dashboard works on air-gapped networks.
- **Dark mode by default**: Pi runs headless. Dashboard is viewed from other machines.
