/**
 * View index — barrel file that re-exports all view classes.
 *
 * Each view file exports its class. This file bundles them into a single
 * `views` namespace for the router to consume.
 */

import { BaseView } from "./base.js";
import { LoginView } from "./login.js";
import { DashboardView } from "./dashboard.js";

// Feature views — each lives in its own folder
import { SearchView } from "./search/search.js";
import { UploadView } from "./upload/upload.js";
import { SettingsView } from "./settings/settings.js";

// Session-scoped views
import { BrowserView } from "./sessions/browser.js";
import { HistoryView } from "./sessions/history.js";
import { GraphView } from "./sessions/graph.js";

export { BaseView };

export const views = {
  DashboardView,
  BrowserView,
  SearchView,
  UploadView,
  HistoryView,
  GraphView,
  SettingsView,
  LoginView,
};
