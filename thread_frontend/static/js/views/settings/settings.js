/**
 * AccountView — simple account management page.
 *
 * Shows the currently logged-in identity, with logout and token management.
 * Auth is always enabled — this page is reachable only after login.
 */

import { BaseView } from "../base.js";
import { ThreadAPI } from "../../api.js";
import { Auth } from "../../auth.js";
import { escapeHtml, showToast } from "../../utils.js";

const api = new ThreadAPI();

export class SettingsView extends BaseView {
  async onMount() {
    try {
      const authStatus = await api.getAuthStatus();
      this._render(authStatus);
      this._bindEvents();
    } catch (err) {
      this.showError(err.message, "#settings");
    }
  }

  _render(authStatus) {
    const username = authStatus.username || "admin";
    const token = Auth.getToken();

    this.mountHTML(`<article>
      <h2>Account</h2>

      <p>Signed in as <strong>${escapeHtml(username)}</strong>.</p>

      <div class="settings-actions">
        <button class="settings-clear-token outline">Log Out</button>
        ${token ? `
          <button class="settings-copy-token">Copy Token</button>
          <details>
            <summary>Token</summary>
            <code class="settings-token">${escapeHtml(token)}</code>
          </details>
        ` : `
          <a href="#login" role="button" class="outline">Go to Login</a>
        `}
      </div>

      <hr>

      <h3>API Token</h3>
      <p class="help-text">API tokens never expire. Use one in your MCP bridge config as <code>THREAD_API_TOKEN</code>. Generate a new one to rotate.</p>

      <form id="api-token-form" class="api-token-form">
        <div class="form-error" id="api-token-error" style="display:none"></div>
        <div class="form-success" id="api-token-success" style="display:none"></div>

        <label for="api-token-password">Current Password</label>
        <input type="password" id="api-token-password" name="password" required autocomplete="current-password" placeholder="Enter your password to generate a token">

        <button type="submit" id="api-token-btn">Generate API Token</button>
      </form>

      <div id="api-token-result" style="display:none">
        <label>Your API Token</label>
        <code class="settings-token" id="api-token-value"></code>
        <button class="settings-copy-api-token" style="margin-top:0.5rem">Copy Token</button>
        <p class="help-text" style="margin-top:0.25rem">Copy this token now — you won't be able to see it again. Store it in your MCP config.</p>
      </div>

      <hr>

      <h3>Change Password</h3>
      <form id="change-password-form" class="change-password-form">
        <div class="form-error" id="change-password-error" style="display:none"></div>
        <div class="form-success" id="change-password-success" style="display:none"></div>

        <label for="current-password">Current Password</label>
        <input type="password" id="current-password" name="current_password" required autocomplete="current-password">

        <label for="new-password">New Password</label>
        <input type="password" id="new-password" name="new_password" required autocomplete="new-password" minlength="8">

        <label for="confirm-password">Confirm New Password</label>
        <input type="password" id="confirm-password" name="confirm_password" required autocomplete="new-password" minlength="8">

        <button type="submit" id="change-password-btn">Change Password</button>
      </form>
    </article>`);
  }

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
        showToast("Logged out", "success");
        window.location.hash = "login";
      });
    }

    // Change password form
    const form = this.root.querySelector("#change-password-form");
    if (form) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        this._handleChangePassword(form);
      });
    }

    // API token form
    const apiTokenForm = this.root.querySelector("#api-token-form");
    if (apiTokenForm) {
      apiTokenForm.addEventListener("submit", (e) => {
        e.preventDefault();
        this._handleGenerateApiToken(apiTokenForm);
      });
    }

    // Copy API token button
    const copyApiBtn = this.root.querySelector(".settings-copy-api-token");
    if (copyApiBtn) {
      copyApiBtn.addEventListener("click", () => {
        const token = this.root.querySelector("#api-token-value").textContent;
        if (token) {
          navigator.clipboard.writeText(token).then(
            () => showToast("API token copied to clipboard", "success"),
            () => showToast("Failed to copy token", "error")
          );
        }
      });
    }
  }

  _hideMsg(selector) {
    const el = this.root.querySelector(selector);
    if (el) el.style.display = "none";
  }

  _showError(selector, msg) {
    const el = this.root.querySelector(selector);
    if (el) {
      el.textContent = msg;
      el.style.display = "block";
    }
  }

  _showSuccess(selector, msg) {
    const el = this.root.querySelector(selector);
    if (el) {
      el.textContent = msg;
      el.style.display = "block";
    }
  }

  async _handleGenerateApiToken(form) {
    const password = this.root.querySelector("#api-token-password").value;
    const btn = this.root.querySelector("#api-token-btn");

    // Clear previous messages
    this._hideMsg("#api-token-error");
    this._hideMsg("#api-token-success");
    const resultEl = this.root.querySelector("#api-token-result");
    if (resultEl) resultEl.style.display = "none";

    if (!password) {
      this._showError("#api-token-error", "Password is required.");
      return;
    }

    btn.disabled = true;
    btn.textContent = "Generating…";

    try {
      const data = await api.login(password, 0);
      this.root.querySelector("#api-token-value").textContent = data.token;
      if (resultEl) resultEl.style.display = "block";
      form.reset();
      showToast("API token generated", "success");
    } catch (err) {
      // Try to parse the error message from the response
      let msg = err.message;
      try {
        const parsed = JSON.parse(err.message);
        msg = parsed.message || msg;
      } catch (_) { /* use raw message */ }
      this._showError("#api-token-error", msg);
      showToast(msg, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Generate API Token";
    }
  }

  async _handleChangePassword(form) {
    const currentPassword = this.root.querySelector("#current-password").value;
    const newPassword = this.root.querySelector("#new-password").value;
    const confirmPassword = this.root.querySelector("#confirm-password").value;
    const btn = this.root.querySelector("#change-password-btn");

    // Clear previous messages
    this._hideMsg("#change-password-error");
    this._hideMsg("#change-password-success");

    // Validate
    if (!currentPassword || !newPassword || !confirmPassword) {
      this._showError("#change-password-error", "All fields are required.");
      return;
    }
    if (newPassword.length < 8) {
      this._showError("#change-password-error", "New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      this._showError("#change-password-error", "New passwords do not match.");
      return;
    }
    if (currentPassword === newPassword) {
      this._showError("#change-password-error", "New password must be different from your current password.");
      return;
    }

    // Submit
    btn.disabled = true;
    btn.textContent = "Changing…";

    try {
      await api.changePassword(currentPassword, newPassword);
      this._showSuccess("#change-password-success", "Password changed successfully.");
      form.reset();
      showToast("Password changed", "success");
    } catch (err) {
      this._showError("#change-password-error", err.message);
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Change Password";
    }
  }
}
