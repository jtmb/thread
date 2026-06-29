/**
 * GraphView — entry relationship visualization.
 *
 * Phase 7 (current): Lists cross-references between entries as a link table.
 * Future: Full vis-network force-directed graph (needs library vendoring).
 *
 * Route: #sessions/:name/graph
 * Uses: api.listEntries()
 */

import { BaseView } from "../base.js";
import { ThreadAPI } from "../../api.js";
import { escapeHtml, showToast } from "../../utils.js";

const api = new ThreadAPI();

export class GraphView extends BaseView {
  constructor(opts) {
    super(opts);
    this._sessionName = opts.params?.name || "";
  }

  async onMount() {
    const name = this._sessionName;
    if (!name) {
      this.showError("No session name specified", "#/");
      return;
    }
    this.showLoading(`Analyzing entry graph for ${escapeHtml(name)}…`);

    try {
      const { data: entries } = await api.listEntries(name, 200);
      const refs = this._extractReferences(entries);
      this._render(entries, refs);
    } catch (err) {
      this.showError(err.message, `#sessions/${encodeURIComponent(name)}`);
    }
  }

  // ── Reference extraction ──────────────────────────────────────────────

  /**
   * Extract cross-references between entries.
   * Detects patterns like: @mention, #tag, link references, "see entry X"
   * @param {Array} entries
   * @returns {Array<{from: string, to: string, type: string}>}
   */
  _extractReferences(entries) {
    const refs = [];
    const idSet = new Set(entries.map((e) => e.id));

    for (const entry of entries) {
      const content = entry.content || "";

      // Detect @entry-id mentions
      const mentions = content.match(/@([a-f0-9-]{8,})/gi) || [];
      for (const m of mentions) {
        const targetId = m.slice(1);
        if (idSet.has(targetId) && targetId !== entry.id) {
          refs.push({ from: entry.id, to: targetId, type: "mention" });
        }
      }

      // Detect #tag references shared with other entries
      const tags = entry.tags || [];
      for (const other of entries) {
        if (other.id === entry.id) continue;
        const otherTags = other.tags || [];
        const common = tags.filter((t) => otherTags.includes(t));
        if (common.length > 0) {
          refs.push({ from: entry.id, to: other.id, type: `tag:${common[0]}` });
        }
      }
    }

    // Deduplicate
    const seen = new Set();
    return refs.filter((r) => {
      const key = `${r.from}→${r.to}:${r.type}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  // ── Rendering ─────────────────────────────────────────────────────────

  _render(entries, refs) {
    const name = this._sessionName;

    // Build ID → preview label mapping
    const labels = {};
    for (const e of entries) {
      const preview = (e.content || "").replace(/\n/g, " ").slice(0, 60);
      labels[e.id] = preview || `entry-${(e.id || "").slice(0, 8)}`;
    }

    let refsHtml;
    if (refs.length === 0) {
      refsHtml = `<div class="empty-state">
        <p>No cross-references found between the ${entries.length} entries in this session.</p>
        <p class="graph-hint">References are detected from @mentions and shared tags between entries.</p>
      </div>`;
    } else {
      const rows = refs.slice(0, 500).map((r) => {
        const fromLabel = labels[r.from] || r.from;
        const toLabel = labels[r.to] || r.to;
        return `<tr>
          <td><code>${escapeHtml((r.from || "").slice(0, 8))}</code></td>
          <td class="graph-ref-label">${escapeHtml(fromLabel)}</td>
          <td class="graph-ref-arrow">→</td>
          <td><span class="tag-chip">${escapeHtml(r.type)}</span></td>
          <td><code>${escapeHtml((r.to || "").slice(0, 8))}</code></td>
          <td class="graph-ref-label">${escapeHtml(toLabel)}</td>
        </tr>`;
      }).join("");

      refsHtml = `<div class="graph-stats">
        <p><strong>${entries.length}</strong> entries, <strong>${refs.length}</strong> references</p>
      </div>
      <div class="graph-ref-table-wrapper">
        <table class="graph-ref-table">
          <thead>
            <tr>
              <th>From ID</th><th>Content</th><th></th><th>Type</th><th></th><th>To Content</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
    }

    this.mountHTML(`<article>
      <h2>Entry Graph: ${escapeHtml(name)}</h2>

      <div id="graph-container">
        ${refsHtml}
      </div>

      <details class="graph-legend">
        <summary>Legend</summary>
        <ul>
          <li><strong>@mention</strong> — Entry content references another entry by ID</li>
          <li><strong>tag:*</strong> — Entries share a common tag</li>
        </ul>
        <p class="graph-future-note">Full interactive graph visualization coming in a future update.</p>
      </details>
    </article>`);
  }
}
