"""Tests for strict environment-backed server configuration."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import AnyHttpUrl, SecretStr, ValidationError
from pytest import MonkeyPatch

from book_viewer.server import create_server
from book_viewer.settings import ServerSettings


def test_default_settings_make_no_provider_assumptions(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in (
        "VIEWER_HOST",
        "VIEWER_PORT",
        "VIEWER_STATIC_ROOT",
        "LLM_CHAT_COMPLETIONS_URL",
        "LLM_MODEL",
        "LLM_API_KEY",
        "LLM_EXTRA_HEADERS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = ServerSettings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.chat_completions_endpoint is None
    assert settings.chat_model is None
    assert settings.translation_backend_configured is False
    assert settings.request_headers() == {"Content-Type": "application/json"}


def test_settings_parse_documented_environment(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VIEWER_HOST", "localhost")
    monkeypatch.setenv("VIEWER_PORT", "8123")
    monkeypatch.setenv("VIEWER_STATIC_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "LLM_CHAT_COMPLETIONS_URL",
        "https://provider.example/api/v1/chat/completions",
    )
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv("LLM_EXTRA_HEADERS", '{"X-Client":"parallel-reader"}')
    settings = ServerSettings()
    assert settings.host == "localhost"
    assert settings.port == 8123
    assert settings.static_root == tmp_path
    assert settings.chat_completions_endpoint == (
        "https://provider.example/api/v1/chat/completions"
    )
    assert settings.chat_model == "test-model"
    assert settings.translation_backend_configured is True
    assert settings.request_headers() == {
        "Content-Type": "application/json",
        "X-Client": "parallel-reader",
        "Authorization": "Bearer secret",
    }


def test_settings_support_custom_api_key_headers(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = ServerSettings(
        static_root=tmp_path,
        chat_completions_url=AnyHttpUrl("https://provider.example/chat/completions"),
        chat_model="model",
        api_key=SecretStr("secret"),
        api_key_header="api-key",
        api_key_scheme="",
    )
    assert settings.request_headers()["api-key"] == "secret"


def test_settings_reject_invalid_values(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError, match="less than or equal to 65535"):
        ServerSettings(port=70_000)
    with pytest.raises(ValidationError, match="surrounding whitespace"):
        ServerSettings(
            chat_completions_url=AnyHttpUrl("https://provider.example/chat/completions"),
            chat_model=" model ",
        )
    with pytest.raises(ValidationError, match="configured together"):
        ServerSettings(chat_model="model")
    with pytest.raises(ValidationError, match="managed by the client"):
        ServerSettings(
            chat_completions_url=AnyHttpUrl("https://provider.example/chat/completions"),
            chat_model="model",
            extra_headers={"Content-Type": "text/plain"},
        )
    with pytest.raises(ValidationError, match="HTTP token"):
        ServerSettings(
            chat_completions_url=AnyHttpUrl("https://provider.example/chat/completions"),
            chat_model="model",
            extra_headers={"Invalid Header": "value"},
        )
    with pytest.raises(ValidationError, match="must not duplicate"):
        ServerSettings(
            chat_completions_url=AnyHttpUrl("https://provider.example/chat/completions"),
            chat_model="model",
            api_key=SecretStr("secret"),
            extra_headers={"authorization": "custom"},
        )


def test_server_requires_existing_static_root(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    settings = ServerSettings(static_root=tmp_path / "missing", port=0)
    with pytest.raises(FileNotFoundError, match="static root"):
        create_server(settings)
