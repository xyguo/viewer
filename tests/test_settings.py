"""Tests for strict config.toml-backed server configuration."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import AnyHttpUrl, SecretStr, ValidationError
from pytest import MonkeyPatch

from book_viewer.credentials import CredentialStoreError
from book_viewer.settings import (
    ServerSettings,
    load_application_config,
    load_server_settings,
)


class MemoryCredentialStore:
    def __init__(self, api_key: str | None = None, *, unavailable: bool = False) -> None:
        self.api_key = api_key
        self.unavailable = unavailable

    def read_api_key(self) -> str | None:
        if self.unavailable:
            raise CredentialStoreError("unavailable")
        return self.api_key

    def write_api_key(self, value: str) -> None:
        self.api_key = value

    def delete_api_key(self) -> None:
        self.api_key = None


def test_default_settings_make_no_provider_assumptions() -> None:
    settings = ServerSettings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.reader_data_path.is_absolute()
    assert settings.chat_completions_endpoint is None
    assert settings.chat_model is None
    assert settings.translation_backend_configured is False
    assert settings.max_tokens == 900
    assert settings.request_headers() == {"Content-Type": "application/json"}


def test_settings_load_documented_toml_and_keyring(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""schema_version = 1

[viewer]
host = "localhost"
port = 8123
static_root = "{tmp_path}"
books_root = "{tmp_path / "library"}"
data_path = "{tmp_path / "reader-data.sqlite3"}"

[translation]
chat_completions_url = "https://provider.example/api/v1/chat/completions"
model = "test-model"
timeout_seconds = 12.5
cache_items = 128

[translation.auth]
header = "Authorization"
scheme = "Bearer"

[translation.auth.extra_headers]
X-Client = "parallel-reader"

[translation.generation]
temperature = 0.7
top_p = 0.6
top_k = 20
max_tokens = 1200
repeat_penalty = 1.05

[translation.generation.extra_body]
seed = 42
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("LLM_MODEL", "ignored-environment-model")

    settings = load_server_settings(
        config_path=config_path,
        credential_store=MemoryCredentialStore("secret"),
    )

    assert settings.host == "localhost"
    assert settings.port == 8123
    assert settings.static_root == tmp_path
    assert settings.books_root == tmp_path / "library"
    assert settings.reader_data_path == tmp_path / "reader-data.sqlite3"
    assert settings.chat_completions_endpoint == (
        "https://provider.example/api/v1/chat/completions"
    )
    assert settings.chat_model == "test-model"
    assert settings.max_tokens == 1200
    assert settings.top_p == 0.6
    assert settings.top_k == 20
    assert settings.repeat_penalty == 1.05
    assert settings.extra_body == {"seed": 42}
    assert settings.request_headers() == {
        "Content-Type": "application/json",
        "X-Client": "parallel-reader",
        "Authorization": "Bearer secret",
    }


def test_settings_support_custom_api_key_headers(tmp_path: Path) -> None:
    settings = ServerSettings(
        static_root=tmp_path,
        books_root=tmp_path,
        reader_data_path=tmp_path / "reader.sqlite3",
        chat_completions_url=AnyHttpUrl("https://provider.example/chat/completions"),
        chat_model="model",
        api_key=SecretStr("secret"),
        api_key_header="api-key",
        api_key_scheme="",
    )

    assert settings.request_headers()["api-key"] == "secret"


def test_settings_reject_invalid_values(tmp_path: Path) -> None:
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
        ServerSettings(extra_headers={"Content-Type": "text/plain"})
    with pytest.raises(ValidationError, match="HTTP token"):
        ServerSettings(extra_headers={"Invalid Header": "value"})
    with pytest.raises(ValidationError, match="must not duplicate"):
        ServerSettings(
            api_key=SecretStr("secret"),
            extra_headers={"authorization": "custom"},
        )
    with pytest.raises(ValidationError, match="cannot override"):
        ServerSettings(extra_body={"max_tokens": 5})
    with pytest.raises(ValidationError, match="absolute path"):
        ServerSettings(books_root=Path("relative"))


def test_legacy_installer_config_is_migrated_in_memory(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    books_root = tmp_path / "my library"
    config_path.write_text(f'books_root = "{books_root}"\n', encoding="utf-8")

    config = load_application_config(config_path)
    settings = load_server_settings(
        config_path=config_path,
        credential_store=MemoryCredentialStore(),
    )

    assert config.viewer.books_root == books_root
    assert settings.books_root == books_root


def test_books_root_precedence_is_cli_then_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    configured_root = tmp_path / "configured"
    command_line_root = tmp_path / "command-line"
    config_path.write_text(
        f'schema_version = 1\n\n[viewer]\nbooks_root = "{configured_root}"\n',
        encoding="utf-8",
    )

    assert (
        load_server_settings(
            config_path=config_path,
            credential_store=MemoryCredentialStore(),
        ).books_root
        == configured_root
    )
    assert (
        load_server_settings(
            config_path=config_path,
            books_root=command_line_root,
            credential_store=MemoryCredentialStore(),
        ).books_root
        == command_line_root
    )


def test_missing_invalid_and_symlinked_config(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.toml"
    settings = load_server_settings(
        config_path=missing_path,
        credential_store=MemoryCredentialStore(),
    )
    assert settings.config_path == missing_path

    invalid_path = tmp_path / "invalid.toml"
    invalid_path.write_text(
        'schema_version = 1\n\n[viewer]\nbooks_root = "relative/path"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="absolute path"):
        load_application_config(invalid_path)

    symlink_path = tmp_path / "linked.toml"
    symlink_path.symlink_to(invalid_path)
    with pytest.raises(ValueError, match="symbolic link"):
        load_application_config(symlink_path)


def test_unavailable_keyring_does_not_prevent_server_startup(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    settings = load_server_settings(
        config_path=tmp_path / "missing.toml",
        credential_store=MemoryCredentialStore(unavailable=True),
    )

    assert settings.api_key is None
    assert "Could not read the translation API key" in caplog.text
