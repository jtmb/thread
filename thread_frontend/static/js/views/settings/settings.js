/**
 * SettingsView — authentication management.
 *
 * Features:
 * - Auth status display (enabled/disabled, logged in/out)
 * - Token management: copy, reveal, log out
 *
 * Uses: api.getStats(), api.getAuthStatus()
 */

import { BaseView } from "../base.js";
import { ThreadAPI } from "../../api.js";
import { Auth } from "../../auth.js";
import { escapeHtml, showToast } from "../../utils.js";

const api = new ThreadAPI();

export class SettingsView extends BaseView {
  constructor(opts) {
    super(opts);
  }

  async onMount() {
    this.showLoading("Loading authentication info…");

    try {
      const [stats, authStatus] = await Promise.all([
        api.getStats(),
        api.getAuthStatus(),
      ]);
      this._render(stats, authStatus);
      this._bindEvents();
    } catch (err) {
      this.showError(err.message, "#settings");
    }
  }

  // ── Rendering ─────────────────────────────────────────────────────────

  _render(stats, authStatus) {
    const token = Auth.getToken();

    this.mountHTML(`<article>
      <h2>Authentication</h2>

      <section class="settings-section">
        <div class="settings-grid">
          <div class="settings-stat">
            <span class="settings-stat-label">Auth Enabled</span>
            <span class="settings-stat-value">${authStatus.auth_enabled ? "✅ Yes" : "❌ No"}</span>
          </div>
          <div class="settings-stat">
            <span class="settings-stat-label">Status</span>
            <span class="settings-stat-value">${authStatus.authenticated ? `✅ Logged in as ${escapeHtml(authStatus.username || "")}` : "🔓 Not authenticated"}</span>
          </div>
        </div>
        <div class="settings-actions">
          ${token ? `
            <button class="settings-copy-token">Copy Token</button>
            <button class="settings-clear-token">Log Out</button>
            <details>
              <summary>Token (click to reveal)</summary>
              <code class="settings-token">${escapeHtml(token)}</code>
            </details>
          ` : `
            <a href="#login" role="button">Go to Login</a>
          `}
        </div>
      </section>
    </article>`);
  }

  // ── Events ────────────────────────────────────────────────────────────

  _bindEvents() {
    const copyBtn = this.root.querySelector(".settings-copy-token");
    const clearBtn = this.root.querySelector(".settings-clear-token");

    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        const token = Auth.getToken();
        if (token) {
          navigator.clipboard.writeText(token).then(
            () => showToast("Token copied to clipboard", "success"),
            () => showToast("Failed to copy token", "error")
          );
        }
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        Auth.clearToken();
        showToast("Logged out", "info");
        setTimeout(() => { window.location.hash = "login"; }, 500);
      });
    }
  }
}
