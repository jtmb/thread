/**
 * SearchView — full-text search across sessions with FTS5 ranking.
 *
 * Features:
 * - Search input with 300ms debounce
 * - Session multi-select filter (cross-session search)
 * - Tag filter chips from session tags
 * - Results with highlight snippets and BM25 rank
 * - URL query sync: ?q=...&sessions=...
 *
 * Uses: api.searchGlobal(), api.search(), api.getTags(), api.listSessions()
 */

import { BaseView } from "../base.js";
import { ThreadAPI } from "../../api.js";
import { escapeHtml, debounce, relativeTime, priorityColor } from "../../utils.js";

const api = new ThreadAPI();

export class SearchView extends BaseView {
  constructor(opts) {
    super(opts);
    this._sessions = [];
    this._selectedSessions = [];
    this._tags = [];
    this._results = null;
    this._busy = false;
    // Debounced search: fires 300ms after last keystroke
    this._doSearch = debounce(this._performSearch.bind(this), 300);
  }

  async onMount() {
    this.mountHTML(this._renderSkeleton());

    // Parse initial query from URL
    if (this.query.q) {
      const input = this.root.querySelector(".search-input");
      if (input) input.value = this.query.q;
    }

    try {
      [this._sessions] = await Promise.all([
        api.listSessions(),
      ]);
      // Extract target sessions from URL
      if (this.query.sessions) {
        this._selectedSessions = this.query.sessions.split(",");
      }
      this._renderContent(this._sessions, this._selectedSessions, null);
      this._bindEvents();

      // Run initial search if query present
      if (this.query.q) {
        this._doSearch();
      }
    } catch (err) {
      this.showError(err.message, "#search");
    }
  }

  // ── Rendering ─────────────────────────────────────────────────────────

  _renderSkeleton() {
    return `<article>
      <h2>Search</h2>
      <div class="search-controls" aria-busy="true">
        <input type="search" class="search-input" placeholder="Search entries..." autofocus>
        <div class="search-filters">
          <select class="session-filter" multiple size="1">
            <option value="">Loading sessions…</option>
          </select>
        </div>
      </div>
      <div class="search-results">
        <p class="search-hint">Type a query to search across all sessions.</p>
      </div>
    </article>`;
  }

  _renderContent(sessions, selectedSessions, results) {
    const sessionOptions = sessions.map((s) => {
      const sel = selectedSessions.includes(s.name) ? " selected" : "";
      return `<option value="${escapeHtml(s.name)}"${sel}>${escapeHtml(s.name)} (${s.entry_count ?? 0})</option>`;
    }).join("");

    let resultsHtml;
    if (!results) {
      resultsHtml = `<p class="search-hint">Type a query to search across ${sessions.length} sessions. Prefix match (pyth*) and phrase ("exact phrase") supported.</p>`;
    } else if (results.length === 0) {
      resultsHtml = `<div class="empty-state">
        <p>No results found. Try different keywords or broaden your session filter.</p>
      </div>`;
    } else {
      resultsHtml = results.map((r) => this._renderResultItem(r)).join("");
    }

    this.mountHTML(`<article>
      <h2>Search</h2>
      <div class="search-controls">
        <input type="search" class="search-input" placeholder="Search entries..." autofocus value="${escapeHtml(this.query.q || "")}">
        <div class="search-filters">
          <select class="session-filter" multiple size="${Math.min(sessions.length + 1, 6)}">
            <option value="__all__"${selectedSessions.length === 0 ? " selected" : ""}>All sessions</option>
            <option disabled>──────────</option>
            ${sessionOptions}
          </select>
        </div>
      </div>
      ${results ? `<p class="search-count">${results.length} result${results.length !== 1 ? "s" : ""}</p>` : ""}
      <div class="search-results">${resultsHtml}</div>
    </article>`);

    this._bindEvents();
    // Focus search input
    const input = this.root.querySelector(".search-input");
    if (input) {
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    }
  }

  _renderResultItem(result) {
    const priority = priorityColor(result.priority || 5);
    const tags = (result.tags || []).map(
      (t) => `<span class="tag-chip">${escapeHtml(t)}</span>`
    ).join("");
    const sessionLabel = result.session_name
      ? `<span class="search-session-label">${escapeHtml(result.session_name)}</span>`
      : "";
    const highlight = result.highlight || escapeHtml((result.content || "").slice(0, 300));
    const rank = result.rank != null
      ? `<span class="search-rank" title="BM25 relevance score">${Number(result.rank).toFixed(1)}</span>`
      : "";

    return `<article class="entry-card search-result-item" data-entry-id="${escapeHtml(result.id || "")}">
      <div class="entry-meta">
        ${sessionLabel}
        <span class="priority-badge ${priority}">P${result.priority ?? "—"}</span>
        ${tags}
        ${rank}
        <time class="entry-time" datetime="${escapeHtml(result.created_at || "")}">${relativeTime(result.created_at)}</time>
      </div>
      <p class="entry-content search-highlight">${highlight}</p>
    </article>`;
  }

  // ── Events ────────────────────────────────────────────────────────────

  _bindEvents() {
    const input = this.root.querySelector(".search-input");
    const filter = this.root.querySelector(".session-filter");

    if (input) {
      input.addEventListener("input", () => {
        const q = input.value.trim();
        this.query = { ...this.query, q };
        this._updateHash();
        this._doSearch();
      });
    }

    if (filter) {
      filter.addEventListener("change", () => {
        const selected = Array.from(filter.selectedOptions)
          .map((o) => o.value)
          .filter((v) => v && v !== "__all__");
        this._selectedSessions = selected;
        this.query = { ...this.query, sessions: selected.join(",") };
        this._updateHash();
        this._doSearch();
      });
    }
  }

  _updateHash() {
    const q = this.query.q ? `q=${encodeURIComponent(this.query.q)}` : "";
    const s = this._selectedSessions.length > 0
      ? `sessions=${this._selectedSessions.map(encodeURIComponent).join(",")}`
      : "";
    const query = [q, s].filter(Boolean).join("&");
    const newHash = query ? `search?${query}` : "search";
    if (window.location.hash !== `#${newHash}`) {
      history.replaceState(null, "", `#${newHash}`);
    }
  }

  // ── Search logic ──────────────────────────────────────────────────────

  async _performSearch() {
    const query = this.query.q;
    if (!query || query.length < 2) {
      // Restore hint
      const resultsEl = this.root.querySelector(".search-results");
      if (resultsEl) {
        resultsEl.innerHTML = `<p class="search-hint">Type at least 2 characters to search.</p>`;
      }
      return;
    }

    this._busy = true;
    const resultsEl = this.root.querySelector(".search-results");
    if (resultsEl) {
      resultsEl.innerHTML = `<p aria-busy="true">Searching…</p>`;
    }

    try {
      const results = await api.searchGlobal(query, this._selectedSessions);
      this._renderContent(this._sessions, this._selectedSessions, results);
    } catch (err) {
      const resultsEl = this.root.querySelector(".search-results");
      if (resultsEl) {
        resultsEl.innerHTML = `<p class="error-state">Search failed: ${escapeHtml(err.message)}</p>`;
      }
    } finally {
      this._busy = false;
    }
  }
}
