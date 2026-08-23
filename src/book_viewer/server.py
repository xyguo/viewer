"""Serve the static reader and same-origin local translation proxy."""

from __future__ import annotations

import functools
import hashlib
import logging
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

from pydantic import BaseModel, ValidationError

from .models import ErrorResponse, TranslationRequest, TranslationResponse
from .settings import ServerSettings
from .translation import LlamaCppTranslator, TranslationCache, TranslationError, Translator

MAX_REQUEST_BYTES = 64 * 1024


class ClientRequestError(Exception):
    """An invalid HTTP request with a safe client-facing explanation."""

    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


class BookViewerHTTPServer(ThreadingHTTPServer):
    """Threaded server carrying immutable runtime collaborators for handlers."""

    def __init__(self, settings: ServerSettings, translator: Translator | None = None) -> None:
        static_root = settings.static_root.resolve()
        if not static_root.is_dir():
            raise FileNotFoundError(f"Viewer static root does not exist: {static_root}")
        self.settings = settings
        self.translator = translator or LlamaCppTranslator(settings)
        self.translation_cache = TranslationCache(settings.translation_cache_items)
        handler = functools.partial(ReaderHandler, directory=str(static_root))
        super().__init__((settings.host, settings.port), handler)


class ReaderHandler(SimpleHTTPRequestHandler):
    """Generic static-file handler with one validated translation endpoint."""

    server_version = "ParallelBookViewer/1.0"

    @property
    def viewer_server(self) -> BookViewerHTTPServer:
        return cast(BookViewerHTTPServer, self.server)

    def do_POST(self) -> None:
        if self.path != "/api/translate":
            self._send_json(ErrorResponse(error="Endpoint not found."), HTTPStatus.NOT_FOUND)
            return
        try:
            request = self._read_translation_request()
            cache_key = self._cache_key(request)
            translation = self.viewer_server.translation_cache.get(cache_key)
            if translation is None:
                translation = self.viewer_server.translator.translate(request)
                self.viewer_server.translation_cache.put(cache_key, translation)
            self._send_json(TranslationResponse(translation=translation))
        except ClientRequestError as error:
            self._send_json(ErrorResponse(error=str(error)), error.status)
        except TranslationError as error:
            self._send_json(ErrorResponse(error=str(error)), error.status)
        except Exception:
            logging.exception("Unexpected translation proxy error")
            self._send_json(
                ErrorResponse(error="The local translation proxy encountered an unexpected error."),
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _read_translation_request(self) -> TranslationRequest:
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
            return TranslationRequest.model_validate_json(self.rfile.read(length))
        except ValidationError as error:
            raise ClientRequestError(
                "Request body does not match the translation schema."
            ) from error

    def _cache_key(self, request: TranslationRequest) -> str:
        settings = self.viewer_server.settings
        cache_material = "\n".join(
            (
                settings.chat_completions_endpoint,
                settings.translation_model,
                request.model_dump_json(),
            )
        )
        return hashlib.sha256(cache_material.encode()).hexdigest()

    def _send_json(self, payload: BaseModel, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = payload.model_dump_json().encode()
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


def create_server(
    settings: ServerSettings | None = None,
    *,
    translator: Translator | None = None,
) -> BookViewerHTTPServer:
    """Create a configured server without starting its event loop."""

    return BookViewerHTTPServer(settings or ServerSettings(), translator)


def run_server(settings: ServerSettings | None = None) -> int:
    """Run the local reader until interrupted."""

    with create_server(settings) as server:
        host, port = server.server_address[:2]
        print(f"Parallel book reader available at http://{host}:{port}")
        print("Press Ctrl-C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping parallel book reader.")
    return 0
