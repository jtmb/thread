/**
 * UploadView — file upload with drag-and-drop, progress tracking, and result summary.
 *
 * Features:
 * - Drag-and-drop zone + file picker button
 * - Target session selector (with create-new option)
 * - Tags input (comma-separated)
 * - Priority slider (0-10)
 * - Upload progress bar (via XMLHttpRequest.onprogress)
 * - Result summary: entries created, bytes processed
 *
 * Uses: api.uploadFile(), api.listSessions(), api.createSession()
 */

import { BaseView } from "../base.js";
import { ThreadAPI } from "../../api.js";
import { escapeHtml, showToast, formatBytes } from "../../utils.js";

const api = new ThreadAPI();

export class UploadView extends BaseView {
  constructor(opts) {
    super(opts);
    this._sessions = [];
    this._uploading = false;
    this._xhr = null;
    this._result = null;
  }

  async onMount() {
    this.showLoading("Loading sessions…");

    try {
      this._sessions = await api.listSessions();
      this._renderForm();
      this._bindEvents();
    } catch (err) {
      this.showError(err.message, "#upload");
    }
  }

  onUnmount() {
    // Abort any ongoing upload
    if (this._xhr) {
      this._xhr.abort();
      this._xhr = null;
    }
  }

  // ── Rendering ─────────────────────────────────────────────────────────

  _renderForm() {
    const options = this._sessions.map(
      (s) => `<option value="${escapeHtml(s.name)}">${escapeHtml(s.name)} (${s.entry_count ?? 0} entries)</option>`
    ).join("");

    this.mountHTML(`<article>
      <h2>Upload Files</h2>
      <p class="upload-desc">Upload markdown, text, or JSON files. Files are chunked into entries automatically.</p>

      <div class="upload-zone" id="upload-zone">
        <div class="upload-zone-content">
          <span class="upload-icon">📁</span>
          <p>Drag & drop a file here, or click to browse</p>
          <p class="upload-hint">.md, .txt, .json — max ${formatBytes(4 * 1024 * 1024)}</p>
        </div>
        <input type="file" id="upload-file-input" accept=".md,.txt,.json,.markdown" hidden>
      </div>

      <div class="upload-form-fields">
        <label>
          Target session
          <select class="upload-session-select">
            <option value="">— Select session —</option>
            ${options}
            <option disabled>──────────</option>
            <option value="__new__">+ Create new session…</option>
          </select>
        </label>
        <div class="upload-new-session" hidden>
          <label>
            New session name
            <input type="text" class="upload-session-name" placeholder="my-project" pattern="[a-zA-Z0-9_-]+">
          </label>
        </div>
        <label>
          Tags (comma-separated)
          <input type="text" class="upload-tags" placeholder="docs, api, reference">
        </label>
        <label>
          Priority: <span class="upload-priority-value">5</span>
          <input type="range" class="upload-priority" min="0" max="10" value="5" step="1">
        </label>
      </div>

      <div class="upload-progress" hidden>
        <progress class="upload-progress-bar" value="0" max="100"></progress>
        <p class="upload-progress-text">0%</p>
      </div>

      <div class="upload-result" hidden></div>

      <div class="upload-actions">
        <button class="upload-submit-btn" disabled>Upload</button>
      </div>
    </article>`);
  }

  _renderResult(result) {
    const resultEl = this.root.querySelector(".upload-result");
    if (!resultEl) return;

    resultEl.hidden = false;
    resultEl.innerHTML = `<article class="upload-result-card">
      <h3>✅ Upload complete</h3>
      <dl>
        <dt>File</dt><dd>${escapeHtml(result.file_name || "unknown")}</dd>
        <dt>Entries created</dt><dd>${result.entries_created ?? result.chunks ?? "—"}</dd>
        <dt>Size</dt><dd>${formatBytes(result.file_size || 0)}</dd>
      </dl>
      <a href="#sessions/${escapeHtml(result.session_name || "")}" role="button">Browse entries</a>
    </article>`;
  }

  // ── Events ────────────────────────────────────────────────────────────

  _bindEvents() {
    const zone = this.root.querySelector("#upload-zone");
    const fileInput = this.root.querySelector("#upload-file-input");
    const sessionSelect = this.root.querySelector(".upload-session-select");
    const newSessionDiv = this.root.querySelector(".upload-new-session");
    const priorityRange = this.root.querySelector(".upload-priority");
    const priorityValue = this.root.querySelector(".upload-priority-value");
    const submitBtn = this.root.querySelector(".upload-submit-btn");

    let selectedFile = null;

    // Click zone to open file picker
    if (zone && fileInput) {
      zone.addEventListener("click", () => fileInput.click());

      zone.addEventListener("dragover", (e) => {
        e.preventDefault();
        zone.classList.add("upload-zone-active");
      });
      zone.addEventListener("dragleave", () => {
        zone.classList.remove("upload-zone-active");
      });
      zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.classList.remove("upload-zone-active");
        const files = e.dataTransfer?.files;
        if (files && files.length > 0) {
          selectedFile = files[0];
          this._onFileSelected(selectedFile, zone, submitBtn);
        }
      });
    }

    if (fileInput) {
      fileInput.addEventListener("change", () => {
        selectedFile = fileInput.files?.[0] || null;
        this._onFileSelected(selectedFile, zone, submitBtn);
      });
    }

    // Session selector: show/hide new session input
    if (sessionSelect && newSessionDiv) {
      sessionSelect.addEventListener("change", () => {
        newSessionDiv.hidden = sessionSelect.value !== "__new__";
      });
    }

    // Priority range slider
    if (priorityRange && priorityValue) {
      priorityRange.addEventListener("input", () => {
        priorityValue.textContent = priorityRange.value;
      });
    }

    // Submit button
    if (submitBtn) {
      submitBtn.addEventListener("click", () => this._doUpload(selectedFile));
    }
  }

  _onFileSelected(file, zone, submitBtn) {
    if (!file) return;
    const contentEl = zone.querySelector(".upload-zone-content");
    if (contentEl) {
      contentEl.innerHTML = `
        <span class="upload-icon">📄</span>
        <p><strong>${escapeHtml(file.name)}</strong></p>
        <p class="upload-hint">${formatBytes(file.size)}</p>
      `;
    }
    if (submitBtn) submitBtn.disabled = false;
  }

  async _doUpload(file) {
    if (!file || this._uploading) return;

    const sessionSelect = this.root.querySelector(".upload-session-select");
    const newSessionName = this.root.querySelector(".upload-session-name");
    const tagsInput = this.root.querySelector(".upload-tags");
    const priorityRange = this.root.querySelector(".upload-priority");
    const progressDiv = this.root.querySelector(".upload-progress");
    const progressBar = this.root.querySelector(".upload-progress-bar");
    const progressText = this.root.querySelector(".upload-progress-text");

    let sessionName = sessionSelect?.value;
    if (sessionName === "__new__") {
      sessionName = newSessionName?.value?.trim();
      if (!sessionName) {
        showToast("Please enter a session name", "error");
        return;
      }
    }
    if (!sessionName) {
      showToast("Please select a target session", "error");
      return;
    }

    const tags = tagsInput?.value
      ? tagsInput.value.split(",").map((t) => t.trim()).filter(Boolean)
      : [];
    const priority = parseInt(priorityRange?.value || "5", 10);

    this._uploading = true;
    if (progressDiv) progressDiv.hidden = false;

    // Disable submit
    const submitBtn = this.root.querySelector(".upload-submit-btn");
    if (submitBtn) submitBtn.disabled = true;

    // Create new session if needed
    try {
      if (sessionSelect?.value === "__new__") {
        await api.createSession(sessionName);
        showToast(`Session "${sessionName}" created`, "success");
      }
    } catch (err) {
      showToast(`Failed to create session: ${err.message}`, "error");
      this._uploading = false;
      if (submitBtn) submitBtn.disabled = false;
      return;
    }

    // Build form data
    const formData = new FormData();
    formData.append("file", file);
    formData.append("session", sessionName);
    formData.append("priority", String(priority));
    if (tags.length > 0) {
      formData.append("tags", tags.join(","));
    }

    try {
      const result = await api.uploadFile(formData, (pct) => {
        if (progressBar) progressBar.value = pct;
        if (progressText) progressText.textContent = `${pct}%`;
      });
      this._result = result;
      if (progressDiv) progressDiv.hidden = true;
      if (progressText) progressText.textContent = "100%";
      this._renderResult(result);
      showToast("Upload complete!", "success");
    } catch (err) {
      showToast(`Upload failed: ${err.message}`, "error");
    } finally {
      this._uploading = false;
      if (submitBtn) submitBtn.disabled = false;
    }
  }
}
