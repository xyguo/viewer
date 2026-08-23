"""Unit tests for the llama.cpp translation client and cache."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from types import TracebackType
from typing import Self

import pytest

from book_viewer.models import TranslationRequest
from book_viewer.settings import ServerSettings
from book_viewer.translation import LlamaCppTranslator, TranslationCache, TranslationError


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.body = json.dumps(payload).encode()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class FakeUrlOpen:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests: list[tuple[urllib.request.Request, float]] = []

    def __call__(
        self,
        request: urllib.request.Request,
        *,
        timeout: float,
    ) -> FakeResponse:
        self.requests.append((request, timeout))
        return self.response


def translation_request() -> TranslationRequest:
    return TranslationRequest(
        sentence="これは文です。",
        before=["前の文です。"],
        after=["次の文です。"],
        source_language="Japanese",
        target_language="English",
    )


def test_llama_cpp_request_uses_context_without_authorization(tmp_path: Path) -> None:
    settings = ServerSettings(
        static_root=tmp_path,
        translation_model="configured-model",
        request_timeout_seconds=12.5,
    )
    opener = FakeUrlOpen(
        FakeResponse({"choices": [{"message": {"role": "assistant", "content": "Translated."}}]})
    )
    translator = LlamaCppTranslator(settings, urlopen=opener)

    assert translator.translate(translation_request()) == "Translated."
    request, timeout = opener.requests[0]
    assert request.full_url == "http://127.0.0.1:8080/v1/chat/completions"
    assert timeout == 12.5
    assert request.get_header("Authorization") is None
    assert isinstance(request.data, bytes)
    payload = json.loads(request.data)
    assert payload["model"] == "configured-model"
    assert payload["messages"][1]["content"] == "これは文です。"
    assert "前の文です。" in payload["messages"][0]["content"]
    assert "次の文です。" in payload["messages"][0]["content"]
    assert payload["stream"] is False


def test_llama_cpp_rejects_invalid_response(tmp_path: Path) -> None:
    translator = LlamaCppTranslator(
        ServerSettings(static_root=tmp_path),
        urlopen=FakeUrlOpen(FakeResponse({"choices": []})),
    )
    with pytest.raises(TranslationError, match="invalid Chat Completions"):
        translator.translate(translation_request())


def test_llama_cpp_reports_connection_failure(tmp_path: Path) -> None:
    def unavailable(
        request: urllib.request.Request,
        *,
        timeout: float,
    ) -> FakeResponse:
        del request, timeout
        raise urllib.error.URLError("offline")

    translator = LlamaCppTranslator(ServerSettings(static_root=tmp_path), urlopen=unavailable)
    with pytest.raises(TranslationError, match="SSH tunnel"):
        translator.translate(translation_request())


def test_translation_cache_evicts_oldest_item() -> None:
    cache = TranslationCache(2)
    cache.put("one", "1")
    cache.put("two", "2")
    cache.put("two", "updated")
    cache.put("three", "3")
    assert cache.get("one") is None
    assert cache.get("two") == "updated"
    assert cache.get("three") == "3"
    with pytest.raises(ValueError, match="positive"):
        TranslationCache(0)
