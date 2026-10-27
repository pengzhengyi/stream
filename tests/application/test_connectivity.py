"""The connectivity check: whether an endpoint answers exactly what it promises."""

import threading
import time
from collections.abc import Iterator, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from medleyplay.application.connectivity import APPLE_SUCCESS, Check, reachable

type Answer = tuple[int, str, Mapping[str, str]]


def endpoints() -> dict[str, Answer]:
    """What the local server answers at each path: an honest endpoint and a captive portal's."""
    return {
        "/hotspot-detect.html": (200, APPLE_SUCCESS + "\n", {}),
        "/generate_204": (204, "", {}),
        "/portal-page": (200, "<html>Sign in to the cafe's Wi-Fi</html>", {}),
        "/portal-redirect": (302, "", {"Location": "http://portal.example/login"}),
        "/broken": (500, "", {}),
    }


@pytest.fixture
def server() -> Iterator[str]:
    answers = endpoints()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/slow":
                time.sleep(1)
            if self.path == "/garbage":
                self.wfile.write(b"NOT HTTP AT ALL\r\n\r\n")
                return
            status, body, headers = answers.get(self.path, (404, "", {}))
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            if body:
                self.wfile.write(body.encode())

        def log_message(self, *_: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def test_reaches_an_endpoint_that_answers_its_promised_body(server: str) -> None:
    assert reachable([Check(f"{server}/hotspot-detect.html", 200, APPLE_SUCCESS)])


def test_reaches_an_endpoint_that_promises_only_a_status(server: str) -> None:
    assert reachable([Check(f"{server}/generate_204", 204)])


@pytest.mark.parametrize(
    "path", ["/portal-page", "/portal-redirect", "/broken", "/missing", "/garbage"]
)
def test_a_captive_portal_or_another_answer_is_unreachable(server: str, path: str) -> None:
    assert not reachable([Check(f"{server}{path}", 200, APPLE_SUCCESS)])


def test_tries_the_next_endpoint_when_one_cant_be_reached(server: str) -> None:
    checks = [Check("http://127.0.0.1:9/hotspot-detect.html", 200, APPLE_SUCCESS)]
    checks.append(Check(f"{server}/generate_204", 204))

    assert reachable(checks)


def test_an_endpoint_slower_than_the_timeout_is_unreachable(server: str) -> None:
    assert not reachable([Check(f"{server}/slow", 404)], timeout=0.2)
