/**
 * BaseView — abstract base class for all SPA views.
 *
 * Every view inherits from BaseView and overrides the lifecycle methods.
 * The router calls onMount() after construction and onUnmount() before
 * navigating away. Subclasses MUST implement render(data) → HTML string.
 */

export class BaseView {
  constructor(options = {}) {
    /** @type {object} Route params (e.g. { name: "my-topic" }) */
    this.params = options.params || {};
    /** @type {object} Query string params from hash */
    this.query = options.query || {};
    /** @type {HTMLElement} The #app-root container */
    this.root = document.getElementById("app-root");
  }

  /**
   * Called by router after construction. Subclasses should:
   * 1. Fetch data from the API
   * 2. Call this.mountHTML(this.render(data)) with the fetched data
   * 3. Bind event listeners
   */
  async onMount() {
    this.mountHTML(this.render({}));
  }

  /**
   * Called by router before navigating away. Subclasses should:
   * 1. Remove event listeners
   * 2. Close any open connections (EventSource, timers)
   * 3. Clean up third-party instances (vis-network, Chart.js)
   */
  onUnmount() {
    // No-op: override in subclass
  }

  /**
   * Handle Server-Sent Event pushed from the dashboard.
   * @param {MessageEvent} event - The SSE MessageEvent
   */
  onSSEEvent(event) {
    // No-op: override in subclass (typically DashboardView)
  }

  /**
   * Render HTML into #app-root. Subclasses MUST implement this.
   * @param {object} data - Data to render (entries, stats, etc.)
   * @returns {string} HTML string
   */
  render(data) {
    return `<p>View "${this.constructor.name}" — render() not implemented</p>`;
  }

  /**
   * Mount an HTML string into the app root.
   * @param {string} html
   */
  mountHTML(html) {
    if (this.root) {
      this.root.innerHTML = html;
    }
  }

  /** Show a loading indicator with Pico.css aria-busy */
  showLoading(message = "Loading...") {
    this.mountHTML(`<div class="loading" aria-busy="true">${message}</div>`);
  }

  /**
   * Show an error state with optional retry button.
   * @param {string} message - Error description
   * @param {string} [retryHash] - Hash to navigate to for retry
   */
  showError(message, retryHash) {
    let html = `<article class="error-state">
      <h2>Something went wrong</h2>
      <p>${message}</p>`;
    if (retryHash) {
      html += `<a href="#${retryHash}" role="button">Retry</a>`;
    }
    html += "</article>";
    this.mountHTML(html);
  }

  /**
   * Show an empty state with call-to-action.
   * @param {string} message - e.g. "No sessions yet"
   * @param {string} [ctaLabel] - Button label
   * @param {string} [ctaHash] - Hash to navigate to
   */
  showEmpty(message, ctaLabel, ctaHash) {
    let html = `<article class="empty-state">
      <p>${message}</p>`;
    if (ctaLabel && ctaHash) {
      html += `<a href="#${ctaHash}" role="button">${ctaLabel}</a>`;
    }
    html += "</article>";
    this.mountHTML(html);
  }
}
