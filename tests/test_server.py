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
    settings = ServerSettings(
        host="127.0.0.1",
        port=0,
        static_root=tmp_path,
        books_root=tmp_path / "books",
        chat_completions_url=None,
        chat_model=None,
    )
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


def test_server_caches_live_translations_per_target_language(tmp_path: Path) -> None:
    translator = FakeTranslator()
    french_payload = {**valid_payload(), "target_language": "French"}
    with running_server(tmp_path, translator) as (host, port):
        english_status, _english = post_json(host, port, "/api/translate", valid_payload())
        french_status, _french = post_json(host, port, "/api/translate", french_payload)

    assert english_status == 200
    assert french_status == 200
    assert [request.target_language for request in translator.requests] == ["English", "French"]


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


def test_server_rejects_unsupported_live_target_language(tmp_path: Path) -> None:
    translator = FakeTranslator()
    invalid_payload = {**valid_payload(), "target_language": "Klingon"}
    with running_server(tmp_path, translator) as (host, port):
        status, response = post_json(host, port, "/api/translate", invalid_payload)

    assert status == 400
    assert "translation schema" in str(response["error"])
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


def test_server_serves_external_books_from_a_separate_root(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    books_root = tmp_path / "library"
    static_root.mkdir()
    books_root.mkdir()
    (static_root / "index.html").write_text("Viewer", encoding="utf-8")
    (books_root / "catalog.js").write_text("Catalog", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("Secret", encoding="utf-8")
    settings = ServerSettings(
        host="127.0.0.1",
        port=0,
        static_root=static_root,
        books_root=books_root,
    )
    server = create_server(settings, translator=FakeTranslator())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        connection = http.client.HTTPConnection(str(host), int(port), timeout=2)
        connection.request("GET", "/books/catalog.js")
        response = connection.getresponse()
        body = response.read().decode()
        connection.request("GET", "/books/%2e%2e/secret.txt")
        traversal_response = connection.getresponse()
        traversal_response.read()
        connection.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert response.status == 200
    assert body == "Catalog"
    assert traversal_response.status == 404


def test_server_falls_back_to_tracked_example_catalog(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    books_root = tmp_path / "books"
    static_root.mkdir()
    example_dir = books_root / "example"
    example_dir.mkdir(parents=True)
    (static_root / "index.html").write_text("Viewer", encoding="utf-8")
    (example_dir / "catalog.js").write_text("Example catalog", encoding="utf-8")
    settings = ServerSettings(
        host="127.0.0.1",
        port=0,
        static_root=static_root,
        books_root=books_root,
    )
    server = create_server(settings, translator=FakeTranslator())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        connection = http.client.HTTPConnection(str(host), int(port), timeout=2)
        connection.request("GET", "/books/catalog.js")
        response = connection.getresponse()
        body = response.read().decode()
        connection.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert response.status == 200
    assert body == "Example catalog"


def test_server_type_is_explicit(tmp_path: Path) -> None:
    server = create_server(ServerSettings(static_root=tmp_path, port=0))
    try:
        assert isinstance(server, BookViewerHTTPServer)
    finally:
        server.server_close()
