/**
 * SearchView — full-text search across sessions with FTS5 ranking.
 *
 * Features:
 * - Search input with 300ms debounce
 * - Session filter via &lt;details&gt; disclosure (no JS close handler needed)
 * - Results with highlight snippets and BM25 rank
 * - URL query sync: ?q=...&sessions=...
 *
 * Uses: api.searchGlobal(), api.listSessions()
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
    this._results = null;
    this._busy = false;
    this._doSearch = debounce(this._performSearch.bind(this), 300);
  }

  async onMount() {
    this.mountHTML(this._renderSkeleton());

    if (this.query.q) {
      const inp = this.root.querySelector(".search-input");
      if (inp) inp.value = this.query.q;
    }

    try {
      this._sessions = await api.listSessions();
      if (this.query.sessions) {
        this._selectedSessions = this.query.sessions.split(",");
      }
      this._renderContent(this._sessions, this._selectedSessions, null);

      if (this.query.q) this._doSearch();
    } catch (err) {
      this.showError(err.message, "#search");
    }
  }

  // ── Rendering ─────────────────────────────────────────────────────────

  _renderSkeleton() {
    return `<article>
      <h2>Search</h2>
      <input type="search" class="search-input" placeholder="Search entries…" autofocus aria-busy="true">
      <div class="search-results">
        <p class="search-hint">Type a query to search across all sessions.</p>
      </div>
    </article>`;
  }

  /** Build the session-filter &lt;details&gt; element. */
  _renderSessionFilter(sessions, selectedSessions) {
    const allSelected = selectedSessions.length === 0;
    const filterLabel = allSelected
      ? "All sessions"
      : `${selectedSessions.length} session${selectedSessions.length !== 1 ? "s" : ""}`;

    const rows = sessions.map((s) => {
      const sel = selectedSessions.includes(s.name);
      return `<label class="session-filter-row${sel ? " selected" : ""}" data-session="${escapeHtml(s.name)}">
        <input type="checkbox" ${sel ? "checked" : ""} tabindex="-1">
        <span>${escapeHtml(s.name)}</span>
        <span class="badge">${s.entry_count ?? 0}</span>
      </label>`;
    }).join("");

    return `<details class="search-filter">
      <summary>▸ Sessions: <strong>${escapeHtml(filterLabel)}</strong></summary>
      <div class="search-filter-body">
        <label class="session-filter-row all-sessions${allSelected ? " selected" : ""}" data-session="__all__">
          <input type="checkbox" ${allSelected ? "checked" : ""} tabindex="-1">
          <span>All sessions</span>
        </label>
        <div class="session-filter-divider"></div>
        ${rows}
      </div>
    </details>`;
  }

  _renderContent(sessions, selectedSessions, results) {
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
      <input type="search" class="search-input" placeholder="Search entries…" autofocus value="${escapeHtml(this.query.q || "")}">
      ${this._renderSessionFilter(sessions, selectedSessions)}
      ${results ? `<p class="search-count">${results.length} result${results.length !== 1 ? "s" : ""}</p>` : ""}
      <div class="search-results">${resultsHtml}</div>
    </article>`);

    this._bindEvents();

    const inp = this.root.querySelector(".search-input");
    if (inp) {
      inp.focus();
      inp.setSelectionRange(inp.value.length, inp.value.length);
    }
  }

  _renderResultItem(result) {
    const prio = priorityColor(result.priority || 5);
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
        <span class="priority-badge ${prio}">P${result.priority ?? "—"}</span>
        ${tags}
        ${rank}
        <time class="entry-time" datetime="${escapeHtml(result.created_at || "")}">${relativeTime(result.created_at)}</time>
      </div>
      <p class="entry-content search-highlight">${highlight}</p>
    </article>`;
  }

  // ── Events ────────────────────────────────────────────────────────────

  _bindEvents() {
    // Search input
    const inp = this.root.querySelector(".search-input");
    if (inp) {
      inp.addEventListener("input", () => {
        this.query = { ...this.query, q: inp.value.trim() };
        this._updateHash();
        this._doSearch();
      });
    }

    // Details toggle — update the arrow
    const details = this.root.querySelector(".search-filter");
    if (details) {
      details.addEventListener("toggle", () => {
        const s = details.querySelector("summary");
        if (s) {
          s.innerHTML = s.innerHTML.replace(
            /^[▸▾]/,
            details.open ? "▾" : "▸"
          );
        }
      });
    }

    // Session filter rows
    this.root.querySelectorAll(".session-filter-row").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.tagName === "INPUT") return;
        const cb = row.querySelector("input[type=checkbox]");
        if (cb) cb.checked = !cb.checked;
        this._onSessionFilterChange();
      });
      const cb = row.querySelector("input[type=checkbox]");
      if (cb) {
        cb.addEventListener("change", () => this._onSessionFilterChange());
      }
    });
  }

  // ── Filter logic ──────────────────────────────────────────────────────

  _onSessionFilterChange() {
    const allRow = this.root.querySelector(".session-filter-row.all-sessions");
    const allCb = allRow?.querySelector("input[type=checkbox]");
    const rows = this.root.querySelectorAll(".session-filter-row:not(.all-sessions)");

    const allChecked = allCb?.checked;
    const anyChecked = Array.from(rows).some(
      (r) => r.querySelector("input[type=checkbox]")?.checked
    );

    if (allChecked) {
      rows.forEach((r) => {
        const cb = r.querySelector("input[type=checkbox]");
        if (cb) cb.checked = false;
        r.classList.remove("selected");
      });
      if (allRow) allRow.classList.add("selected");
    } else if (anyChecked) {
      if (allCb) allCb.checked = false;
      if (allRow) allRow.classList.remove("selected");
      rows.forEach((r) => {
        const cb = r.querySelector("input[type=checkbox]");
        r.classList.toggle("selected", cb?.checked);
      });
    } else {
      if (allCb) allCb.checked = true;
      if (allRow) allRow.classList.add("selected");
      rows.forEach((r) => r.classList.remove("selected"));
    }

    const checked = this.root.querySelectorAll(
      ".session-filter-row input[type=checkbox]:checked"
    );
    const values = Array.from(checked)
      .map((cb) => cb.closest(".session-filter-row")?.dataset.session)
      .filter((v) => v && v !== "__all__");
    this._selectedSessions = values;

    // Update summary label
    const summary = this.root.querySelector(".search-filter summary strong");
    if (summary) {
      summary.textContent = values.length === 0
        ? "All sessions"
        : `${values.length} session${values.length !== 1 ? "s" : ""}`;
    }

    this.query = { ...this.query, sessions: values.join(",") };
    this._updateHash();
    this._doSearch();
  }

  // ── URL hash ──────────────────────────────────────────────────────────

  _updateHash() {
    const q = this.query.q ? `q=${encodeURIComponent(this.query.q)}` : "";
    const s = this._selectedSessions.length > 0
      ? `sessions=${this._selectedSessions.map(encodeURIComponent).join(",")}`
      : "";
    const query = [q, s].filter(Boolean).join("&");
    const target = query ? `search?${query}` : "search";
    if (window.location.hash !== `#${target}`) {
      history.replaceState(null, "", `#${target}`);
    }
  }

  // ── Search logic ──────────────────────────────────────────────────────

  async _performSearch() {
    const query = this.query.q;
    if (!query || query.length < 2) {
      const el = this.root.querySelector(".search-results");
      if (el) el.innerHTML = `<p class="search-hint">Type at least 2 characters to search.</p>`;
      return;
    }

    this._busy = true;
    const el = this.root.querySelector(".search-results");
    if (el) el.innerHTML = `<p aria-busy="true">Searching…</p>`;

    try {
      const response = await api.searchGlobal(query, this._selectedSessions);
      this._renderContent(this._sessions, this._selectedSessions, response.results);
    } catch (err) {
      const el = this.root.querySelector(".search-results");
      if (el) el.innerHTML = `<p class="error-state">Search failed: ${escapeHtml(err.message)}</p>`;
    } finally {
      this._busy = false;
    }
  }
}
