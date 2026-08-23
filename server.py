#!/usr/bin/env python3
"""Serve the static reader and provide an optional local translation proxy."""

from __future__ import annotations

import functools
import hashlib
import json
import os
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
MAX_REQUEST_BYTES = 64 * 1024
MAX_SENTENCE_CHARS = 4_000
MAX_CONTEXT_ITEMS = 4
MAX_CACHE_ITEMS = 512
DEFAULT_LLAMA_CPP_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_TRANSLATION_MODEL = "tencent-hy-mt"


class TranslationCache:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._values.get(key)

    def put(self, key: str, value: str) -> None:
        with self._lock:
            if len(self._values) >= MAX_CACHE_ITEMS:
                self._values.pop(next(iter(self._values)))
            self._values[key] = value


CACHE = TranslationCache()


class ReaderHandler(SimpleHTTPRequestHandler):
    server_version = "PCPReader/1.0"

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/translate":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json_body()
            normalized = validate_translation_payload(payload)
            endpoint, model = translation_backend_config()
            cache_key = hashlib.sha256(
                json.dumps(
                    {"payload": normalized, "endpoint": endpoint, "model": model},
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            translation = CACHE.get(cache_key)
            if translation is None:
                translation = request_llama_translation(normalized, endpoint, model)
                CACHE.put(cache_key, translation)
            self._send_json({"translation": translation})
        except ClientError as error:
            self._send_json({"error": str(error)}, error.status)
        except Exception:
            self.log_exception("Unexpected translation error")
            self._send_json({"error": "The local translation proxy encountered an unexpected error."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _read_json_body(self) -> Any:
        content_type = self.headers.get_content_type()
        if content_type != "application/json":
            raise ClientError("Content-Type must be application/json.", HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ClientError("Content-Length is required.", HTTPStatus.LENGTH_REQUIRED)
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ClientError("Invalid Content-Length.", HTTPStatus.BAD_REQUEST) from error
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ClientError("Request body is empty or too large.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ClientError("Request body must be valid UTF-8 JSON.", HTTPStatus.BAD_REQUEST) from error

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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

    def log_exception(self, message: str) -> None:
        self.log_error("%s", message)


class ClientError(Exception):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


def validated_text(value: Any, field: str, max_chars: int = MAX_SENTENCE_CHARS) -> str:
    if not isinstance(value, str):
        raise ClientError(f"{field} must be a string.")
    text = " ".join(value.split()).strip()
    if not text:
        raise ClientError(f"{field} must not be empty.")
    if len(text) > max_chars:
        raise ClientError(f"{field} is too long.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
    return text


def validated_context(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_CONTEXT_ITEMS:
        raise ClientError(f"{field} must be an array with at most {MAX_CONTEXT_ITEMS} strings.")
    return [validated_text(item, f"{field} item") for item in value]


def validate_translation_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ClientError("Request body must be a JSON object.")
    return {
        "sentence": validated_text(payload.get("sentence"), "sentence"),
        "before": validated_context(payload.get("before", []), "before"),
        "after": validated_context(payload.get("after", []), "after"),
        "source_language": validated_text(payload.get("source_language", "Japanese"), "source_language", 80),
        "target_language": validated_text(payload.get("target_language", "English"), "target_language", 80),
    }


def translation_backend_config() -> tuple[str, str]:
    base_url = os.environ.get("LLAMA_CPP_BASE_URL", DEFAULT_LLAMA_CPP_BASE_URL).strip()
    model = os.environ.get("TRANSLATION_MODEL", DEFAULT_TRANSLATION_MODEL).strip()
    if not base_url:
        base_url = DEFAULT_LLAMA_CPP_BASE_URL
    if not model:
        model = DEFAULT_TRANSLATION_MODEL
    return f"{base_url.rstrip('/')}/chat/completions", model


def request_llama_translation(payload: dict[str, Any], endpoint: str, model: str) -> str:
    context = json.dumps(
        {
            "preceding_sentences": payload["before"],
            "following_sentences": payload["after"],
        },
        ensure_ascii=False,
    )
    instructions = (
        f"Translate exactly one sentence from {payload['source_language']} to {payload['target_language']}. "
        "The user message is the only sentence to translate. Use the surrounding context below only to resolve "
        "terminology and references; do not translate or repeat that context. Return only the faithful translation "
        "of the user message. Preserve all mathematical notation, symbols, citation keys, and equation references. "
        f"Do not add explanation, quotation marks, Markdown fences, or commentary. Surrounding context: {context}"
    )
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": payload["sentence"]},
        ],
        "temperature": 0,
        "max_tokens": 900,
        "stream": False,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        message = "The llama.cpp server rejected the translation request."
        try:
            response_body = json.loads(error.read().decode("utf-8"))
            message = response_body.get("error", {}).get("message", message)
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
        raise ClientError(message, HTTPStatus.BAD_GATEWAY) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ClientError(
            "The viewer server could not reach llama.cpp at the configured local endpoint. Check the SSH tunnel.",
            HTTPStatus.BAD_GATEWAY,
        ) from error

    try:
        translation = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ClientError(
            "The llama.cpp server returned an invalid Chat Completions response.",
            HTTPStatus.BAD_GATEWAY,
        ) from error
    if not isinstance(translation, str) or not translation.strip():
        raise ClientError("The llama.cpp server returned no translation text.", HTTPStatus.BAD_GATEWAY)
    return translation.strip()


def main() -> None:
    host = os.environ.get("PCP_VIEWER_HOST", "127.0.0.1")
    port = int(os.environ.get("PCP_VIEWER_PORT", "8000"))
    handler = functools.partial(ReaderHandler, directory=str(BASE_DIR))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"PCP reader available at http://{host}:{port}")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping PCP reader.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
