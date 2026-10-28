"""FastAPI application entry point."""

from html import escape

from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.health import router as health_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.fdrs import router as fdr_router
from app.api.institutions import router as institution_router
from app.api.documents import router as document_router
from app.api.integrity import router as integrity_router
from app.api.dashboard import router as dashboard_router
from app.api.notifications import router as notifications_router
from app.api.reports import router as reports_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler, http_error_handler, validation_error_handler

settings = get_settings()

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(audit_router, prefix=settings.api_v1_prefix)
app.include_router(fdr_router, prefix=settings.api_v1_prefix)
app.include_router(institution_router, prefix=settings.api_v1_prefix)
app.include_router(document_router, prefix=settings.api_v1_prefix)
app.include_router(integrity_router, prefix=settings.api_v1_prefix)
app.include_router(dashboard_router, prefix=settings.api_v1_prefix)
app.include_router(notifications_router, prefix=settings.api_v1_prefix)
app.include_router(reports_router, prefix=settings.api_v1_prefix)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root() -> str:
    """Show a small local landing page with useful API links."""
    safe_app_name = escape(settings.app_name)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_app_name}</title>
    <link rel="icon" href="/favicon.ico">
  </head>
  <body>
    <main>
      <h1>{safe_app_name}</h1>
      <p>The local API is running.</p>
      <ul>
        <li><a href="/docs">Interactive API documentation</a></li>
        <li><a href="{settings.api_v1_prefix}/health">API and database health</a></li>
      </ul>
    </main>
  </body>
</html>"""


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Return a tiny SVG mark so browsers do not receive a missing-icon 404."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="12" fill="#123b66"/>
<path d="M18 14h28v8H27v8h16v8H27v12h-9z" fill="#fff"/>
<circle cx="46" cy="45" r="7" fill="#56c3a5"/>
</svg>"""
    return Response(content=svg, media_type="image/svg+xml")
