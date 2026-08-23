"""Unit tests for the provider-neutral Chat Completions client and cache."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from types import TracebackType
from typing import Self

import pytest
from pydantic import AnyHttpUrl, SecretStr

from book_viewer.models import LiveTargetLanguage, TranslationRequest
from book_viewer.settings import ServerSettings
from book_viewer.translation import (
    OpenAICompatibleTranslator,
    TranslationCache,
    TranslationError,
    UnconfiguredTranslator,
)


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


def translation_request(target_language: LiveTargetLanguage = "English") -> TranslationRequest:
    return TranslationRequest(
        sentence="これは文です。",
        before=["前の文です。"],
        after=["次の文です。"],
        source_language="Japanese",
        target_language=target_language,
    )


def test_chat_request_uses_context_without_authorization(tmp_path: Path) -> None:
    settings = ServerSettings(
        static_root=tmp_path,
        chat_completions_url=AnyHttpUrl("http://localhost:8080/v1/chat/completions"),
        chat_model="configured-model",
        request_timeout_seconds=12.5,
        temperature=0.25,
        max_tokens=700,
    )
    opener = FakeUrlOpen(
        FakeResponse({"choices": [{"message": {"role": "assistant", "content": "Translated."}}]})
    )
    translator = OpenAICompatibleTranslator(settings, urlopen=opener)

    assert translator.translate(translation_request("French")) == "Translated."
    request, timeout = opener.requests[0]
    assert request.full_url == "http://localhost:8080/v1/chat/completions"
    assert timeout == 12.5
    assert request.get_header("Authorization") is None
    assert isinstance(request.data, bytes)
    payload = json.loads(request.data)
    assert payload["model"] == "configured-model"
    assert payload["messages"][1]["content"] == "これは文です。"
    assert (
        "Translate exactly one sentence from Japanese to French."
        in (payload["messages"][0]["content"])
    )
    assert "前の文です。" in payload["messages"][0]["content"]
    assert "次の文です。" in payload["messages"][0]["content"]
    assert payload["stream"] is False
    assert payload["temperature"] == 0.25
    assert payload["max_tokens"] == 700


def test_chat_request_supports_remote_provider_authentication(tmp_path: Path) -> None:
    settings = ServerSettings(
        static_root=tmp_path,
        chat_completions_url=AnyHttpUrl("https://provider.example/chat/completions"),
        chat_model="remote-model",
        api_key=SecretStr("secret"),
        extra_headers={"X-Provider-Feature": "enabled"},
    )
    opener = FakeUrlOpen(
        FakeResponse({"choices": [{"message": {"role": "assistant", "content": "Done."}}]})
    )
    translator = OpenAICompatibleTranslator(settings, urlopen=opener)

    assert translator.translate(translation_request()) == "Done."
    upstream_request, _timeout = opener.requests[0]
    assert upstream_request.full_url == "https://provider.example/chat/completions"
    assert upstream_request.get_header("Authorization") == "Bearer secret"
    assert upstream_request.get_header("X-provider-feature") == "enabled"


def test_chat_client_rejects_invalid_response(tmp_path: Path) -> None:
    translator = OpenAICompatibleTranslator(
        ServerSettings(
            static_root=tmp_path,
            chat_completions_url=AnyHttpUrl("https://provider.example/chat/completions"),
            chat_model="model",
        ),
        urlopen=FakeUrlOpen(FakeResponse({"choices": []})),
    )
    with pytest.raises(TranslationError, match="invalid Chat Completions"):
        translator.translate(translation_request())


def test_chat_client_reports_connection_failure(tmp_path: Path) -> None:
    def unavailable(
        request: urllib.request.Request,
        *,
        timeout: float,
    ) -> FakeResponse:
        del request, timeout
        raise urllib.error.URLError("offline")

    settings = ServerSettings(
        static_root=tmp_path,
        chat_completions_url=AnyHttpUrl("https://provider.example/chat/completions"),
        chat_model="model",
    )
    translator = OpenAICompatibleTranslator(settings, urlopen=unavailable)
    with pytest.raises(TranslationError, match="configured Chat Completions endpoint"):
        translator.translate(translation_request())


def test_unconfigured_translator_returns_service_unavailable(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="URL and model"):
        OpenAICompatibleTranslator(
            ServerSettings(
                static_root=tmp_path,
                chat_completions_url=None,
                chat_model=None,
            )
        )

    with pytest.raises(TranslationError) as error_info:
        UnconfiguredTranslator().translate(translation_request())
    assert error_info.value.status == 503


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
