"""The FastAPI app: its routers, domain errors as HTTP statuses, and the Host and Origin checks."""

from collections.abc import Awaitable, Callable, Iterable
from contextlib import AbstractAsyncContextManager
from typing import Final
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from medleyplay import __version__
from medleyplay.domain.errors import (
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    MedleyplayError,
    NotFoundError,
    NotSignedInError,
    PluginCallError,
    PluginUnavailableError,
    SignInRefusedError,
    SignInThrottledError,
)
from medleyplay.web import accounts, catalog, jobs, plugins
from medleyplay.web.deps import Services

_STATUS_OF: Final[tuple[tuple[type[MedleyplayError], int], ...]] = (
    (InvalidInputError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (ForbiddenError, status.HTTP_403_FORBIDDEN),
    (NotSignedInError, status.HTTP_401_UNAUTHORIZED),
    (SignInRefusedError, status.HTTP_401_UNAUTHORIZED),
    (SignInThrottledError, status.HTTP_429_TOO_MANY_REQUESTS),
    (PluginUnavailableError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (PluginCallError, status.HTTP_502_BAD_GATEWAY),
)
_DETAIL_OF: Final[dict[type[MedleyplayError], str]] = {
    NotSignedInError: "Sign in first.",
    SignInRefusedError: "The username or password is wrong.",
}
_SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS"})

type Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_app(
    services: Services, allowed_hosts: Iterable[str], *, lifespan: Lifespan | None = None
) -> FastAPI:
    """Return the app serving `services`, answering only requests addressed to `allowed_hosts`.

    Checking the Host header blocks DNS rebinding; checking a state-changing
    request's Origin against its Host blocks other sites' pages from using a
    signed-in browser.
    """
    app = FastAPI(title="medleyplay", version=__version__, lifespan=lifespan)
    app.state.services = services
    app.include_router(accounts.router)
    app.include_router(catalog.router)
    app.include_router(plugins.router)
    app.include_router(jobs.router)
    app.add_exception_handler(MedleyplayError, _handle_domain_error)  # type: ignore[arg-type] # Starlette types handlers for any Exception
    app.middleware("http")(_refuse_cross_origin_writes)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    return app


def _handle_domain_error(_: Request, error: MedleyplayError) -> JSONResponse:
    code = next(code for kind, code in _STATUS_OF if isinstance(error, kind))
    detail = _DETAIL_OF.get(type(error), str(error))
    headers = (
        {"Retry-After": str(error.retry_after_seconds)}
        if isinstance(error, SignInThrottledError)
        else None
    )
    return JSONResponse({"detail": detail}, status_code=code, headers=headers)


async def _refuse_cross_origin_writes(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    origin = request.headers.get("origin")
    if request.method in _SAFE_METHODS or origin is None:
        return await call_next(request)
    if urlsplit(origin).netloc != request.headers.get("host"):
        return JSONResponse(
            {"detail": "Cross-site requests are refused."},
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return await call_next(request)
