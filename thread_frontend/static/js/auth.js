/**
 * Auth — authentication state management.
 *
 * Tokens are stored in localStorage. The token format is:
 *   base64(json({ sub, iat, exp })).base64(hmac_sig)
 * using HMAC-SHA256 with a server-side secret. No JWT library needed.
 */

const TOKEN_KEY = "thread_auth_token";

/** Cache of server auth status — set by init() */
let _authEnabled = null;

export const Auth = {
  /** @returns {boolean} True if a token is stored */
  isAuthenticated() {
    return !!localStorage.getItem(TOKEN_KEY);
  },

  /** @returns {string|null} The stored token or null */
  getToken() {
    return localStorage.getItem(TOKEN_KEY);
  },

  /** @param {string} token - Store the auth token */
  setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  },

  /** Remove the auth token from storage */
  clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  },

  /**
   * Check if server-side auth is enabled.
   *
   * Cached after first call. When auth is disabled, auto-logs in
   * so the router doesn't redirect to the login form.
   *
   * @returns {Promise<boolean>} True if the server requires authentication
   */
  async isAuthRequired() {
    if (_authEnabled !== null) return _authEnabled;

    try {
      const res = await fetch("/api/v1/auth/status");
      const data = await res.json();
      _authEnabled = data.auth_enabled === true;

      if (!_authEnabled) {
        // Auth disabled: get a token so the dashboard loads without login
        if (!this.isAuthenticated()) {
          try {
            const loginRes = await fetch("/api/v1/auth/login", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ password: "" }),
            });
            if (loginRes.ok) {
              const loginData = await loginRes.json();
              this.setToken(loginData.token);
            }
          } catch {
            // Non-fatal: proceed without token
          }
        }
      }
    } catch {
      _authEnabled = false;
    }

    return _authEnabled;
  },
};
