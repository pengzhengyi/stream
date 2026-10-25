"""A short link is followed only to Bilibili's hosts, and never fetched as pasted."""

import http.server
import threading
from collections.abc import Iterator

import pytest

from medleyplay.plugin_api import NetworkError
from medleyplay.plugins.bilibili.short_links import fetch_redirect, follow_short_link

VIDEO = "https://www.bilibili.com/video/BV1Xx41117Tz?p=2"


class Redirects:
    """A stand-in for the web: each URL redirects as the test says, and asked URLs are kept."""

    def __init__(self, routes: dict[str, str | None]) -> None:
        self.routes = routes
        self.asked: list[str] = []

    def __call__(self, url: str) -> str | None:
        self.asked.append(url)
        return self.routes.get(url)


def test_a_short_link_leads_to_its_video() -> None:
    web = Redirects({"https://b23.tv/abc123": VIDEO})

    assert follow_short_link("https://b23.tv/abc123", web) == VIDEO
    assert web.asked == ["https://b23.tv/abc123"]


def test_the_first_request_is_rebuilt_from_the_code_alone() -> None:
    web = Redirects({"https://b23.tv/abc123": VIDEO})

    follow_short_link("http://B23.tv/abc123?evil=1#frag", web)

    assert web.asked == ["https://b23.tv/abc123"]


def test_a_redirect_off_bilibili_is_returned_without_being_fetched() -> None:
    web = Redirects({"https://b23.tv/abc123": "https://evil.example/x"})

    assert follow_short_link("https://b23.tv/abc123", web) == "https://evil.example/x"
    assert web.asked == ["https://b23.tv/abc123"]


@pytest.mark.parametrize(
    "target",
    ["https://b23.tv:8080/x", "https://user@b23.tv/x", "ftp://b23.tv/x", "file:///etc/passwd"],
)
def test_a_redirect_to_a_port_a_user_or_another_scheme_is_never_fetched(target: str) -> None:
    web = Redirects({"https://b23.tv/abc123": target})

    follow_short_link("https://b23.tv/abc123", web)

    assert web.asked == ["https://b23.tv/abc123"]


def test_short_links_are_followed_through_at_most_three_hops() -> None:
    web = Redirects({f"https://b23.tv/a{n}": f"https://b23.tv/a{n + 1}" for n in range(10)})

    assert follow_short_link("https://b23.tv/a0", web) == "https://b23.tv/a3"
    assert len(web.asked) == 3


def test_a_relative_redirect_is_resolved_against_the_short_link() -> None:
    web = Redirects({"https://b23.tv/abc123": "/def456", "https://b23.tv/def456": VIDEO})

    assert follow_short_link("https://b23.tv/abc123", web) == VIDEO


@pytest.mark.parametrize("link", ["https://b23.tv/", "https://b23.tv/a/b", "https://b23.tv/%2e%2e"])
def test_a_short_link_without_a_code_leads_nowhere(link: str) -> None:
    web = Redirects({})

    assert follow_short_link(link, web) == link
    assert web.asked == []


def test_a_short_link_that_doesnt_redirect_names_itself() -> None:
    assert follow_short_link("https://b23.tv/abc123", Redirects({})) == "https://b23.tv/abc123"


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/moved":
            self.send_response(302)
            self.send_header("Location", VIDEO)
        elif self.path == "/broken":
            self.send_response(503)
        else:
            self.send_response(200)
        self.end_headers()

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture
def server() -> Iterator[str]:
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_fetching_reads_the_redirect_without_following_it(server: str) -> None:
    assert fetch_redirect(f"{server}/moved") == VIDEO


def test_fetching_a_page_that_doesnt_redirect_answers_none(server: str) -> None:
    assert fetch_redirect(f"{server}/page") is None


def test_a_server_error_or_no_server_is_a_network_failure(server: str) -> None:
    with pytest.raises(NetworkError):
        fetch_redirect(f"{server}/broken")
    with pytest.raises(NetworkError):
        fetch_redirect("http://127.0.0.1:9/")
