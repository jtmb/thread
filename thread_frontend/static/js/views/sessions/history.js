/**
 * HistoryView — git commit timeline with diff viewer and revert capability.
 *
 * Features:
 * - Vertical timeline using CSS .commit-timeline / .commit-item (already styled)
 * - "Load more" cursor pagination
 * - Click commit to expand inline diff (green/red highlighting)
 * - Revert button with confirmation
 *
 * Route: #sessions/:name/history?limit=50&before=<hash>
 * Uses: api.getGitLog(), api.getGitDiff(), api.revertGit()
 */

import { BaseView } from "../base.js";
import { ThreadAPI } from "../../api.js";
import { escapeHtml, relativeTime, showToast } from "../../utils.js";

const api = new ThreadAPI();
const PAGE_SIZE = 30;

export class HistoryView extends BaseView {
  constructor(opts) {
    super(opts);
    this._sessionName = opts.params?.name || "";
    this._commits = [];
    this._cursor = null;
    this._hasMore = true;
    this._expandedHash = null;
    this._diffs = {};  // hash → diff text cache
    this._loadingDiff = false;
  }

  async onMount() {
    const name = this._sessionName;
    if (!name) {
      this.showError("No session name specified", "#/");
      return;
    }
    this.showLoading(`Loading history for ${escapeHtml(name)}…`);

    try {
      await this._fetchCommits();
      this._render();
      this._bindEvents();
    } catch (err) {
      // Git repo may not exist yet
      this.mountHTML(`<article>
        <h2>Git History: ${escapeHtml(name)}</h2>
        <div class="empty-state">
          <p>No git history available yet. Commits are created automatically when entries are added or modified.</p>
          <a href="#sessions/${encodeURIComponent(name)}" role="button">Browse entries</a>
        </div>
      </article>`);
    }
  }

  async _fetchCommits() {
    const log = await api.getGitLog(this._sessionName, PAGE_SIZE, this._cursor);
    if (log && log.commits) {
      this._commits = this._commits.concat(log.commits);
      this._hasMore = log.commits.length >= PAGE_SIZE;
      if (log.commits.length > 0) {
        this._cursor = log.commits[log.commits.length - 1].hash;
      }
    } else if (Array.isArray(log)) {
      this._commits = this._commits.concat(log);
      this._hasMore = log.length >= PAGE_SIZE;
      if (log.length > 0) {
        this._cursor = log[log.length - 1].hash;
      }
    } else {
      this._hasMore = false;
    }
  }

  // ── Rendering ─────────────────────────────────────────────────────────

  _render() {
    const name = this._sessionName;
    let timelineHtml;

    if (this._commits.length === 0) {
      timelineHtml = `<div class="empty-state">
        <p>No commits yet.</p>
      </div>`;
    } else {
      timelineHtml = this._commits.map((c) => this._renderCommit(c)).join("");
    }

    this.mountHTML(`<article>
      <h2>Git History: ${escapeHtml(name)}</h2>
      <p>${this._commits.length} commit${this._commits.length !== 1 ? "s" : ""}</p>

      <div class="commit-timeline">
        ${timelineHtml}
      </div>

      ${this._hasMore ? `<div class="history-load-more">
        <button class="history-load-btn" id="history-load-btn">Load older commits…</button>
      </div>` : ""}
    </article>`);

    this._bindEvents();
  }

  _renderCommit(commit) {
    const isExpanded = this._expandedHash === commit.hash;
    const hashShort = (commit.hash || "").slice(0, 7);
    const diff = this._diffs[commit.hash];

    return `<div class="commit-item" data-hash="${escapeHtml(commit.hash || "")}">
      <div class="commit-header">
        <code class="commit-hash" title="${escapeHtml(commit.hash || "")}">${escapeHtml(hashShort)}</code>
        <span class="commit-message">${escapeHtml(commit.message || commit.subject || "")}</span>
        <time class="commit-time">${relativeTime(commit.date || commit.timestamp)}</time>
      </div>
      <div class="commit-meta">
        <span class="commit-author">${escapeHtml(commit.author || commit.author_name || "")}</span>
      </div>
      <div class="commit-actions">
        <button class="commit-diff-btn" data-hash="${escapeHtml(commit.hash || "")}">
          ${isExpanded ? "Hide diff" : "Show diff"}
        </button>
        <button class="commit-revert-btn" data-hash="${escapeHtml(commit.hash || "")}">
          ↩ Revert
        </button>
      </div>
      ${isExpanded ? `<div class="commit-diff">${diff
        ? this._renderDiffContent(diff)
        : `<p aria-busy="true">Loading diff…</p>`
      }</div>` : ""}
    </div>`;
  }

  _renderDiffContent(diff) {
    if (!diff) return "";
    // Split into lines and colorize
    const lines = diff.split("\n");
    return `<pre class="diff-view">${lines.map((line) => {
      if (line.startsWith("+") && !line.startsWith("+++")) {
        return `<span class="diff-added">${escapeHtml(line)}</span>`;
      }
      if (line.startsWith("-") && !line.startsWith("---")) {
        return `<span class="diff-removed">${escapeHtml(line)}</span>`;
      }
      if (line.startsWith("@@")) {
        return `<span class="diff-hunk">${escapeHtml(line)}</span>`;
      }
      return escapeHtml(line);
    }).join("\n")}</pre>`;
  }

  // ── Events ────────────────────────────────────────────────────────────

  _bindEvents() {
    // Load more
    const loadBtn = this.root.querySelector("#history-load-btn");
    if (loadBtn) {
      loadBtn.addEventListener("click", async () => {
        loadBtn.disabled = true;
        loadBtn.textContent = "Loading…";
        try {
          await this._fetchCommits();
          this._render();
        } catch (err) {
          showToast(`Failed: ${err.message}`, "error");
          loadBtn.disabled = false;
          loadBtn.textContent = "Load older commits…";
        }
      });
    }

    // Toggle diff
    this.root.querySelectorAll(".commit-diff-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const hash = btn.dataset.hash;
        if (this._expandedHash === hash) {
          this._expandedHash = null;
          this._render();
          return;
        }
        this._expandedHash = hash;
        this._render();

        // Fetch diff if not cached
        if (!this._diffs[hash] && !this._loadingDiff) {
          this._loadingDiff = true;
          try {
            const result = await api.getGitDiff(this._sessionName, hash);
            this._diffs[hash] = result.diff || result.text || result;
            this._render();
          } catch (err) {
            this._diffs[hash] = `Error loading diff: ${err.message}`;
            this._render();
          } finally {
            this._loadingDiff = false;
          }
        }
      });
    });

    // Revert
    this.root.querySelectorAll(".commit-revert-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const hash = btn.dataset.hash;
        const confirmed = confirm(
          `Revert commit ${(hash || "").slice(0, 7)}?\n\nThis will restore the repository to the state before this commit.`
        );
        if (!confirmed) return;

        btn.disabled = true;
        btn.textContent = "Reverting…";
        try {
          await api.revertGit(this._sessionName, hash);
          showToast(`Commit ${(hash || "").slice(0, 7)} reverted`, "success");
          // Reload commits
          this._commits = [];
          this._cursor = null;
          this._expandedHash = null;
          this._diffs = {};
          await this._fetchCommits();
          this._render();
        } catch (err) {
          showToast(`Revert failed: ${err.message}`, "error");
          btn.disabled = false;
          btn.textContent = "↩ Revert";
        }
      });
    });
  }
}
