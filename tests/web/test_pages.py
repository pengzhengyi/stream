"""The web client: its page at every path outside `/api`, its assets, and a hint before a build."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from medleyplay.application.accounts import AccountService
from medleyplay.application.catalog import CatalogService
from medleyplay.application.jobs import JobService
from medleyplay.application.libraries import LibraryService
from medleyplay.application.playback import PlaybackService
from medleyplay.application.plugins import PluginService
from medleyplay.web.app import create_app
from medleyplay.web.deps import Services
from tests.conftest import TEST_HOST

PAGE = "<!doctype html><title>medleyplay</title>"


def _built(folder: Path) -> Path:
    """A built client: `index.html`, and `assets/index-1a2b.js`."""
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text(PAGE)
    (folder / "assets" / "index-1a2b.js").write_text("console.log('hi')")
    return folder


@pytest.fixture
def pages(
    accounts: AccountService,
    catalog: CatalogService,
    plugins: PluginService,
    jobs: JobService,
    libraries: LibraryService,
    playback: PlaybackService,
    tmp_path: Path,
) -> TestClient:
    """A client of a server whose web client is built."""
    services = Services(accounts, catalog, plugins, jobs, libraries, playback)
    app = create_app(services, [TEST_HOST], client_dir=_built(tmp_path / "built"))
    return TestClient(app, base_url=f"http://{TEST_HOST}")


@pytest.mark.parametrize("path", ["/", "/index.html", "/queue", "/tracks/7"])
def test_every_path_outside_the_api_answers_the_page_revalidated(
    pages: TestClient, path: str
) -> None:
    response = pages.get(path)

    assert (response.status_code, response.text) == (200, PAGE)
    assert response.headers["cache-control"] == "no-cache"


def test_an_asset_is_kept_for_good(pages: TestClient) -> None:
    response = pages.get("/assets/index-1a2b.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_a_missing_asset_is_not_found(pages: TestClient) -> None:
    assert pages.get("/assets/index-old.js").status_code == 404


@pytest.mark.parametrize("path", ["/api", "/api/nothing-here"])
def test_an_api_path_no_route_matches_answers_a_json_404(pages: TestClient, path: str) -> None:
    response = pages.get(path)

    assert (response.status_code, response.json()) == (404, {"detail": "Not Found"})


def test_the_api_still_answers_its_own_routes(pages: TestClient) -> None:
    assert pages.get("/api/tracks").status_code == 401


def test_a_server_without_a_built_client_says_how_to_build_it(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "npm run build" in response.text


def test_a_server_without_a_built_client_still_answers_api_misses_as_json(
    client: TestClient,
) -> None:
    assert client.get("/api/nothing-here").json() == {"detail": "Not Found"}
