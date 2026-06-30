/**
 * BrowserView — paginated entry browser for a session.
 *
 * Features:
 * - "Load more" cursor pagination (50 entries per page)
 * - Entry cards using utils.renderEntryCard()
 * - Click entry to expand full content
 * - Inline priority change (select dropdown)
 * - Inline tag editing
 * - Delete entry with modal confirmation
 * - Export dropdown (JSON / Markdown download)
 *
 * Route: #sessions/:name?limit=50
 * Uses: api.listEntries(), api.updateEntry(), api.deleteEntry()
 */

import { BaseView } from "../base.js";
import { ThreadAPI } from "../../api.js";
import { escapeHtml, showToast, relativeTime, priorityColor } from "../../utils.js";

const api = new ThreadAPI();
const PAGE_SIZE = 50;

export class BrowserView extends BaseView {
  constructor(opts) {
    super(opts);
    this._sessionName = opts.params?.name || "";
    this._entries = [];
    this._cursor = null;
    this._hasMore = true;
    this._loading = false;
    this._expandedId = null;
  }

  async onMount() {
    const name = this._sessionName;
    if (!name) {
      this.showError("No session name specified", "#/");
      return;
    }
    this.showLoading(`Loading ${escapeHtml(name)}…`);

    try {
      const { data, pagination } = await api.listEntries(name, PAGE_SIZE);
      this._entries = data;
      this._hasMore = pagination.hasMore;
      if (data.length > 0) {
        this._cursor = data[data.length - 1].id;
      }
      this._render();
    } catch (err) {
      this.showError(err.message, `#sessions/${encodeURIComponent(name)}`);
    }
  }

  // ── Rendering ─────────────────────────────────────────────────────────

  _render() {
    const name = this._sessionName;
    let entriesHtml;
    if (this._entries.length === 0) {
      entriesHtml = `<div class="empty-state">
        <p>This session has no entries yet.</p>
        <a href="#upload" role="button">Upload a file</a>
      </div>`;
    } else {
      entriesHtml = this._entries.map((e) => this._renderEntryCard(e)).join("");
    }

    this.mountHTML(`<article>
      <header>
        <h2>${escapeHtml(name)}</h2>
        <p>${this._entries.length} entry${this._entries.length !== 1 ? "s" : ""}</p>
      </header>

      <div class="browser-toolbar">
        <div class="export-dropdown">
          <button class="browser-export-btn">⬇ Export</button>
          <div class="export-menu" hidden>
            <button data-format="json">📄 JSON</button>
            <button data-format="markdown">📝 Markdown</button>
          </div>
        </div>
        <button class="browser-refresh-btn">🔄 Refresh</button>
      </div>

      <div class="entry-list" id="entry-list">
        ${entriesHtml}
      </div>

      ${this._hasMore ? `<div class="browser-load-more">
        <button class="browser-load-btn" id="load-more-btn">Load more…</button>
      </div>` : ""}

      <div class="modal-overlay" id="delete-modal" hidden>
        <div class="modal-card">
          <h3>Delete entry?</h3>
          <p>This action cannot be undone. The entry will be permanently deleted.</p>
          <div class="modal-actions">
            <button class="modal-cancel">Cancel</button>
            <button class="modal-confirm-delete">Delete</button>
          </div>
        </div>
      </div>
    </article>`);

    this._bindEvents();
  }

  _renderEntryCard(entry) {
    const entryId = String(entry.id ?? "");
    const isExpanded = this._expandedId === entryId;
    const escContent = entry.content || "";
    const preview = escContent.length > 300 && !isExpanded
      ? escapeHtml(escContent).slice(0, 300) + "…"
      : escapeHtml(escContent);
    const tags = (entry.tags || []).map(
      (t) => `<span class="tag-chip">${escapeHtml(t)}</span>`
    ).join("");

    return `<article class="entry-card browser-entry" data-entry-id="${escapeHtml(entry.id || "")}">
      <div class="entry-meta">
        <span class="priority-badge ${priorityColor(entry.priority)}">P${entry.priority ?? "—"}</span>
        ${tags}
        <time class="entry-time" datetime="${escapeHtml(entry.created_at || "")}">${relativeTime(entry.created_at)}</time>
        <span class="browser-entry-actions">
          <select class="browser-priority-select" data-entry-id="${escapeHtml(entry.id || "")}" title="Change priority">
            ${[0,1,2,3,4,5,6,7,8,9,10].map(p => `<option value="${p}"${p === (entry.priority ?? 5) ? " selected" : ""}>P${p}</option>`).join("")}
          </select>
          <button class="browser-edit-tags-btn" data-entry-id="${escapeHtml(entry.id || "")}" title="Edit tags">🏷</button>
          <button class="browser-delete-btn" data-entry-id="${escapeHtml(entry.id || "")}" title="Delete entry">🗑</button>
        </span>
      </div>
      <div class="entry-content browser-content ${isExpanded ? "" : "browser-content-collapsed"}">
        <pre>${preview}</pre>
      </div>
      ${escContent.length > 300 ? `<button class="browser-expand-btn" data-entry-id="${escapeHtml(entry.id || "")}">${isExpanded ? "Show less" : "Show more…"}</button>` : ""}
    </article>`;
  }

  // ── Events ────────────────────────────────────────────────────────────

  _bindEvents() {
    // Load more
    const loadBtn = this.root.querySelector("#load-more-btn");
    if (loadBtn) {
      loadBtn.addEventListener("click", () => this._loadMore());
    }

    // Export dropdown
    const exportBtn = this.root.querySelector(".browser-export-btn");
    const exportMenu = this.root.querySelector(".export-menu");
    if (exportBtn && exportMenu) {
      let closeHandler = null;

      exportBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const opening = exportMenu.hidden;
        exportMenu.hidden = !exportMenu.hidden;

        // Remove any stale close handler
        if (closeHandler) {
          document.removeEventListener("click", closeHandler);
          closeHandler = null;
        }

        // When opening, listen for the next outside click to close
        if (opening) {
          closeHandler = () => {
            exportMenu.hidden = true;
            document.removeEventListener("click", closeHandler);
            closeHandler = null;
          };
          // Defer registration so the current click doesn't trigger it
          setTimeout(() => document.addEventListener("click", closeHandler), 0);
        }
      });

      // Format buttons
      exportMenu.querySelectorAll("button[data-format]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          exportMenu.hidden = true;
          if (closeHandler) {
            document.removeEventListener("click", closeHandler);
            closeHandler = null;
          }
          this._exportEntries(btn.dataset.format);
        });
      });
    }

    // Refresh
    const refreshBtn = this.root.querySelector(".browser-refresh-btn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => this.onMount());
    }

    // Expand/collapse entry content
    this.root.querySelectorAll(".browser-expand-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const entryId = btn.dataset.entryId;
        this._expandedId = this._expandedId === entryId ? null : entryId;
        this._render();
      });
    });

    // Priority change
    this.root.querySelectorAll(".browser-priority-select").forEach((sel) => {
      sel.addEventListener("change", async () => {
        const entryId = sel.dataset.entryId;
        const newPriority = parseInt(sel.value, 10);
        try {
          await api.updateEntry(this._sessionName, entryId, { priority: newPriority });
          showToast(`Priority set to ${newPriority}`, "success");
        } catch (err) {
          showToast(`Failed: ${err.message}`, "error");
          // Revert select
          const entry = this._entries.find((e) => e.id === entryId);
          if (entry) sel.value = String(entry.priority ?? 5);
        }
      });
    });

    // Edit tags
    this.root.querySelectorAll(".browser-edit-tags-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const entryId = btn.dataset.entryId;
        const entry = this._entries.find((e) => e.id === entryId);
        if (!entry) return;
        const currentTags = (entry.tags || []).join(", ");
        const newTags = prompt("Edit tags (comma-separated):", currentTags);
        if (newTags !== null) {
          const tags = newTags.split(",").map((t) => t.trim()).filter(Boolean);
          api.updateEntry(this._sessionName, entryId, { tags })
            .then(() => {
              entry.tags = tags;
              this._render();
              showToast("Tags updated", "success");
            })
            .catch((err) => showToast(`Failed: ${err.message}`, "error"));
        }
      });
    });

    // Delete entry
    this.root.querySelectorAll(".browser-delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._pendingDeleteId = btn.dataset.entryId;
        const modal = this.root.querySelector("#delete-modal");
        if (modal) modal.hidden = false;
      });
    });

    // Modal: cancel
    const modalCancel = this.root.querySelector(".modal-cancel");
    if (modalCancel) {
      modalCancel.addEventListener("click", () => {
        const modal = this.root.querySelector("#delete-modal");
        if (modal) modal.hidden = true;
        this._pendingDeleteId = null;
      });
    }

    // Modal: confirm delete
    const modalConfirm = this.root.querySelector(".modal-confirm-delete");
    if (modalConfirm) {
      modalConfirm.addEventListener("click", async () => {
        if (!this._pendingDeleteId) return;
        try {
          await api.deleteEntry(this._sessionName, this._pendingDeleteId);
          this._entries = this._entries.filter((e) => e.id !== this._pendingDeleteId);
          this._render();
          showToast("Entry deleted", "success");
        } catch (err) {
          showToast(`Failed: ${err.message}`, "error");
        } finally {
          const modal = this.root.querySelector("#delete-modal");
          if (modal) modal.hidden = true;
          this._pendingDeleteId = null;
        }
      });
    }
  }

  async _loadMore() {
    if (this._loading || !this._hasMore) return;
    this._loading = true;

    const loadBtn = this.root.querySelector("#load-more-btn");
    if (loadBtn) {
      loadBtn.disabled = true;
      loadBtn.textContent = "Loading…";
    }

    try {
      const { data: more } = await api.listEntries(this._sessionName, PAGE_SIZE, this._cursor);
      if (more.length > 0) {
        this._entries = this._entries.concat(more);
        this._cursor = more[more.length - 1].id;
        this._hasMore = more.length >= PAGE_SIZE;
      } else {
        this._hasMore = false;
      }
      this._render();
    } catch (err) {
      showToast(`Failed to load more: ${err.message}`, "error");
    } finally {
      this._loading = false;
    }
  }

  /**
   * Export all loaded entries as a downloadable file.
   * @param {"json"|"markdown"} format
   */
  _exportEntries(format) {
    const entries = this._entries;
    if (entries.length === 0) {
      showToast("No entries to export", "error");
      return;
    }

    const safeName = this._sessionName.replace(/[^a-zA-Z0-9_-]/g, "_");
    let filename, mimeType, content;

    if (format === "json") {
      filename = `${safeName}-export.json`;
      mimeType = "application/json";
      content = JSON.stringify(
        entries.map((e) => ({
          id: e.id,
          content: e.content,
          priority: e.priority,
          tags: e.tags,
          created_at: e.created_at,
        })),
        null,
        2
      );
    } else {
      filename = `${safeName}-export.md`;
      mimeType = "text/markdown";
      content = entries
        .map((e) => {
          const prio = `P${e.priority ?? "—"}`;
          const tags = (e.tags || []).map((t) => `\`${t}\``).join(" ");
          const time = e.created_at ? new Date(e.created_at).toISOString() : "";
          return `## Entry ${e.id ?? "?"}

**Priority:** ${prio}  
**Tags:** ${tags || "—"}  
**Created:** ${time}

${e.content || ""}

---`;
        })
        .join("\n\n");
    }

    const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast(`Exported ${entries.length} entries as ${format.toUpperCase()}`, "success");
  }
}
