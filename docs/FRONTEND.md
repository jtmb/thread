# Thread — Frontend Architecture

> Vanilla JS SPA served by Flask at `/dashboard/*`. Hash router, Pico.css dark theme, Chart.js analytics, zero build step.

## Overview

The Thread frontend is a **single-page application** (SPA) with no build pipeline — plain HTML, CSS, and ES modules served directly by Flask/Waitress. All client-side routing uses `window.location.hash`, so page refreshes work without server-side route matching.

```mermaid
graph TB
    subgraph Browser
        HTML[index.html<br/>Jinja2 template]
        CSS[app.css + print.css<br/>Pico.css v2 dark theme]
        JS[ES modules<br/>vanilla JS, no framework]
        CHART[Chart.js 4.4.7<br/>canvas charts]
    end
    subgraph "Flask / Waitress"
        BP[frontend_bp<br/>url_prefix=/dashboard]
        STATIC[static/ folder<br/>CSS, JS, vendor, img]
    end
    HTML --> CSS
    HTML --> JS
    JS --> CHART
    BP --> HTML
    BP --> STATIC
```

## Directory Structure

```
thread_frontend/
├── __init__.py            # Flask Blueprint, serves index.html for all /dashboard/* routes
├── templates/
│   └── index.html         # Shell HTML — Jinja2 renders once, SPA takes over
└── static/
    ├── vendor/
    │   └── pico.min.css   # Pico.css v2 classless dark theme (~30KB)
    ├── css/
    │   ├── app.css        # Custom styles (layout, cards, browser, charts, modals)
    │   └── print.css      # Print-specific styles (hides nav, buttons, modals)
    ├── js/
    │   ├── app.js         # Entry point — bootstraps router + auth
    │   ├── router.js      # Hash router — matches #/path to View classes
    │   ├── api.js         # ThreadAPI class — fetch wrapper for all endpoints
    │   ├── auth.js        # Auth module — JWT token management, auto-login
    │   ├── utils.js       # escapeHtml(), showToast(), relativeTime(), priorityColor()
    │   └── views/
    │       ├── index.js   # Barrel file — exports all views
    │       ├── base.js    # BaseView — lifecycle (onMount, onUnmount, render)
    │       ├── login.js   # LoginView — API key → JWT form
    │       ├── dashboard.js  # DashboardView — stats, charts, sessions table
    │       └── sessions/
    │           ├── browser.js  # BrowserView — paginated entry list + CRUD
    │           ├── history.js  # HistoryView — git log + diff + revert
    │           └── graph.js    # GraphView — entry cross-reference table
    └── img/
        └── logo.svg       # Thread logo (optional)
```

## SPA Lifecycle

```mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant F as Flask
    participant R as Router
    participant V as View
    participant A as API

    U->>B: Navigate to /dashboard/
    B->>F: GET /dashboard/
    F-->>B: index.html (Jinja2 rendered)
    B->>R: DOMContentLoaded → init()
    R->>R: matchRoute(hash)
    R->>V: new DashboardView({ params, query })
    R->>V: view.onMount()
    V->>A: api.getStats() / api.getSessions()
    A-->>V: JSON responses
    V->>V: render(data) → mountHTML(html)
    V-->>B: DOM updated

    U->>B: Click session link (#/sessions/thread)
    B->>R: hashchange → render()
    R->>R: matchRoute("sessions/thread") → BrowserView
    R->>V: prev.onUnmount() → new BrowserView.onMount()
    V->>A: api.listEntries("thread", 50)
    A-->>V: { data: [...], pagination: { cursor, hasMore } }
    V->>V: _render() → mountHTML(html)
```

## Hash Router (`router.js`)

Simple pattern-matching router — no dependencies, ~70 lines.

### Route Table

| Hash Pattern | View Class | Auth | Description |
|-------------|-----------|------|-------------|
| `""` (empty) | `DashboardView` | No | Stats, charts, sessions table |
| `sessions/:name` | `BrowserView` | Yes | Paginated entry browser |
| `sessions/:name/history` | `HistoryView` | Yes | Git commit log + diffs |
| `sessions/:name/graph` | `GraphView` | Yes | Entry cross-references |
| `search` | `SearchView` | Yes | FTS5 search + tag filter |
| `upload` | `UploadView` | Yes | File upload + chunk progress |
| `settings` | `SettingsView` | Yes | Server config / info |
| `login` | `LoginView` | No | API key → JWT form |

### Route Matching

```mermaid
flowchart LR
    HASH["#sessions/thread"] --> SPLIT["split('/') → ['sessions','thread']"]
    SPLIT --> LOOP["For each ROUTE entry"]
    LOOP --> MATCH{":prefix?"}
    MATCH -->|":name"| PARAM["params.name = segment"]
    MATCH -->|literal| EQ{"=== segment?"}
    EQ -->|yes| NEXT["Next segment"]
    EQ -->|no| SKIP["Skip route"]
    PARAM --> NEXT
    NEXT --> DONE{"All segments matched?"}
    DONE -->|yes| RETURN["Return { view, params, auth }"]
    DONE -->|no| SKIP
```

### Query String Parsing

Hash query strings (`#/search?q=hello&tags=system`) are parsed into a `query` object:
```js
// router.js → parseQuery()
// "#/search?q=hello&tags=system" → { q: "hello", tags: "system" }
```

Route params and query are passed to views as:
```js
new match.view({ params: match.params, query })
```

### Auth Guard

The router checks `Auth.isAuthenticated()` before mounting `auth: true` routes. If the server requires authentication (`isAuthRequired()`) and the user isn't authenticated, they're redirected to `#/login`. If auth is disabled server-side, the auto-login flow kicks in transparently.

## View Architecture

### BaseView (`base.js`)

All views extend `BaseView`, which provides the lifecycle contract:

```mermaid
classDiagram
    class BaseView {
        +params: object
        +query: object
        +root: HTMLElement
        +onMount() Promise
        +onUnmount()
        +onSSEEvent(event)
        +render(data) string
        +mountHTML(html)
        +showLoading(message)
        +showError(message, backUrl)
    }
    class DashboardView {
        -_sessions: Array
        -_stats: object
        -_eventSource: EventSource
        +onMount()
        +onUnmount()
        +onSSEEvent(event)
        +render(data)
        -_renderStats()
        -_renderServerInfo()
        -_renderSessionsTable()
        -_renderAllCharts()
        -_renderSessionsChart()
        -_renderUptimeChart()
        -_connectSSE()
    }
    class BrowserView {
        -_sessionName: string
        -_entries: Array
        -_cursor: number|null
        -_hasMore: boolean
        -_expandedId: string|null
        +onMount()
        -_render()
        -_renderEntryCard(entry)
        -_bindEvents()
        -_loadMore()
        -_exportEntries(format)
    }
    BaseView <|-- DashboardView
    BaseView <|-- BrowserView
```

### View Lifecycle

1. **Constructor** — stores `params` and `query` from the router
2. **`onMount()`** — fetches data, calls `render()`, binds events. Called by router after construction
3. **`render(data)`** — returns an HTML string. Most views call `mountHTML()` with the result
4. **`onUnmount()`** — cleans up listeners, EventSource, Chart.js instances. Called by router before navigating away

### DashboardView — Charts & SSE

The dashboard has two Chart.js charts, real-time SSE updates, and a sessions table.

```mermaid
flowchart TB
    DASH[DashboardView.onMount] --> STATS[api.getStats]
    DASH --> SESS[api.listSessions]
    DASH --> SSE[SSE connect]
    STATS --> RENDER[_renderStats + _renderServerInfo]
    SESS --> TABLE[_renderSessionsTable]
    STATS --> CHART1[_renderSessionsChart<br/>entries vs cache hit rate]
    STATS --> CHART2[_renderUptimeChart<br/>uptime gauge]
    SSE --> ONSSE[onSSEEvent]
    ONSSE --> UPDATE[Update stats + re-render table]
```

**Charts:**
- **Sessions chart**: Two-line graph (Chart.js `line` type) — blue line for entries per session (left Y axis), green dashed line for cache hit rate % (right Y axis 0–100%)
- **Uptime chart**: Single stat display showing server uptime

**SSE (Server-Sent Events):** Dashboard connects to `/api/v1/events` with the JWT token. Every 30 seconds the server pushes updated stats, and the dashboard re-renders the sessions table + stat cards without a full page refresh.

### BrowserView — Entry List + CRUD

Paginated entry browser with cursor-based "Load more", inline editing, and export.

> **Type coercion note:** Entry IDs from the API are integers, but DOM `dataset` attributes are always strings. `_renderEntryCard()` normalizes with `const entryId = String(entry.id ?? "")` so `dataset.entryId` comparisons (e.g., "Show more" button, expand toggle) work reliably.

```mermaid
flowchart TB
    ONMOUNT[onMount] --> FETCH[api.listEntries name, 50]
    FETCH --> RENDER[_render]
    RENDER --> CARDS[50 entry cards]
    CARDS --> BIND[_bindEvents]

    BIND --> EXPAND["Show more… button"]
    BIND --> PRIORITY["Priority select"]
    BIND --> TAGS["Edit tags button"]
    BIND --> DELETE["Delete + modal"]
    BIND --> LOADMORE["Load more… (cursor pagination)"]
    BIND --> EXPORT["Export dropdown (JSON/Markdown)"]

    EXPAND --> TOGGLE["Toggle _expandedId → _render()"]
    PRIORITY --> API_PUT["api.updateEntry priority"]
    TAGS --> PROMPT["prompt() → api.updateEntry tags"]
    DELETE --> MODAL["Modal confirm → api.deleteEntry"]
    LOADMORE --> FETCH_MORE["api.listEntries with cursor"]
    EXPORT --> DOWNLOAD["Blob → createObjectURL → click download"]
```

**Pagination:** Uses cursor-based pagination via `before` parameter (the last entry's `id`). "Load more" fetches the next 50 entries and appends them.

**Export:** Dropdown with two format options:
- **JSON** — array of entry objects (`{ id, content, priority, tags, created_at }`). Good for backup/restore.
- **Markdown** — human-readable document with headers, priority labels, tags, timestamps. Good for sharing.

### HistoryView — Git Log

Shows the git commit log for a session with paginated "Load more". Each commit shows the message, date, and a "View diff" button. Diffs open in a modal showing the full `git diff` output. Revert button restores a previous state.

### GraphView — Entry Cross-References

Scans all entries for cross-references (@mentions, #tags, URL links) and renders a link table showing which entries reference each other. Future: full vis-network force-directed graph.

### SearchView — FTS5 Search

Full-text search across sessions with FTS5 ranking, 300ms debounced input, and BM25 relevance scores.

**Search input:** Standalone `<input type="search">` (Pico pill). No attached button — no alignment issues with replaced vs non-replaced elements.

**Session filter:** `<details class="search-filter">` disclosure below the input. Summary shows `▸ Sessions: **All sessions**` (or `**N sessions**`) with a `▸`/`▾` arrow updated via the native `toggle` event. Open/close is browser-native — zero JS close-handler code, zero `z-index` or `position: absolute` hacks. Mutual exclusion preserved: picking any session deselects "All sessions", clicking "All" clears individual picks. Selection syncs to the URL hash (`?sessions=...`).

**Result cards:** Each result shows a session label badge, priority badge, tag chips, relative time, and a BM25 rank score. Content highlights wrap matching terms in `<em>` tags.

## API Client (`api.js`)

Thin wrapper around `fetch()` with JWT auth header injection:

```mermaid
flowchart LR
    CALL["api.listEntries(name, limit)"] --> REQ["request(url, opts)"]
    REQ --> HEADER["Authorization: Bearer <jwt>"]
    HEADER --> FETCH["fetch('/api/v1/...')"]
    FETCH --> OK{response.ok?}
    OK -->|yes| JSON["return res.json()"]
    OK -->|no| THROW["throw new Error(res.text())"]
```

All API methods return the full JSON response. Views are responsible for destructuring:

```js
// API response shape:
{ data: [...], pagination: { cursor: "123", hasMore: true } }

// Views destructure:
const { data, pagination } = await api.listEntries(name, 50);
```

**Auth token management** (`auth.js`):
- JWT stored in `sessionStorage`
- `Auth.isAuthenticated()` — checks token existence + expiry
- `Auth.isAuthRequired()` — checks server config, auto-logs in if auth is disabled
- Token added to all `fetch()` calls via `Authorization: Bearer` header
- On 401 response, token is cleared and user redirected to login

## CSS Architecture

### Theme: Pico.css v2 Classless Dark

Pico.css provides the dark theme foundation. The classless variant means semantic HTML (`<article>`, `<nav>`, `<table>`, `<button>`) gets styled automatically — no utility classes needed.

```
app.css layers:
 ├─ Layout (container max-width, #app-root min-height)
 ├─ Entry Cards (border-left accent, priority badges, tag chips)
 ├─ Dashboard Stats (metric cards grid, stat values)
 ├─ Browser (toolbar, export dropdown, entry actions, content collapse)
 ├─ Search (input + details disclosure filter, results)
 ├─ Upload (drop zone, progress bar, chunk info)
 ├─ Settings (config table)
 ├─ Toast (animated notifications — success/error/info)
 ├─ Modal (overlay + card, confirm/cancel actions)
 ├─ Charts (canvas containers, responsive sizing)
 └─ Print (print.css — hides nav, buttons, modals)
```

### Entry Card Styling

```mermaid
graph LR
    subgraph "Entry Card Layout"
        ACCENT["border-left: 3px var(--pico-primary)"]
        BG["background: #1e2430"]
        BORDER["border: 1px rgba(255,255,255,0.08)"]
        META["entry-meta flex row"]
        CONTENT["browser-content pre"]
        EXPAND["browser-expand-btn"]
    end
    ACCENT --> CARD["article.entry-card.browser-entry"]
    BG --> CARD
    BORDER --> CARD
    CARD --> META
    CARD --> CONTENT
    CARD --> EXPAND
    META --> PRIO["priority-badge (colored by level)"]
    META --> TAGS["tag-chip pills"]
    META --> TIME["entry-time (relative)"]
    META --> ACTIONS["browser-entry-actions"]
    ACTIONS --> SEL["priority select"]
    ACTIONS --> EDIT["edit tags btn"]
    ACTIONS --> DEL["delete btn"]
```

**Key CSS variables from Pico:**
- `--pico-primary` — accent color (blue `#01aaff`)
- `--pico-card-background-color` — `#181c25` (base card bg)
- `--pico-muted` — muted text/border (**Pico v2 classless caveat:** this variable is NOT defined. Use `rgba(255,255,255,0.08)` for borders and `rgba(255,255,255,0.3)` for muted text as safe fallbacks. Hardcoded fallback example: `.browser-entry { background: #1e2430; border: 1px solid rgba(255,255,255,0.08); }`)

### Print Styles (`print.css`)

Hides all interactive chrome when printing: navigation, buttons, modals, toast, the export dropdown, and browser actions. Only entry content, headers, and metadata are printed. Applied via `media="print"` on the `<link>` tag.

## Data Flow Summary

```mermaid
flowchart TB
    subgraph Browser
        USER[User Interaction]
        ROUTER[Hash Router]
        VIEW[Active View]
        API[ThreadAPI client]
        STORAGE[SessionStorage<br/>JWT token]
    end
    subgraph Server
        FLASK[Flask / Waitress]
        SQLITE[(SQLite + FTS5)]
    end

    USER -->|"click link / type URL"| ROUTER
    ROUTER -->|"mount(params, query)"| VIEW
    VIEW -->|"fetch() + Bearer token"| API
    API -->|"GET/POST/PUT/DELETE"| FLASK
    FLASK -->|"SQL queries"| SQLITE
    SQLITE -->|"rows"| FLASK
    FLASK -->|"JSON response"| API
    API -->|"destructured data"| VIEW
    VIEW -->|"mountHTML(html)"| USER

    STORAGE -->|"read token"| API
    FLASK -->|"JWT on login"| STORAGE
```

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Initial load** | ~35KB HTML + ~30KB Pico.css + ~15KB JS | No build step, no bundler overhead |
| **Page transitions** | <50ms | Client-side hash routing, no server round-trip |
| **Chart rendering** | <100ms (Chart.js) | Canvas-based, 2 datasets per chart |
| **API calls** | 5-50ms (local network) | SQLite with WAL mode, no network latency on Pi |
| **SSE reconnect** | 30s interval | Server pushes stats; client reconnects automatically |
| **Memory (browser)** | ~5-10MB | Vanilla JS, no framework overhead |

## Browser Support

Target: **Modern evergreen browsers** (Chrome 90+, Firefox 90+, Safari 15+, Edge 90+).

Uses ES modules (`import`/`export`), `fetch()`, `AbortController`, `EventSource`, `Blob`, `URL.createObjectURL` — all widely supported since 2020. No polyfills needed.
