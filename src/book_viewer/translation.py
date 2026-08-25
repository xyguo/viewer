"""Translation backend abstraction and OpenAI-compatible Chat Completions client."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from types import TracebackType
from typing import Protocol, Self, cast

from pydantic import ValidationError

from .models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    TranslationRequest,
    UpstreamErrorResponse,
)
from .settings import ServerSettings


class TranslationError(Exception):
    """A safe error that can be returned to a viewer client."""

    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_GATEWAY) -> None:
        super().__init__(message)
        self.status = status


class Translator(Protocol):
    def translate(self, request: TranslationRequest) -> str:
        """Translate exactly the selected sentence."""

        ...


class ReadableResponse(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def read(self) -> bytes: ...


class UrlOpen(Protocol):
    def __call__(self, request: urllib.request.Request, *, timeout: float) -> ReadableResponse: ...


class TranslationCache:
    """Small thread-safe FIFO cache for repeated sentence clicks."""

    def __init__(self, max_items: int) -> None:
        if max_items < 1:
            raise ValueError("max_items must be positive")
        self._max_items = max_items
        self._values: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._values.get(key)

    def put(self, key: str, value: str) -> None:
        with self._lock:
            if key not in self._values and len(self._values) >= self._max_items:
                self._values.pop(next(iter(self._values)))
            self._values[key] = value


class UnconfiguredTranslator:
    """Explain that live translation needs an explicitly configured backend."""

    def translate(self, request: TranslationRequest) -> str:
        del request
        raise TranslationError(
            "Live translation is not configured. Set translation.chat_completions_url "
            "and translation.model in Settings.",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )


class OpenAICompatibleTranslator:
    """Provider-neutral client for an OpenAI-compatible Chat Completions endpoint."""

    def __init__(
        self,
        settings: ServerSettings,
        *,
        urlopen: UrlOpen | None = None,
    ) -> None:
        endpoint = settings.chat_completions_endpoint
        model = settings.chat_model
        if endpoint is None or model is None:
            raise ValueError("A Chat Completions URL and model are required")
        self._settings = settings
        self._endpoint = endpoint
        self._model = model
        self._urlopen = urlopen or cast(UrlOpen, urllib.request.urlopen)

    def translate(self, request: TranslationRequest) -> str:
        chat_request = self._create_chat_request(request)
        payload = chat_request.model_dump(mode="json", exclude_none=True)
        payload.update(self._settings.extra_body)
        upstream_request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
            headers=self._settings.request_headers(),
            method="POST",
        )
        try:
            response_context = self._urlopen(
                upstream_request,
                timeout=self._settings.request_timeout_seconds,
            )
            with response_context as response:
                raw_response = response.read()
            parsed = ChatCompletionResponse.model_validate_json(raw_response)
        except urllib.error.HTTPError as error:
            raise self._http_error(error) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise TranslationError(
                "The viewer server could not reach the configured Chat Completions endpoint."
            ) from error
        except (ValidationError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TranslationError(
                "The translation service returned an invalid Chat Completions response."
            ) from error

        translation = parsed.choices[0].message.content.strip()
        if not translation:
            raise TranslationError("The translation service returned no translation text.")
        return translation

    def _create_chat_request(self, request: TranslationRequest) -> ChatCompletionRequest:
        context = json.dumps(
            {
                "preceding_sentences": request.before,
                "following_sentences": request.after,
            },
            ensure_ascii=False,
        )
        instructions = (
            f"Translate exactly one sentence from {request.source_language} to "
            f"{request.target_language}. The user message is the only sentence to translate. "
            "Use the surrounding context below only to resolve terminology and references; do "
            "not translate or repeat that context. Return only the faithful translation of the "
            "user message. Preserve all mathematical notation, symbols, citation keys, and "
            "equation references. Do not add explanation, quotation marks, Markdown fences, or "
            f"commentary. Surrounding context: {context}"
        )
        return ChatCompletionRequest(
            model=self._model,
            messages=[
                ChatMessage(role="system", content=instructions),
                ChatMessage(role="user", content=request.sentence),
            ],
            temperature=self._settings.temperature,
            top_p=self._settings.top_p,
            top_k=self._settings.top_k,
            max_tokens=self._settings.max_tokens,
            repeat_penalty=self._settings.repeat_penalty,
        )

    def _http_error(self, error: urllib.error.HTTPError) -> TranslationError:
        fallback = "The translation service rejected the Chat Completions request."
        try:
            parsed = UpstreamErrorResponse.model_validate_json(error.read())
            message = parsed.error.message
        except (ValidationError, UnicodeDecodeError, json.JSONDecodeError):
            message = fallback
        return TranslationError(message)
