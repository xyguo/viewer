"""Tests for strict environment-backed server configuration."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from book_viewer.server import create_server
from book_viewer.settings import ServerSettings


def test_default_settings_target_local_llama_cpp(monkeypatch: MonkeyPatch) -> None:
    for name in (
        "VIEWER_HOST",
        "VIEWER_PORT",
        "VIEWER_STATIC_ROOT",
        "LLAMA_CPP_BASE_URL",
        "TRANSLATION_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = ServerSettings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.chat_completions_endpoint == ("http://127.0.0.1:8080/v1/chat/completions")
    assert settings.translation_model == "tencent-hy-mt"


def test_settings_parse_documented_environment(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIEWER_HOST", "localhost")
    monkeypatch.setenv("VIEWER_PORT", "8123")
    monkeypatch.setenv("VIEWER_STATIC_ROOT", str(tmp_path))
    monkeypatch.setenv("LLAMA_CPP_BASE_URL", "http://localhost:9090/v1/")
    monkeypatch.setenv("TRANSLATION_MODEL", "test-model")
    settings = ServerSettings()
    assert settings.host == "localhost"
    assert settings.port == 8123
    assert settings.static_root == tmp_path
    assert settings.chat_completions_endpoint == "http://localhost:9090/v1/chat/completions"
    assert settings.translation_model == "test-model"


def test_settings_reject_invalid_values() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 65535"):
        ServerSettings(port=70_000)
    with pytest.raises(ValidationError, match="surrounding whitespace"):
        ServerSettings(translation_model=" model ")


def test_server_requires_existing_static_root(tmp_path: Path) -> None:
    settings = ServerSettings(static_root=tmp_path / "missing", port=0)
    with pytest.raises(FileNotFoundError, match="static root"):
        create_server(settings)
