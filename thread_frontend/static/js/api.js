/**
 * ThreadAPI — client-side API wrapper for all Thread server endpoints.
 *
 * Reads the auth token from localStorage and attaches it as a Bearer token.
 * On 401 responses, clears the token and redirects to login. In debug mode
 * (when auth is disabled server-side), Bearer is still sent — the server
 * ignores it.
 */

import { Auth } from "./auth.js";

const API_BASE = "/api/v1";

/**
 * Make an authenticated fetch request to the Thread API.
 *
 * @param {string} path - API path (e.g. "/sessions")
 * @param {object} [options] - Fetch options (method, body, etc.)
 * @returns {Promise<Response>}
 */
async function request(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  const token = Auth.getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  // Auth failure: clear token and redirect to login
  if (response.status === 401) {
    Auth.clearToken();
    window.location.hash = "login";
    throw new Error("Authentication required");
  }

  return response;
}

/**
 * API client with methods for every endpoint.
 *
 * Usage:
 *   const api = new ThreadAPI();
 *   const sessions = await api.listSessions();
 *   const entry = await api.createEntry("my-session", { content: "Hello" });
 */
export class ThreadAPI {
  // ── Auth ────────────────────────────────────────────────────────────────
  async login(username, password) {
    const res = await request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async logout() {
    const res = await request("/auth/logout", { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async getAuthStatus() {
    const res = await request("/auth/status");
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  // ── Health & Stats ──────────────────────────────────────────────────────
  async getHealth() {
    const res = await request("/health");
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async getStats() {
    const res = await request("/stats");
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async getStorage() {
    const res = await request("/stats/storage");
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  // ── Sessions ─────────────────────────────────────────────────────────────
  async listSessions() {
    const res = await request("/sessions");
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async createSession(name, description = "") {
    const res = await request("/sessions", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async deleteSession(name) {
    const res = await request(`/sessions/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  // ── Entries ──────────────────────────────────────────────────────────────
  async listEntries(sessionName, limit = 50, before = null) {
    let url = `/sessions/${encodeURIComponent(sessionName)}/entries?limit=${limit}`;
    if (before) url += `&before=${encodeURIComponent(before)}`;
    const res = await request(url);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async getEntry(sessionName, entryId) {
    const res = await request(
      `/sessions/${encodeURIComponent(sessionName)}/entries/${encodeURIComponent(entryId)}`
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async createEntry(sessionName, { content, priority = 5, tags = [] }) {
    const res = await request(
      `/sessions/${encodeURIComponent(sessionName)}/entries`,
      {
        method: "POST",
        body: JSON.stringify({ content, priority, tags }),
      }
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async updateEntry(sessionName, entryId, updates) {
    const res = await request(
      `/sessions/${encodeURIComponent(sessionName)}/entries/${encodeURIComponent(entryId)}`,
      {
        method: "PUT",
        body: JSON.stringify(updates),
      }
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async deleteEntry(sessionName, entryId) {
    const res = await request(
      `/sessions/${encodeURIComponent(sessionName)}/entries/${encodeURIComponent(entryId)}`,
      { method: "DELETE" }
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async batchRead(ids) {
    const res = await request("/entries", {
      method: "POST",
      body: JSON.stringify({ ids }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async bulkCreate(sessionName, entries) {
    const res = await request(
      `/sessions/${encodeURIComponent(sessionName)}/entries/bulk`,
      {
        method: "POST",
        body: JSON.stringify({ entries }),
      }
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  // ── Upload ───────────────────────────────────────────────────────────────
  async uploadFile(formData, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/upload`);
      const token = Auth.getToken();
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
      xhr.onload = () => {
        if (xhr.status === 401) {
          Auth.clearToken();
          window.location.hash = "login";
          reject(new Error("Authentication required"));
          return;
        }
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error(xhr.responseText));
        }
      };
      xhr.onerror = () => reject(new Error("Upload failed"));
      xhr.send(formData);
    });
  }

  // ── Search ───────────────────────────────────────────────────────────────
  async search(sessionName, query, limit = 100) {
    const q = encodeURIComponent(query);
    const res = await request(
      `/sessions/${encodeURIComponent(sessionName)}/search?q=${q}&limit=${limit}`
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async searchGlobal(query, sessions = [], limit = 100) {
    let url = `/search?q=${encodeURIComponent(query)}&limit=${limit}`;
    if (sessions.length > 0) {
      url += `&sessions=${sessions.map(encodeURIComponent).join(",")}`;
    }
    const res = await request(url);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async getTags(sessionName) {
    const res = await request(
      `/sessions/${encodeURIComponent(sessionName)}/tags`
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  // ── Git ──────────────────────────────────────────────────────────────────
  async getGitLog(sessionName, limit = 50, before = null) {
    let url = `/sessions/${encodeURIComponent(sessionName)}/git/log?limit=${limit}`;
    if (before) url += `&before=${encodeURIComponent(before)}`;
    const res = await request(url);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async getGitDiff(sessionName, hash) {
    const res = await request(
      `/sessions/${encodeURIComponent(sessionName)}/git/diff/${encodeURIComponent(hash)}`
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async revertGit(sessionName, hash) {
    const res = await request(
      `/sessions/${encodeURIComponent(sessionName)}/git/revert`,
      {
        method: "POST",
        body: JSON.stringify({ commit_hash: hash }),
      }
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  // ── Real-Time Events (SSE) ───────────────────────────────────────────────
  connectSSE() {
    let url = `${API_BASE}/events`;
    const token = Auth.getToken();
    if (token) url += `?token=${encodeURIComponent(token)}`;
    return new EventSource(url);
  }
}
