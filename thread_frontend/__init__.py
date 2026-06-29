"""Frontend blueprint — serves the SPA shell and static assets.

Routes:
  GET /dashboard/              → index.html
  GET /dashboard/<path:subpath> → index.html (SPA client-side routing)
  GET /dashboard/static/<path:filename> → static asset (CSS, JS, vendor, img)

All /dashboard/* HTML requests return the same index.html — the SPA's
hash router handles client-side rendering. Static assets are served
through Flask's static file machinery.
"""

from flask import Blueprint, render_template

frontend_bp = Blueprint(
    "frontend",
    __name__,
    url_prefix="/dashboard",
)


@frontend_bp.route("/")
@frontend_bp.route("/<path:subpath>")
def serve_spa(subpath: str | None = None) -> str:
    """Serve the SPA shell for all /dashboard/* HTML requests.

    The hash router (router.js) reads `window.location.hash` and mounts
    the matching view into `#app-root`. Returning index.html for every
    subpath makes bookmarkable hash URLs work on page refresh.
    """
    return render_template("index.html")
