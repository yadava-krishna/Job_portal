"""FastAPI application factory. Run: uvicorn backend.main:app"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse

from backend.api.deps import is_local_request
from backend.api.routes import applications, auth, health, jobs, profile, reports
from backend.config import VERSION, get_settings
from backend.db import Base, get_engine, init_engine
from backend.services.scheduler_service import get_scheduler
from core import timeutil
from core.logging_setup import redact, setup_logging

log = logging.getLogger("backend")
API_PREFIX = "/api/v1"


def create_app(*, start_scheduler: bool = True) -> FastAPI:
    settings = get_settings()
    timeutil.set_timezone(settings.timezone)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        setup_logging(settings.storage_dir / "logs", "INFO")
        init_engine(settings.database_url)
        if settings.is_sqlite:
            # Local development and tests only; PostgreSQL schema is managed by Alembic migrations.
            Base.metadata.create_all(get_engine())
        if start_scheduler:
            get_scheduler(settings).start()
        log.info("JobPilot backend %s started (%s)", VERSION, settings.environment)
        yield
        get_scheduler(settings).shutdown()

    app = FastAPI(
        title="JobPilot API", version=VERSION, lifespan=lifespan,
        description="Multi-user job discovery, matching and application tracking. "
                    "Uses only permitted sources; applications are always submitted by the user on the original platform.",
        # Docs routes are registered below so access can depend on DOCS_MODE and the caller.
        docs_url=None, openapi_url=None, redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,  # bearer tokens, no cookies
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "ngrok-skip-browser-warning"],
        expose_headers=["Content-Disposition", "Retry-After"],
        max_age=600,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith(API_PREFIX) and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": "Validation failed", "errors": errors})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.error("Unhandled error on %s %s: %s", request.method, request.url.path, redact(repr(exc)), exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    for r in (health.router, auth.router, profile.router, jobs.router, applications.router, reports.router):
        app.include_router(r, prefix=API_PREFIX)

    def docs_allowed(request: Request) -> bool:
        mode = settings.docs_mode
        return mode == "public" or (mode == "local" and is_local_request(request, settings))

    @app.get(f"{API_PREFIX}/openapi.json", include_in_schema=False)
    def openapi_schema(request: Request):
        if not docs_allowed(request):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        return JSONResponse(app.openapi())

    @app.get(f"{API_PREFIX}/docs", include_in_schema=False)
    def swagger_ui(request: Request):
        if not docs_allowed(request):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        return get_swagger_ui_html(openapi_url=f"{API_PREFIX}/openapi.json", title="JobPilot API")

    @app.get("/", include_in_schema=False)
    def root(request: Request):
        body = {"service": "jobpilot-backend", "health": f"{API_PREFIX}/health"}
        if docs_allowed(request):
            body["docs"] = f"{API_PREFIX}/docs"
        return body

    return app


app = create_app()
