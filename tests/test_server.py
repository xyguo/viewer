"""HTTP-level tests for the static reader and translation proxy."""

from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from book_viewer.models import TranslationRequest
from book_viewer.server import BookViewerHTTPServer, create_server
from book_viewer.settings import ServerSettings
from book_viewer.translation import TranslationError


class FakeTranslator:
    def __init__(self, result: str = "Translated.") -> None:
        self.result = result
        self.requests: list[TranslationRequest] = []

    def translate(self, request: TranslationRequest) -> str:
        self.requests.append(request)
        return self.result


class FailingTranslator:
    def translate(self, request: TranslationRequest) -> str:
        del request
        raise TranslationError("Backend unavailable.")


@contextmanager
def running_server(
    tmp_path: Path,
    translator: FakeTranslator | FailingTranslator | None,
) -> Generator[tuple[str, int]]:
    (tmp_path / "index.html").write_text("<h1>Reader</h1>", encoding="utf-8")
    settings = ServerSettings(host="127.0.0.1", port=0, static_root=tmp_path)
    server = create_server(settings, translator=translator)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield str(host), int(port)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def post_json(host: str, port: int, path: str, payload: object) -> tuple[int, dict[str, object]]:
    connection = http.client.HTTPConnection(host, port, timeout=2)
    connection.request(
        "POST",
        path,
        body=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    status = response.status
    body = json.loads(response.read())
    connection.close()
    return status, body


def valid_payload() -> dict[str, object]:
    return {
        "sentence": "これは文です。",
        "before": ["前です。"],
        "after": ["次です。"],
        "source_language": "Japanese",
        "target_language": "English",
    }


def test_server_translates_and_caches_identical_requests(tmp_path: Path) -> None:
    translator = FakeTranslator()
    with running_server(tmp_path, translator) as (host, port):
        first_status, first = post_json(host, port, "/api/translate", valid_payload())
        second_status, second = post_json(host, port, "/api/translate", valid_payload())

    assert first_status == 200
    assert second_status == 200
    assert first == second == {"translation": "Translated."}
    assert len(translator.requests) == 1


def test_server_rejects_unknown_endpoint_and_invalid_schema(tmp_path: Path) -> None:
    translator = FakeTranslator()
    with running_server(tmp_path, translator) as (host, port):
        missing_status, missing = post_json(host, port, "/api/missing", valid_payload())
        invalid_status, invalid = post_json(host, port, "/api/translate", {"sentence": 4})

    assert missing_status == 404
    assert missing == {"error": "Endpoint not found."}
    assert invalid_status == 400
    assert "translation schema" in str(invalid["error"])
    assert translator.requests == []


def test_server_returns_safe_backend_error(tmp_path: Path) -> None:
    with running_server(tmp_path, FailingTranslator()) as (host, port):
        status, payload = post_json(host, port, "/api/translate", valid_payload())
    assert status == 502
    assert payload == {"error": "Backend unavailable."}


def test_server_reports_unconfigured_live_translation(tmp_path: Path) -> None:
    with running_server(tmp_path, None) as (host, port):
        status, payload = post_json(host, port, "/api/translate", valid_payload())
    assert status == 503
    assert "LLM_CHAT_COMPLETIONS_URL" in str(payload["error"])


def test_server_serves_static_files_with_security_headers(tmp_path: Path) -> None:
    with running_server(tmp_path, FakeTranslator()) as (host, port):
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read().decode()
        headers = dict(response.getheaders())
        connection.close()

    assert response.status == 200
    assert body == "<h1>Reader</h1>"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["X-Frame-Options"] == "SAMEORIGIN"


def test_server_type_is_explicit(tmp_path: Path) -> None:
    server = create_server(ServerSettings(static_root=tmp_path, port=0))
    try:
        assert isinstance(server, BookViewerHTTPServer)
    finally:
        server.server_close()
