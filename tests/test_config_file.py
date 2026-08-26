"""Tests for atomic config.toml persistence and separate keyring secrets."""

from __future__ import annotations

import stat
import tomllib
from pathlib import Path

import pytest

from book_viewer.config_file import ConfigSettingsStore, SettingsStoreError
from book_viewer.models import SettingsField
from tests.fakes import MemoryCredentialStore


def field_by_name(store: ConfigSettingsStore, name: str) -> SettingsField:
    return next(field for field in store.read().fields if field.name == name)


def test_settings_store_masks_keyring_secret_and_reports_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """schema_version = 1

[translation]
chat_completions_url = "https://provider.example/v1/chat/completions"
model = "model"
""",
        encoding="utf-8",
    )
    store = ConfigSettingsStore(config_path, MemoryCredentialStore("super-secret"))

    api_key = field_by_name(store, "translation.api_key")
    port = field_by_name(store, "viewer.port")
    top_k = field_by_name(store, "translation.generation.top_k")
    repeat_penalty = field_by_name(store, "translation.generation.repeat_penalty")
    max_tokens = field_by_name(store, "translation.generation.max_tokens")
    document = store.read()

    assert document.source == str(config_path)
    assert "super-secret" not in document.model_dump_json()
    assert api_key.is_set is True
    assert api_key.value is None
    assert port.is_set is False
    assert port.value == "8000"
    assert port.default_value == "8000"
    assert top_k.note == (
        "This llama.cpp-specific parameter may be rejected by the official OpenAI API."
    )
    assert repeat_penalty.note == top_k.note
    assert max_tokens.note is None


def test_settings_store_writes_canonical_toml_and_keyring(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    credentials = MemoryCredentialStore("old-secret")
    store = ConfigSettingsStore(config_path, credentials)

    document = store.update(
        {
            "viewer.books_root": str(tmp_path / "books"),
            "translation.chat_completions_url": ("https://provider.example/v1/chat/completions"),
            "translation.model": "new model",
            "translation.api_key": "new-secret",
            "translation.generation.max_tokens": "1200",
            "translation.generation.top_k": "20",
            "translation.generation.repeat_penalty": "1.05",
        }
    )
    saved_text = config_path.read_text(encoding="utf-8")
    saved = tomllib.loads(saved_text)

    assert document.restart_required is True
    assert credentials.api_key == "new-secret"
    assert "new-secret" not in saved_text
    assert saved["viewer"] == {"books_root": str(tmp_path / "books")}
    assert saved["translation"]["model"] == "new model"
    generation = saved["translation"]["generation"]
    assert set(generation) == {"max_tokens", "repeat_penalty", "top_k"}
    assert generation["max_tokens"] == 1200
    assert generation["top_k"] == 20
    assert generation["repeat_penalty"] == 1.05
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


def test_other_updates_preserve_key_and_explicit_remove_deletes_it(tmp_path: Path) -> None:
    credentials = MemoryCredentialStore("keep-this-secret")
    store = ConfigSettingsStore(tmp_path / "config.toml", credentials)

    updated = store.update({"translation.generation.max_tokens": "1200"})
    assert credentials.api_key == "keep-this-secret"
    assert field_by_name(store, "translation.api_key").is_set is True
    assert "keep-this-secret" not in updated.model_dump_json()

    removed = store.update({"translation.api_key": None})
    assert removed.restart_required is True
    assert credentials.api_key is None
    assert field_by_name(store, "translation.api_key").is_set is False


def test_reset_uses_default_and_optional_blank_removes_value(tmp_path: Path) -> None:
    store = ConfigSettingsStore(tmp_path / "config.toml", MemoryCredentialStore())
    store.update(
        {
            "translation.chat_completions_url": "http://localhost:8080/v1/chat/completions",
            "translation.model": "model",
            "translation.generation.temperature": "0.7",
            "translation.generation.top_p": "0.6",
        }
    )

    document = store.update(
        {
            "translation.generation.temperature": None,
            "translation.generation.top_p": "",
        }
    )
    temperature = next(
        field for field in document.fields if field.name == "translation.generation.temperature"
    )
    top_p = next(field for field in document.fields if field.name == "translation.generation.top_p")
    saved_translation = tomllib.loads((tmp_path / "config.toml").read_text(encoding="utf-8"))[
        "translation"
    ]
    saved_generation = saved_translation.get("generation", {})

    assert temperature.value == "0.0"
    assert temperature.is_set is False
    assert top_p.value is None
    assert top_p.is_set is False
    assert "temperature" not in saved_generation
    assert "top_p" not in saved_generation


def test_invalid_settings_do_not_replace_existing_file_or_key(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    original = "schema_version = 1\n\n[viewer]\nport = 8000\n"
    config_path.write_text(original, encoding="utf-8")
    credentials = MemoryCredentialStore("old-secret")
    store = ConfigSettingsStore(config_path, credentials)

    with pytest.raises(SettingsStoreError, match="less than or equal to 65535"):
        store.update(
            {
                "viewer.port": "70000",
                "translation.api_key": "new-secret",
            }
        )

    assert config_path.read_text(encoding="utf-8") == original
    assert credentials.api_key == "old-secret"


def test_keyring_failure_does_not_replace_existing_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    original = "schema_version = 1\n\n[viewer]\nport = 8000\n"
    config_path.write_text(original, encoding="utf-8")
    store = ConfigSettingsStore(
        config_path,
        MemoryCredentialStore("old-secret", fail_writes=True),
    )

    with pytest.raises(SettingsStoreError, match="Keyring write failed"):
        store.update(
            {
                "viewer.port": "8123",
                "translation.api_key": "new-secret",
            }
        )

    assert config_path.read_text(encoding="utf-8") == original


def test_settings_store_rejects_unknown_fields(tmp_path: Path) -> None:
    store = ConfigSettingsStore(tmp_path / "config.toml", MemoryCredentialStore())
    with pytest.raises(SettingsStoreError, match=r"unsupported\.value"):
        store.update({"unsupported.value": "value"})
