"""Serve the static FinPilot developer portal without exposing filesystem paths.

The assets are small, so return buffered responses rather than FileResponse.
This avoids file-response streaming/content-length issues with the application's
HTTP middleware stack while preserving normal content-type and cache headers.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

router = APIRouter(tags=["Developer Portal"])

_PORTAL_DIR = Path(__file__).resolve().parent.parent / "static" / "developer_portal"
_PORTAL_ASSETS = {
    "styles.css": "text/css",
    "app.js": "text/javascript",
}


@router.get("/developer-portal", include_in_schema=False, response_class=HTMLResponse)
def developer_portal_index() -> HTMLResponse:
    """Return the developer portal landing page as a complete HTML response."""
    path = _PORTAL_DIR / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Developer portal page not found")

    return HTMLResponse(
        content=path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/developer-portal/{asset_name}", include_in_schema=False)
def developer_portal_asset(asset_name: str) -> Response:
    """Serve only known static assets, never arbitrary paths from the URL."""
    media_type = _PORTAL_ASSETS.get(asset_name)
    if media_type is None:
        raise HTTPException(status_code=404, detail="Developer portal asset not found")

    path = _PORTAL_DIR / asset_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Developer portal asset not found")

    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type=media_type,
        headers={"Cache-Control": "no-cache"},
    )
