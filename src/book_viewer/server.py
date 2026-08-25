"""Serve the static reader and same-origin local translation proxy."""

from __future__ import annotations

import functools
import hashlib
import ipaddress
import logging
import posixpath
import urllib.parse
import webbrowser
from collections.abc import Callable
from contextlib import suppress
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TypeVar, cast

from pydantic import BaseModel, ValidationError

from .config_file import ConfigSettingsStore, SettingsStoreError
from .library import create_catalog, serialize_catalog
from .models import (
    ErrorResponse,
    ReadingStateCollection,
    ReadingStateUpdate,
    SettingsUpdate,
    TranslationRequest,
    TranslationResponse,
)
from .reader_data import ReaderDataStore
from .settings import ServerSettings, load_server_settings
from .translation import (
    OpenAICompatibleTranslator,
    TranslationCache,
    TranslationError,
    Translator,
    UnconfiguredTranslator,
)

MAX_REQUEST_BYTES = 64 * 1024
READING_STATES_ENDPOINT = "/api/reading-states"
SETTINGS_ENDPOINT = "/api/settings"
ModelT = TypeVar("ModelT", bound=BaseModel)


class ClientRequestError(Exception):
    """An invalid HTTP request with a safe client-facing explanation."""

    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


class BookViewerHTTPServer(ThreadingHTTPServer):
    """Threaded server carrying immutable runtime collaborators for handlers."""

    def __init__(
        self,
        settings: ServerSettings,
        translator: Translator | None = None,
        reader_data_store: ReaderDataStore | None = None,
        settings_store: ConfigSettingsStore | None = None,
    ) -> None:
        static_root = settings.static_root.resolve()
        if not static_root.is_dir():
            raise FileNotFoundError(f"Viewer static root does not exist: {static_root}")
        self.settings = settings
        self.books_root = settings.books_root.resolve()
        self.reader_data_store = reader_data_store or ReaderDataStore(settings.reader_data_path)
        self.settings_store = settings_store or ConfigSettingsStore(settings.config_path)
        catalog = create_catalog(self.books_root)
        self.catalog_book_count = 0 if catalog is None else len(catalog.books)
        if translator is not None:
            self.translator = translator
        elif settings.translation_backend_configured:
            self.translator = OpenAICompatibleTranslator(settings)
        else:
            self.translator = UnconfiguredTranslator()
        self.translation_cache = TranslationCache(settings.translation_cache_items)
        handler = functools.partial(ReaderHandler, directory=str(static_root))
        super().__init__((settings.host, settings.port), handler)


class ReaderHandler(SimpleHTTPRequestHandler):
    """Generic static-file handler with one validated translation endpoint."""

    server_version = "ParallelBookViewer/1.0"

    @property
    def viewer_server(self) -> BookViewerHTTPServer:
        return cast(BookViewerHTTPServer, self.server)

    def translate_path(self, path: str) -> str:
        request_path = urllib.parse.urlsplit(path).path
        if request_path == "/books" or request_path.startswith("/books/"):
            relative_path = (
                "/example/catalog.js"
                if request_path == "/books/catalog.js"
                else request_path.removeprefix("/books")
            )
            resolved_path = _resolve_static_path(self.viewer_server.books_root, relative_path)
            return str(resolved_path)
        return super().translate_path(path)

    def do_GET(self) -> None:
        request_path = urllib.parse.urlsplit(self.path).path
        if request_path == SETTINGS_ENDPOINT:
            if not self._settings_request_is_local():
                self._send_json(
                    ErrorResponse(error="Settings are available only on this device."),
                    HTTPStatus.FORBIDDEN,
                )
                return
            try:
                self._send_json(self.viewer_server.settings_store.read())
            except SettingsStoreError as error:
                self._send_json(ErrorResponse(error=str(error)), error.status)
            except Exception:
                logging.exception("Could not read local viewer settings")
                self._send_json(
                    ErrorResponse(error="The local viewer could not read its settings."),
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return
        if request_path == READING_STATES_ENDPOINT:
            try:
                states = self.viewer_server.reader_data_store.list_reading_states()
                self._send_json(ReadingStateCollection(states=states))
            except Exception:
                logging.exception("Could not read local reader data")
                self._send_json(
                    ErrorResponse(error="The local viewer could not read saved reader data."),
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return
        catalog = (
            create_catalog(self.viewer_server.books_root)
            if request_path == "/books/catalog.js"
            else None
        )
        if catalog is not None:
            catalog_javascript = serialize_catalog(catalog).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(catalog_javascript)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(catalog_javascript)
            return
        super().do_GET()

    def do_POST(self) -> None:
        request_path = urllib.parse.urlsplit(self.path).path
        try:
            if request_path == READING_STATES_ENDPOINT:
                update = self._read_json_request(
                    ReadingStateUpdate,
                    "reading-state schema",
                )
                state = self.viewer_server.reader_data_store.update_reading_state(update)
                self._send_json(state)
                return
            if request_path == SETTINGS_ENDPOINT:
                if not self._settings_request_is_local():
                    self._send_json(
                        ErrorResponse(error="Settings are available only on this device."),
                        HTTPStatus.FORBIDDEN,
                    )
                    return
                update = self._read_json_request(
                    SettingsUpdate,
                    "settings schema",
                )
                document = self.viewer_server.settings_store.update(update.values)
                self._send_json(document)
                return
            if request_path == "/api/translate":
                request = self._read_json_request(
                    TranslationRequest,
                    "translation schema",
                )
                cache_key = self._cache_key(request)
                translation = self.viewer_server.translation_cache.get(cache_key)
                if translation is None:
                    translation = self.viewer_server.translator.translate(request)
                    self.viewer_server.translation_cache.put(cache_key, translation)
                self._send_json(TranslationResponse(translation=translation))
                return
            self._send_json(ErrorResponse(error="Endpoint not found."), HTTPStatus.NOT_FOUND)
        except ClientRequestError as error:
            self._send_json(ErrorResponse(error=str(error)), error.status)
        except TranslationError as error:
            self._send_json(ErrorResponse(error=str(error)), error.status)
        except SettingsStoreError as error:
            self._send_json(ErrorResponse(error=str(error)), error.status)
        except Exception:
            logging.exception("Unexpected local viewer API error")
            self._send_json(
                ErrorResponse(error="The local viewer encountered an unexpected API error."),
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _read_json_request(
        self,
        model_type: type[ModelT],
        schema_label: str,
    ) -> ModelT:
        if self.headers.get_content_type() != "application/json":
            raise ClientRequestError(
                "Content-Type must be application/json.",
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            )
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ClientRequestError("Content-Length is required.", HTTPStatus.LENGTH_REQUIRED)
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ClientRequestError("Invalid Content-Length.") from error
        if length <= 0:
            raise ClientRequestError("Request body must not be empty.")
        if length > MAX_REQUEST_BYTES:
            raise ClientRequestError(
                "Request body is too large.",
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
        try:
            return model_type.model_validate_json(self.rfile.read(length))
        except ValidationError as error:
            raise ClientRequestError(f"Request body does not match the {schema_label}.") from error

    def _cache_key(self, request: TranslationRequest) -> str:
        settings = self.viewer_server.settings
        cache_material = "\n".join(
            (
                settings.translation_backend_identity,
                request.model_dump_json(),
            )
        )
        return hashlib.sha256(cache_material.encode()).hexdigest()

    def _settings_request_is_local(self) -> bool:
        client_host = str(self.client_address[0])
        host_header = self.headers.get("Host", "")
        request_host = urllib.parse.urlsplit(f"//{host_header}").hostname
        return (
            _is_loopback_host(client_host)
            and request_host is not None
            and (request_host.casefold() == "localhost" or _is_loopback_host(request_host))
        )

    def _send_json(self, payload: BaseModel, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = payload.model_dump_json(by_alias=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        super().end_headers()


def _resolve_static_path(root: Path, request_path: str) -> Path:
    decoded_path = urllib.parse.unquote(request_path, errors="surrogatepass")
    normalized_path = posixpath.normpath(decoded_path)
    parts = [part for part in normalized_path.split("/") if part not in {"", "."}]
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(resolved_root):
        return resolved_root / ".invalid-request-path"
    return candidate


def _is_loopback_host(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def create_server(
    settings: ServerSettings | None = None,
    *,
    translator: Translator | None = None,
    reader_data_store: ReaderDataStore | None = None,
    settings_store: ConfigSettingsStore | None = None,
) -> BookViewerHTTPServer:
    """Create a configured server without starting its event loop."""

    return BookViewerHTTPServer(
        settings or load_server_settings(),
        translator,
        reader_data_store,
        settings_store,
    )


def _browser_url(host: str, port: int) -> str:
    browser_host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    if ":" in browser_host:
        browser_host = f"[{browser_host}]"
    return f"http://{browser_host}:{port}"


def run_server(
    settings: ServerSettings | None = None,
    *,
    open_browser: bool = True,
    browser_opener: Callable[[str], bool] | None = None,
) -> int:
    """Run the local reader until interrupted."""

    server = create_server(settings)
    try:
        host, port = server.server_address[:2]
        reader_url = _browser_url(str(host), int(port))
        print(f"Parallel book reader available at {reader_url}")
        print(f"Found {server.catalog_book_count} built books in {server.books_root}")
        if open_browser:
            try:
                opened = (browser_opener or webbrowser.open_new_tab)(reader_url)
            except Exception:
                logging.exception("Could not open the default browser")
                opened = False
            if not opened:
                print(f"Could not open a browser automatically. Open {reader_url} manually.")
        print("Press Ctrl-C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping parallel book reader.")
    finally:
        with suppress(KeyboardInterrupt):
            server.server_close()
    return 0
