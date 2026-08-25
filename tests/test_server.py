"""HTTP-level tests for the static reader and translation proxy."""

from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from pytest import CaptureFixture, MonkeyPatch

from book_viewer import server as server_module
from book_viewer.models import TranslationRequest
from book_viewer.server import create_server, run_server
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


class InterruptingServer:
    def __init__(self, address: tuple[str, int], books_root: Path, book_count: int) -> None:
        self.server_address = address
        self.books_root = books_root
        self.catalog_book_count = book_count
        self.closed = False

    def serve_forever(self) -> None:
        raise KeyboardInterrupt

    def server_close(self) -> None:
        self.closed = True


@contextmanager
def running_server(
    tmp_path: Path,
    translator: FakeTranslator | FailingTranslator | None,
    *,
    static_root: Path | None = None,
    books_root: Path | None = None,
) -> Generator[tuple[str, int]]:
    selected_static_root = static_root or tmp_path
    selected_static_root.mkdir(parents=True, exist_ok=True)
    index_path = selected_static_root / "index.html"
    if not index_path.exists():
        index_path.write_text("<h1>Reader</h1>", encoding="utf-8")
    settings = ServerSettings(
        host="127.0.0.1",
        port=0,
        static_root=selected_static_root,
        books_root=books_root or tmp_path / "books",
        reader_data_path=tmp_path / "reader-data.sqlite3",
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


def get_text(host: str, port: int, path: str) -> tuple[int, str, dict[str, str]]:
    connection = http.client.HTTPConnection(host, port, timeout=2)
    connection.request("GET", path)
    response = connection.getresponse()
    status = response.status
    body = response.read().decode()
    headers = dict(response.getheaders())
    connection.close()
    return status, body, headers


def valid_payload() -> dict[str, object]:
    return {
        "sentence": "これは文です。",
        "before": ["前です。"],
        "after": ["次です。"],
        "source_language": "Japanese",
        "target_language": "English",
    }


def write_built_book(books_root: Path, slug: str) -> None:
    book_root = books_root / slug
    book_root.mkdir(parents=True)
    (book_root / "source.md").write_text("Source.", encoding="utf-8")
    (book_root / "target.md").write_text("Target.", encoding="utf-8")
    (book_root / "document-data.js").write_text("window.DATA = {};\n", encoding="utf-8")
    (book_root / "book.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "slug": slug,
                "title": f"Title {slug}",
                "reader_title": f"Reader {slug}",
                "description": "A sample.",
                "source": {
                    "language": "Japanese",
                    "label": "Japanese",
                    "html_lang": "ja",
                    "markdown": "source.md",
                    "html_id_prefix": "source",
                },
                "target": {
                    "language": "English",
                    "label": "English",
                    "html_lang": "en",
                    "markdown": "target.md",
                    "html_id_prefix": "target",
                },
            }
        ),
        encoding="utf-8",
    )


def test_server_requires_existing_static_root(tmp_path: Path) -> None:
    settings = ServerSettings(static_root=tmp_path / "missing", port=0)
    with pytest.raises(FileNotFoundError, match="static root"):
        create_server(settings)


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
        status, body, headers = get_text(host, port, "/")

    assert status == 200
    assert body == "<h1>Reader</h1>"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["X-Frame-Options"] == "SAMEORIGIN"


def test_server_serves_external_books_from_a_separate_root(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    books_root = tmp_path / "library"
    static_root.mkdir()
    example_root = books_root / "example"
    example_root.mkdir(parents=True)
    (static_root / "index.html").write_text("Viewer", encoding="utf-8")
    (example_root / "asset.txt").write_text("Book asset", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("Secret", encoding="utf-8")
    with running_server(
        tmp_path,
        FakeTranslator(),
        static_root=static_root,
        books_root=books_root,
    ) as (host, port):
        status, body, _headers = get_text(host, port, "/books/example/asset.txt")
        traversal_status, _traversal_body, _traversal_headers = get_text(
            host, port, "/books/%2e%2e/secret.txt"
        )

    assert status == 200
    assert body == "Book asset"
    assert traversal_status == 404


def test_server_falls_back_to_tracked_example_catalog(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    books_root = tmp_path / "books"
    static_root.mkdir()
    example_dir = books_root / "example"
    example_dir.mkdir(parents=True)
    (static_root / "index.html").write_text("Viewer", encoding="utf-8")
    (books_root / "catalog.js").write_text("Stale root catalog", encoding="utf-8")
    (example_dir / "catalog.js").write_text("Example catalog", encoding="utf-8")
    with running_server(
        tmp_path,
        FakeTranslator(),
        static_root=static_root,
        books_root=books_root,
    ) as (host, port):
        status, body, _headers = get_text(host, port, "/books/catalog.js")

    assert status == 200
    assert body == "Example catalog"


def test_server_refreshes_catalog_without_restart_or_generated_root_file(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    books_root = tmp_path / "books"
    static_root.mkdir()
    (static_root / "index.html").write_text("Viewer", encoding="utf-8")
    write_built_book(books_root, "sample-book")
    with running_server(
        tmp_path,
        FakeTranslator(),
        static_root=static_root,
        books_root=books_root,
    ) as (host, port):
        first_status, first_body, _first_headers = get_text(host, port, "/books/catalog.js")

        write_built_book(books_root, "new-book")
        refreshed_status, refreshed_body, _refreshed_headers = get_text(
            host, port, "/books/catalog.js"
        )

    assert first_status == 200
    assert '"sample-book"' in first_body
    assert '"new-book"' not in first_body
    assert refreshed_status == 200
    assert '"sample-book"' in refreshed_body
    assert '"new-book"' in refreshed_body
    assert not (books_root / "catalog.js").exists()


def test_server_persists_reading_state_across_restarts(tmp_path: Path) -> None:
    update = {
        "bookSlug": "sample-book",
        "chapterId": "chapter-2",
        "segmentId": "segment-14",
        "progressPercent": 42,
        "sourceScrollTop": 750,
        "targetScrollTop": 810,
        "lastOpenedAt": 1_000,
        "updatedAt": 1_100,
    }
    with running_server(tmp_path, FakeTranslator()) as (host, port):
        status, saved = post_json(host, port, "/api/reading-states", update)

    assert status == 200
    assert saved == update

    with running_server(tmp_path, FakeTranslator()) as (host, port):
        status, body, _headers = get_text(host, port, "/api/reading-states")

    assert status == 200
    assert json.loads(body) == {"states": [update]}


def test_server_rejects_invalid_reading_state(tmp_path: Path) -> None:
    with running_server(tmp_path, FakeTranslator()) as (host, port):
        status, response = post_json(
            host,
            port,
            "/api/reading-states",
            {
                "bookSlug": "sample-book",
                "progressPercent": 101,
                "updatedAt": 1_100,
            },
        )

    assert status == 400
    assert "reading-state schema" in str(response["error"])


def test_run_server_opens_browser_after_binding(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    fake_server = InterruptingServer(("0.0.0.0", 8765), tmp_path / "books", 2)
    opened_urls: list[str] = []

    def fake_create_server(_settings: ServerSettings | None) -> InterruptingServer:
        return fake_server

    def record_opened_url(url: str) -> bool:
        opened_urls.append(url)
        return True

    monkeypatch.setattr(server_module, "create_server", fake_create_server)

    assert run_server(browser_opener=record_opened_url) == 0

    assert opened_urls == ["http://127.0.0.1:8765"]
    assert fake_server.closed is True
    assert "Found 2 built books" in capsys.readouterr().out


def test_run_server_can_skip_browser(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_server = InterruptingServer(("127.0.0.1", 8000), tmp_path / "books", 0)

    def fake_create_server(_settings: ServerSettings | None) -> InterruptingServer:
        return fake_server

    monkeypatch.setattr(server_module, "create_server", fake_create_server)

    def unexpected_opener(_url: str) -> bool:
        raise AssertionError("browser opener should not be called")

    assert run_server(open_browser=False, browser_opener=unexpected_opener) == 0
