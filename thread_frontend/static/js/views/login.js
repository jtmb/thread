/**
 * LoginView — Pi-hole style full-page password-only login.
 *
 * Hides the nav bar on mount for full-page takeover. On successful
 * login, stores the token and redirects to the dashboard.
 */

import { BaseView } from "./base.js";
import { ThreadAPI } from "../api.js";
import { Auth } from "../auth.js";
import { showToast } from "../utils.js";

const NAV_SELECTOR = ".dashboard-nav";

export class LoginView extends BaseView {
  async onMount() {
    if (Auth.isAuthenticated()) {
      window.location.hash = "";
      return;
    }

    this._hideNav();
    this.mountHTML(this.render());
    this._bindEvents();
  }

  onUnmount() {
    this._showNav();
  }

  _hideNav() {
    const nav = document.querySelector(NAV_SELECTOR);
    if (nav) nav.style.display = "none";
  }

  _showNav() {
    const nav = document.querySelector(NAV_SELECTOR);
    if (nav) nav.style.display = "";
  }

  render() {
    return `
      <div class="login-page">
        <div class="login-card">
          <div class="login-logo">
            <span class="login-icon">🔐</span>
            <h1>Sign in to Thread</h1>
          </div>
          <form id="login-form">
            <label>
              Password
              <input type="password" id="login-password"
                     placeholder="Enter your password"
                     autocomplete="current-password" autofocus>
            </label>
            <div id="login-error" class="login-error" style="display:none;"></div>
            <button type="submit" id="login-submit">Log in</button>
          </form>
        </div>
      </div>`;
  }

  _bindEvents() {
    const form = document.getElementById("login-form");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const btn = document.getElementById("login-submit");
      const errorEl = document.getElementById("login-error");
      const password = document.getElementById("login-password").value;

      if (!password) {
        this._showError(errorEl, "Password is required.");
        return;
      }

      this._setSubmitting(btn, true);
      errorEl.style.display = "none";

      try {
        const api = new ThreadAPI();
        const result = await api.login(password);
        Auth.setToken(result.token);
        showToast("Login successful", "success");
        window.location.hash = "";
      } catch (err) {
        this._showError(errorEl, err.message || "Invalid password. Please try again.");
        this._setSubmitting(btn, false);
        document.getElementById("login-password")?.focus();
      }
    });
  }

  _showError(el, msg) {
    el.textContent = msg;
    el.style.display = "block";
  }

  _setSubmitting(btn, submitting) {
    btn.disabled = submitting;
    btn.textContent = submitting ? "Signing in…" : "Log in";
  }
}
