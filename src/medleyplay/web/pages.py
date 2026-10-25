"""Serving the web client: its page at every path outside `/api`, and its hashed assets.

`npm run build` in `web/` writes the client into the `client` folder beside this
module, so the package carries it.
"""

from pathlib import Path
from typing import Final, override

from fastapi import status
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

CLIENT_DIR: Final = Path(__file__).parent / "client"
NOT_BUILT: Final = """<!doctype html>
<title>medleyplay</title>
<p>The web client isn't built. Run <code>npm ci &amp;&amp; npm run build</code> in
<code>web/</code>, then restart the server. The API is at <a href="/docs">/docs</a>.</p>
"""
_PAGE: Final = "index.html"
_ASSETS: Final = "assets/"


class ClientFiles(StaticFiles):
    """The client's files; any other path outside `/api` answers the page.

    The page is revalidated on every load, so a new build shows at once; the
    assets' names change with their content, so a browser keeps them for good.
    """

    def __init__(self, directory: Path) -> None:
        """Serve the client built into `directory`."""
        super().__init__(directory=directory, html=True)

    @override
    async def get_response(self, path: str, scope: Scope) -> Response:
        if _is_api(path):
            return _no_route()
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            # A missing asset stays missing; any other path is a view of the page.
            if error.status_code != status.HTTP_404_NOT_FOUND or path.startswith(_ASSETS):
                raise
            response = await super().get_response(_PAGE, scope)
        if path.startswith(_ASSETS) and response.status_code == status.HTTP_200_OK:
            response.headers["cache-control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["cache-control"] = "no-cache"
        return response


def client_app(directory: Path) -> ASGIApp:
    """Return what serves the client in `directory`, or a page saying how to build it."""
    if (directory / _PAGE).is_file():
        return ClientFiles(directory)
    return _not_built


async def _not_built(scope: Scope, receive: Receive, send: Send) -> None:
    path = str(scope["path"]).removeprefix("/")
    response = _no_route() if _is_api(path) else HTMLResponse(NOT_BUILT)
    await response(scope, receive, send)


def _is_api(path: str) -> bool:
    # An API path no route matched is the API's own 404, never the page.
    return path == "api" or path.startswith("api/")


def _no_route() -> Response:
    return JSONResponse({"detail": "Not Found"}, status_code=status.HTTP_404_NOT_FOUND)
