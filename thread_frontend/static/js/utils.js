/**
 * Utility functions used across all views.
 *
 * Pure functions, no side effects. Import individually or as a namespace.
 */

/**
 * Format bytes into human-readable size.
 * @param {number} bytes
 * @returns {string} e.g. "2.3 MB"
 */
export function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

/**
 * Format a date to locale string.
 * @param {string|Date} date
 * @returns {string}
 */
export function formatDate(date) {
  if (!date) return "";
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric",
  });
}

/**
 * Human-readable relative time.
 * @param {string|Date} date
 * @returns {string} e.g. "3 minutes ago"
 */
export function relativeTime(date) {
  if (!date) return "";
  const d = typeof date === "string" ? new Date(date) : date;
  const now = Date.now();
  const diff = now - d.getTime();
  const seconds = Math.floor(diff / 1000);

  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes > 1 ? "s" : ""} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours > 1 ? "s" : ""} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} day${days > 1 ? "s" : ""} ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} month${months > 1 ? "s" : ""} ago`;
  const years = Math.floor(months / 12);
  return `${years} year${years > 1 ? "s" : ""} ago`;
}

/**
 * Debounce a function call.
 * @param {Function} fn
 * @param {number} ms - Debounce delay in milliseconds
 * @returns {Function}
 */
export function debounce(fn, ms = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

/**
 * Escape HTML special characters to prevent XSS.
 * @param {string} text
 * @returns {string}
 */
export function escapeHtml(text) {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
  return String(text).replace(/[&<>"']/g, (c) => map[c]);
}

/**
 * Show a toast notification (auto-dismissing).
 * @param {string} message
 * @param {"success"|"error"|"info"} [type="info"]
 */
export function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed; bottom: 1rem; right: 1rem; z-index: 9999;
    padding: 0.75rem 1.25rem; border-radius: 8px; font-size: 0.875rem;
    animation: toastIn 0.3s ease;
  `;
  if (type === "success") toast.style.background = "#388e3c";
  else if (type === "error") toast.style.background = "#d32f2f";
  else toast.style.background = "var(--pico-primary)";

  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s";
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

/**
 * Return a CSS class or hex color for a priority value.
 * @param {number} priority - 0-10
 * @returns {string} CSS class name
 */
export function priorityColor(priority) {
  if (priority >= 8) return "priority-high";
  if (priority >= 5) return "priority-medium";
  return "priority-low";
}

/**
 * Render a single entry as a card HTML string.
 * @param {object} entry - Entry object from the API
 * @returns {string} HTML
 */
export function renderEntryCard(entry) {
  const escaped = escapeHtml(entry.content || "");
  // Truncate to 200 characters for card preview
  const preview = escaped.length > 200 ? escaped.slice(0, 200) + "…" : escaped;
  const tags = (entry.tags || []).map(
    (t) => `<span class="tag-chip">${escapeHtml(t)}</span>`
  ).join("");

  return `<article class="entry-card" data-entry-id="${escapeHtml(entry.id || "")}">
    <div class="entry-meta">
      <span class="priority-badge ${priorityColor(entry.priority)}">P${entry.priority ?? "—"}</span>
      ${tags}
      <time class="entry-time" datetime="${escapeHtml(entry.created_at || "")}">${relativeTime(entry.created_at)}</time>
    </div>
    <p class="entry-content">${preview}</p>
  </article>`;
}
