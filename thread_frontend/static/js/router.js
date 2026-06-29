/**
 * Hash Router — matches URL hash to views and mounts them into #app-root.
 *
 * Routes map hash fragments (minus leading #) to View classes. The router
 * guards authenticated routes and handles keyboard shortcuts.
 */

import { views } from "./views/index.js";

/** Route definition: pattern → View constructor, optional auth gate */
const ROUTES = [
  { pattern: "",             view: views.DashboardView },
  { pattern: "sessions/:name",      view: views.BrowserView,   auth: true },
  { pattern: "search",              view: views.SearchView,    auth: true },
  { pattern: "upload",              view: views.UploadView,    auth: true },
  { pattern: "sessions/:name/history",  view: views.HistoryView,   auth: true },
  { pattern: "sessions/:name/graph",    view: views.GraphView,     auth: true },
  { pattern: "settings",            view: views.SettingsView,  auth: true },
  { pattern: "login",               view: views.LoginView },
];

/** Currently mounted view instance — cleaned up on navigation */
let _currentView = null;

/**
 * Parse a hash fragment and match against registered routes.
 *
 * @param {string} hash - The raw hash without leading #
 * @returns {{ view: Function, params: object } | null}
 */
function matchRoute(hash) {
  // Strip query string for matching
  const pathOnly = hash.split("?")[0];
  const segments = pathOnly.split("/").filter(Boolean);

  for (const route of ROUTES) {
    const patternSegs = route.pattern.split("/").filter(Boolean);
    if (patternSegs.length === 0 && segments.length === 0) {
      return { view: route.view, params: {} };
    }
    if (patternSegs.length !== segments.length) continue;

    const params = {};
    let matched = true;
    for (let i = 0; i < patternSegs.length; i++) {
      if (patternSegs[i].startsWith(":")) {
        params[patternSegs[i].slice(1)] = segments[i];
      } else if (patternSegs[i] !== segments[i]) {
        matched = false;
        break;
      }
    }
    if (matched) {
      return { view: route.view, params, auth: route.auth };
    }
  }
  return null;
}

/** Parse query string from hash into an object */
function parseQuery(hash) {
  const qs = hash.includes("?") ? hash.split("?")[1] : "";
  const params = {};
  for (const pair of qs.split("&").filter(Boolean)) {
    const [k, v] = pair.split("=");
    params[decodeURIComponent(k)] = decodeURIComponent(v || "");
  }
  return params;
}

/**
 * Navigate to a hash route programmatically.
 * @param {string} path - e.g. "/sessions/my-topic"
 */
export function navigate(path) {
  window.location.hash = path;
}

/**
 * Render the current route — called on hashchange and initial load.
 */
export async function render() {
  const hash = window.location.hash.replace("#", "");
  const match = matchRoute(hash);

  // Auth guard: redirect unauthenticated users to login
  const { Auth } = await import("./auth.js");
  if (match && match.auth && !Auth.isAuthenticated()) {
    const authRequired = await Auth.isAuthRequired();
    if (authRequired) {
      window.location.hash = "login";
      return;
    }
    // Auth disabled server-side — Auth.isAuthRequired() already auto-logged in
  }

  // Unmount previous view
  if (_currentView && typeof _currentView.onUnmount === "function") {
    _currentView.onUnmount();
  }
  _currentView = null;

  const root = document.getElementById("app-root");
  if (!root) return;

  // Show loading state
  root.innerHTML = `<div class="loading" aria-busy="true">Loading...</div>`;

  // 404 — no matching route
  if (!match) {
    root.innerHTML = `<article class="error-state">
      <h2>404 — Not Found</h2>
      <p>No route matches <code>#${hash || "/"}</code></p>
      <a href="#/" role="button">Go Home</a>
    </article>`;
    return;
  }

  // Instantiate and mount
  try {
    const query = parseQuery(hash);
    const viewInst = new match.view({ params: match.params, query });
    _currentView = viewInst;

    if (typeof viewInst.onMount === "function") {
      await viewInst.onMount();
    }
  } catch (err) {
    console.error("View mount error:", err);
    root.innerHTML = `<article class="error-state">
      <h2>Error</h2>
      <p>Failed to load view: ${err.message}</p>
      <a href="#/" role="button">Go Home</a>
    </article>`;
  }
}

/** Initialize router — bind events and render on load */
export function init() {
  window.addEventListener("hashchange", render);
  window.addEventListener("DOMContentLoaded", render);
  _setupKeyboardShortcuts();

  // Initial render (if hash already set or empty)
  if (document.readyState === "interactive" || document.readyState === "complete") {
    render();
  }
}

/** Keyboard shortcuts for navigation */
function _setupKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    // Ignore when typing in inputs
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;

    // Escape — close any open modal
    if (e.key === "Escape") {
      const modal = document.getElementById("modal-root");
      if (modal) modal.innerHTML = "";
    }

    // / — focus search
    if (e.key === "/" && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      const searchInput = document.querySelector("#search-input");
      if (searchInput) searchInput.focus();
    }

    // g + key navigation (g prefix)
    if (e.key === "g") {
      const handler = (e2) => {
        document.removeEventListener("keydown", handler);
        switch (e2.key) {
          case "d": navigate(""); break;           // dashboard
          case "s": navigate("settings"); break;   // settings
          case "l": navigate("login"); break;      // login
        }
      };
      document.addEventListener("keydown", handler, { once: true });
    }
  });
}
