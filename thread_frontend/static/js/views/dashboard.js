/**
 * DashboardView — landing page with live-updating metrics and session table.
 *
 * On mount: fetches /api/v1/stats, /api/v1/stats/storage, and /api/v1/sessions
 * in parallel, then renders a Chart.js doughnut (storage), 3 metric cards,
 * and a sorted sessions table with entry counts. Connects to SSE for
 * real-time updates every 30s.
 *
 * chart.js@4.4.7 is loaded in the SPA shell — no dynamic import needed.
 */

import { BaseView } from "./base.js";
import { ThreadAPI } from "../api.js";
import { formatBytes, formatDate, relativeTime, showToast } from "../utils.js";
import { Auth } from "../auth.js";

export class DashboardView extends BaseView {
  constructor(opts) {
    super(opts);
    this._charts = [];
    this._eventSource = null;
  }

  async onMount() {
    this.mountHTML(this._renderSkeleton());

    try {
      const api = new ThreadAPI();
      const [stats, storage, sessions] = await Promise.all([
        api.getStats(),
        api.getStorage(),
        api.listSessions(),
      ]);
      this._renderContent(stats, storage, sessions);
    } catch (err) {
      this.root.innerHTML = `<article class="error-state">
        <h2>Dashboard</h2>
        <p>Could not load dashboard data.</p>
        <small>${err.message}</small>
        <button onclick="location.reload()">Retry</button>
      </article>`;
      return;
    }

    this._connectSSE();
  }

  onUnmount() {
    if (this._eventSource) {
      this._eventSource.close();
      this._eventSource = null;
    }
    for (const c of this._charts) {
      c.destroy();
    }
    this._charts = [];
  }

  onSSEEvent(event) {
    try {
      const data = JSON.parse(event.data);
      if (!data.sessions) return;
      this._updateFromSSE(data);
    } catch {
      // Malformed event — skip
    }
  }

  // ── Rendering ────────────────────────────────────────────────────────────

  /** Show skeleton before data loads */
  _renderSkeleton() {
    return `<article aria-busy="true">
      <h2>Dashboard</h2>
      <p>Loading metrics…</p>
      <div class="dashboard-metrics"></div>
      <div class="sessions-table"></div>
    </article>`;
  }

  /** Full render with fetched data */
  _renderContent(stats, storage, sessions) {
    const totalEntries = stats.db?.total_entries ?? 0;
    const totalSessions = stats.db?.total_sessions ?? sessions.length;
    const uptime = stats.server?.uptime_seconds ?? 0;

    const html = `<article>
      <h2>Dashboard</h2>

      <div class="dashboard-quick-search">
        <input type="search" id="dashboard-search" placeholder="Quick search… (press /)"
               aria-label="Quick search">
      </div>

      <div class="dashboard-metrics">
        <div class="metric-card">
          <span class="metric-value">${totalSessions}</span>
          <span class="metric-label">Sessions</span>
        </div>
        <div class="metric-card">
          <span class="metric-value">${totalEntries.toLocaleString()}</span>
          <span class="metric-label">Entries</span>
        </div>
        <div class="metric-card">
          <span class="metric-value">${this._formatUptime(uptime)}</span>
          <span class="metric-label">Uptime</span>
        </div>
      </div>

      <div class="dashboard-charts">
        <div class="dashboard-chart">
          <canvas id="chart-storage"></canvas>
        </div>
        <div class="dashboard-chart">
          <canvas id="chart-sessions"></canvas>
        </div>
        <div class="dashboard-chart">
          <canvas id="chart-latency"></canvas>
        </div>
      </div>

      ${this._renderServerSection(stats)}
      ${this._renderPoolSection(stats)}
      ${this._renderCacheSection(stats)}
      ${this._renderSessionsTable(sessions)}
    </article>`;

    this.mountHTML(html);
    this._renderAllCharts(storage, stats, sessions);
    this._bindSearchInput();
  }

  _renderSessionsTable(sessions) {
    if (!sessions.length) {
      return `<div class="empty-state">
        <p>No sessions yet.</p>
        <small>Create one via the API or upload a file.</small>
      </div>`;
    }

    // Sort by entry count descending
    const sorted = [...sessions].sort(
      (a, b) => (b.entry_count ?? 0) - (a.entry_count ?? 0)
    );

    const rows = sorted.map((s) => {
      const count = s.entry_count ?? 0;
      const updated = relativeTime(s.updated_at);
      return `<tr>
        <td>
          <a href="#/sessions/${this._escapeAttr(s.name)}" class="session-link">
            ${this._escapeHtml(s.name)}
          </a>
          ${s.description ? `<br><small>${this._escapeHtml(s.description)}</small>` : ""}
        </td>
        <td><span class="badge">${count}</span></td>
        <td><small>${updated}</small></td>
      </tr>`;
    }).join("");

    return `<h3>Sessions</h3>
      <div class="overflow-auto">
        <table class="sessions-table striped">
          <thead><tr>
            <th>Name</th>
            <th>Entries</th>
            <th>Updated</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  _renderServerSection(stats) {
    const server = stats.server || {};
    const db = stats.db || {};
    return `<section class="settings-section">
      <h3>Server</h3>
      <div class="settings-grid">
        <div class="settings-stat">
          <span class="settings-stat-label">Version</span>
          <span class="settings-stat-value">${this._escapeHtml(server.version || "—")}</span>
        </div>
        <div class="settings-stat">
          <span class="settings-stat-label">Uptime</span>
          <span class="settings-stat-value" id="dash-uptime">${this._formatUptime(server.uptime_seconds || 0)}</span>
        </div>
        <div class="settings-stat">
          <span class="settings-stat-label">DB Size</span>
          <span class="settings-stat-value">${formatBytes(db.size_bytes || 0)}</span>
        </div>
        <div class="settings-stat">
          <span class="settings-stat-label">Entries</span>
          <span class="settings-stat-value">${(db.total_entries || 0).toLocaleString()}</span>
        </div>
        <div class="settings-stat">
          <span class="settings-stat-label">Sessions</span>
          <span class="settings-stat-value">${(db.total_sessions || 0).toLocaleString()}</span>
        </div>
        <div class="settings-stat">
          <span class="settings-stat-label">WAL Size</span>
          <span class="settings-stat-value">${formatBytes(db.wal_size_bytes || 0)}</span>
        </div>
      </div>
    </section>`;
  }

  _renderPoolSection(stats) {
    const pool = stats.pool || {};
    const pct = pool.utilization_pct ?? 0;
    return `<section class="settings-section">
      <h3>Connection Pool</h3>
      <div class="settings-grid">
        <div class="settings-stat">
          <span class="settings-stat-label">Active</span>
          <span class="settings-stat-value" id="dash-pool-active">${pool.active_connections ?? "—"}</span>
        </div>
        <div class="settings-stat">
          <span class="settings-stat-label">Total</span>
          <span class="settings-stat-value" id="dash-pool-total">${pool.total_connections ?? "—"}</span>
        </div>
        <div class="settings-stat">
          <span class="settings-stat-label">Utilization</span>
          <span class="settings-stat-value" id="dash-pool-pct">${pct}%</span>
        </div>
      </div>
      <div class="settings-bar">
        <div class="settings-bar-fill" id="dash-pool-bar" style="width:${pct}%;background:${pct > 80 ? '#d32f2f' : 'var(--pico-primary)'}"></div>
      </div>
    </section>`;
  }

  _renderCacheSection(stats) {
    const cache = stats.cache || {};
    const total = (cache.search_hits || 0) + (cache.search_misses || 0);
    const hitRate = total === 0 ? "—" : `${Math.round((cache.search_hits / total) * 100)}%`;
    return `<section class="settings-section">
      <h3>Cache</h3>
      <div class="settings-grid">
        <div class="settings-stat">
          <span class="settings-stat-label">Search Entries</span>
          <span class="settings-stat-value" id="dash-cache-entries">${cache.search_entries ?? "—"}</span>
        </div>
        <div class="settings-stat">
          <span class="settings-stat-label">Max Search</span>
          <span class="settings-stat-value">${cache.search_max ?? "—"}</span>
        </div>
        <div class="settings-stat">
          <span class="settings-stat-label">Hits</span>
          <span class="settings-stat-value" id="dash-cache-hits">${(cache.search_hits ?? 0).toLocaleString()}</span>
        </div>
        <div class="settings-stat">
          <span class="settings-stat-label">Misses</span>
          <span class="settings-stat-value" id="dash-cache-misses">${(cache.search_misses ?? 0).toLocaleString()}</span>
        </div>
        <div class="settings-stat">
          <span class="settings-stat-label">Hit Rate</span>
          <span class="settings-stat-value" id="dash-cache-rate">${hitRate}</span>
        </div>
      </div>
    </section>`;
  }

  _renderAllCharts(storage, stats, sessions) {
    if (!window.Chart) return;
    // Destroy any existing charts before recreating
    for (const c of this._charts) c.destroy();
    this._charts = [];

    this._charts.push(this._renderStorageChart(storage));
    this._charts.push(this._renderSessionsChart(sessions, stats));
    this._charts.push(this._renderLatencyChart(stats));
  }

  _renderStorageChart(storage) {
    const canvas = document.getElementById("chart-storage");
    if (!canvas) return null;

    const total = storage.total_bytes || 1;
    const used = storage.used_bytes || 0;
    const free = total - used;
    const usedPct = Math.round((used / total) * 100);

    const usedColor = usedPct > 85 ? "#d93526"
      : usedPct > 60 ? "#e9a820"
      : "#4caf50";
    const freeColor = "#3a3a5c";

    const centerTextPlugin = {
      id: "centerText",
      afterDraw: (chart) => {
        const { ctx, width, height } = chart;
        ctx.save();
        ctx.font = "bold 22px system-ui, sans-serif";
        ctx.fillStyle = usedColor;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(`${usedPct}%`, width / 2, height / 2 - 6);
        ctx.font = "10px system-ui, sans-serif";
        ctx.fillStyle = "#888";
        ctx.fillText(`${formatBytes(used)} of ${formatBytes(total)}`, width / 2, height / 2 + 14);
        ctx.restore();
      },
    };

    return new window.Chart(canvas, {
      type: "doughnut",
      data: {
        labels: ["Used", "Free"],
        datasets: [{
          data: [used, free],
          backgroundColor: [usedColor, freeColor],
          borderColor: [usedColor, freeColor],
          borderWidth: 1,
          borderRadius: 4,
        }],
      },
      options: {
        cutout: "60%",
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          title: { display: true, text: "Disk Usage", font: { size: 13 }, color: "#aaa", padding: { bottom: 6 } },
          legend: {
            display: true, position: "bottom",
            labels: { padding: 16, usePointStyle: true, pointStyleWidth: 10, font: { size: 11 } },
          },
          tooltip: { callbacks: { label: (ctx) => ` ${ctx.label}: ${formatBytes(ctx.raw)}` } },
        },
      },
      plugins: [centerTextPlugin],
    });
  }

  _renderSessionsChart(sessions, stats) {
    const canvas = document.getElementById("chart-sessions");
    if (!canvas) return null;

    const sorted = [...sessions].sort((a, b) => (b.entry_count ?? 0) - (a.entry_count ?? 0));
    const names = sorted.map((s) => s.name);
    const counts = sorted.map((s) => s.entry_count ?? 0);

    // Compute cache hit rate for the overlay line
    const cache = stats?.cache || {};
    const hits = cache.search_hits || 0;
    const misses = cache.search_misses || 0;
    const total = hits + misses;
    const hitRate = total > 0 ? Math.round((hits / total) * 100) : 0;

    return new window.Chart(canvas, {
      type: "line",
      data: {
        labels: names,
        datasets: [{
          label: "Entries",
          data: counts,
          borderColor: "#2196f3",
          backgroundColor: "rgba(33, 150, 243, 0.06)",
          borderWidth: 2,
          pointBackgroundColor: "#2196f3",
          pointRadius: 4,
          pointHoverRadius: 6,
          fill: true,
          tension: 0.3,
          yAxisID: "y",
        }, {
          label: `Cache Hit Rate (${hitRate}%)`,
          data: names.map(() => hitRate),
          borderColor: "#4caf50",
          backgroundColor: "rgba(76, 175, 80, 0.04)",
          borderWidth: 2,
          borderDash: [6, 3],
          pointBackgroundColor: "#4caf50",
          pointRadius: 3,
          pointHoverRadius: 5,
          fill: true,
          tension: 0,
          yAxisID: "y1",
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: { display: true, text: "Entries vs Cache Hit Rate", font: { size: 13 }, color: "#aaa", padding: { bottom: 6 } },
          legend: { display: true, position: "bottom", labels: { boxWidth: 12, padding: 12, font: { size: 10 }, usePointStyle: true } },
          tooltip: {
            callbacks: {
              label: (ctx) => ctx.dataset.yAxisID === "y1"
                ? ` Cache Hit Rate: ${hitRate}%`
                : ` ${ctx.raw} entries`,
            },
          },
        },
        scales: {
          y: {
            type: "linear",
            position: "left",
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: "#333" },
            title: { display: true, text: "Entries", color: "#2196f3" },
          },
          y1: {
            type: "linear",
            position: "right",
            beginAtZero: true,
            max: 100,
            ticks: { callback: (v) => v + "%", stepSize: 20 },
            grid: { display: false },
            title: { display: true, text: "Hit Rate", color: "#4caf50" },
          },
          x: { ticks: { font: { size: 10 }, maxRotation: 45 }, grid: { display: false } },
        },
      },
    });
  }

  _renderLatencyChart(stats) {
    const canvas = document.getElementById("chart-latency");
    if (!canvas) return null;

    const req = stats.requests || {};
    const labels = ["Avg", "P50", "P95", "P99"];
    const values = [
      req.average_ms ?? 0,
      req.p50_ms ?? 0,
      req.p95_ms ?? 0,
      req.p99_ms ?? 0,
    ];

    return new window.Chart(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "ms",
          data: values,
          backgroundColor: ["#2196f3", "#4caf50", "#ff9800", "#d93526"],
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: { display: true, text: "Request Latency", font: { size: 13 }, color: "#aaa", padding: { bottom: 6 } },
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => ` ${ctx.raw.toFixed(2)} ms` } },
        },
        scales: {
          y: { beginAtZero: true, title: { display: true, text: "ms", font: { size: 10 } }, grid: { color: "#333" } },
          x: { grid: { display: false } },
        },
      },
    });
  }

  // ── SSE ──────────────────────────────────────────────────────────────────

  _connectSSE() {
    const token = Auth.getToken();
    const url = token
      ? `/api/v1/events?token=${encodeURIComponent(token)}`
      : "/api/v1/events";

    this._eventSource = new EventSource(url);

    this._eventSource.addEventListener("stats_update", (e) => {
      try {
        const data = JSON.parse(e.data);
        this._updateFromSSE(data);
      } catch {
        // Malformed event — ignore
      }
    });

    this._eventSource.onerror = () => {
      // EventSource auto-reconnects. No user-visible error needed.
    };
  }

  /** Update metric cards, pool bar, cache stats, and session table from SSE data. */
  _updateFromSSE(data) {
    const sessions = data.sessions || [];
    const totalEntries = data.total_entries ?? 0;
    const totalSessions = data.total_sessions ?? sessions.length;

    // Update metric cards
    const cards = document.querySelectorAll(".metric-card .metric-value");
    if (cards.length >= 2) {
      cards[0].textContent = String(totalSessions);
      cards[1].textContent = totalEntries.toLocaleString();
    }

    // Update pool stats + utilization bar
    if (data.pool) {
      const activeEl = document.getElementById("dash-pool-active");
      const totalEl = document.getElementById("dash-pool-total");
      const pctEl = document.getElementById("dash-pool-pct");
      const barEl = document.getElementById("dash-pool-bar");
      if (activeEl) activeEl.textContent = data.pool.active_connections ?? "—";
      if (totalEl) totalEl.textContent = data.pool.total_connections ?? "—";
      const pct = data.pool.utilization_pct ?? 0;
      if (pctEl) pctEl.textContent = `${pct}%`;
      if (barEl) {
        barEl.style.width = `${pct}%`;
        barEl.style.background = pct > 80 ? "#d32f2f" : "var(--pico-primary)";
      }
    }

    // Update uptime
    if (data.server?.uptime_seconds != null) {
      const el = document.getElementById("dash-uptime");
      if (el) el.textContent = this._formatUptime(data.server.uptime_seconds);
    }

    // Update sessions table
    const tableBody = document.querySelector(".sessions-table tbody");
    if (tableBody) {
      const sorted = [...sessions].sort(
        (a, b) => (b.entry_count ?? 0) - (a.entry_count ?? 0)
      );
      tableBody.innerHTML = sorted.map((s) => {
        const count = s.entry_count ?? 0;
        const updated = relativeTime(s.updated_at);
        return `<tr>
          <td>
            <a href="#/sessions/${this._escapeAttr(s.name)}" class="session-link">
              ${this._escapeHtml(s.name)}
            </a>
            ${s.description ? `<br><small>${this._escapeHtml(s.description)}</small>` : ""}
          </td>
          <td><span class="badge">${count}</span></td>
          <td><small>${updated}</small></td>
        </tr>`;
      }).join("");
    }
  }

  // ── Helpers ──────────────────────────────────────────────────────────────

  _formatUptime(seconds) {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const mins = Math.floor(seconds / 60);
    if (mins < 60) return `${mins}m`;
    const hours = Math.floor(mins / 60);
    const rem = mins % 60;
    if (hours < 24) return `${hours}h ${rem}m`;
    const days = Math.floor(hours / 24);
    return `${days}d ${hours % 24}h`;
  }

  _bindSearchInput() {
    const input = document.getElementById("dashboard-search");
    if (!input) return;
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const q = input.value.trim();
        if (q) window.location.hash = `search?q=${encodeURIComponent(q)}`;
      }
    });
    // Focus on "/" keyboard shortcut
    const handler = (e) => {
      if (e.key === "/" && document.activeElement !== input) {
        e.preventDefault();
        input.focus();
      }
    };
    document.addEventListener("keydown", handler);
    this._onKeydown = handler;
  }

  _escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  _escapeAttr(str) {
    return str.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
}
