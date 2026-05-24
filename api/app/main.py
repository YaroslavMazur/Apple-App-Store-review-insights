from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp

from app.api.v1.router import router as v1_router
from app.config import Settings, get_settings
from app.exceptions import DomainError
from app.logging import bind_contextvars, clear_contextvars, configure_logging, get_logger
from app.storage.repository import ReviewRepository

REQUEST_ID_HEADER = "X-Request-ID"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    log = get_logger("app")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        repository = ReviewRepository(settings.database_url)
        await repository.initialize()
        app.state.repository = repository
        log.info("app.startup", env=settings.env, log_level=settings.log_level)
        yield
        log.info("app.shutdown")

    app = FastAPI(
        title="Apple Store Review Analysis API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _install_request_id_middleware(app)
    _install_exception_handlers(app)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["meta"])
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    app.include_router(v1_router)
    return app


def _install_request_id_middleware(app: FastAPI) -> None:
    log = get_logger("http")

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[JSONResponse]],
    ) -> JSONResponse:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        bind_contextvars(request_id=request_id, path=request.url.path, method=request.method)
        try:
            log.info("request.start")
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            log.info("request.end", status_code=response.status_code)
            return response
        finally:
            clear_contextvars()


def _install_exception_handlers(app: FastAPI) -> None:
    log = get_logger("error")

    @app.exception_handler(DomainError)
    async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        log.warning("domain.error", code=exc.code, message=exc.message, details=exc.details)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )


app: ASGIApp = create_app()
