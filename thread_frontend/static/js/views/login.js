/**
 * LoginView — authentication form for the Thread dashboard.
 *
 * Renders a login form (username + password). On submit, calls
 * ThreadAPI.login(), stores the token, and navigates to the dashboard.
 */

import { BaseView } from "./base.js";
import { ThreadAPI } from "../api.js";
import { Auth } from "../auth.js";
import { showToast } from "../utils.js";

export class LoginView extends BaseView {
  async onMount() {
    // If already authenticated, redirect to dashboard
    if (Auth.isAuthenticated()) {
      window.location.hash = "";
      return;
    }
    this.mountHTML(this.render());
    this._bindEvents();
  }

  render() {
    return `
      <article class="login-form">
        <h2>Login</h2>
        <form id="login-form">
          <label>
            Username
            <input type="text" id="login-username" name="username"
                   placeholder="admin" autocomplete="username" autofocus>
          </label>
          <label>
            Password
            <input type="password" id="login-password" name="password"
                   placeholder="••••••••" autocomplete="current-password">
          </label>
          <div id="login-error" class="login-error" style="display:none;"></div>
          <button type="submit" id="login-submit">Sign in</button>
        </form>
        <p class="login-hint">
          <small>Auth is disabled by default. Contact your administrator
          if you cannot sign in.</small>
        </p>
      </article>`;
  }

  _bindEvents() {
    const form = document.getElementById("login-form");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const btn = document.getElementById("login-submit");
      const errorEl = document.getElementById("login-error");
      const username = document.getElementById("login-username").value.trim();
      const password = document.getElementById("login-password").value;

      if (!username || !password) {
        errorEl.textContent = "Username and password are required.";
        errorEl.style.display = "block";
        return;
      }

      btn.disabled = true;
      btn.textContent = "Signing in…";
      errorEl.style.display = "none";

      try {
        const api = new ThreadAPI();
        const result = await api.login(username, password);
        Auth.setToken(result.token);
        showToast("Login successful", "success");
        window.location.hash = "";
      } catch (err) {
        errorEl.textContent = err.message || "Login failed. Check your credentials.";
        errorEl.style.display = "block";
        btn.disabled = false;
        btn.textContent = "Sign in";
      }
    });
  }
}
