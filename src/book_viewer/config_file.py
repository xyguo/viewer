"""Validated, atomic config.toml updates for the local Settings UI."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import TypeGuard

import tomli_w
from pydantic import SecretStr, ValidationError

from .credentials import CredentialStore, CredentialStoreError, KeyringCredentialStore
from .models import SettingsDocument, SettingsField, SettingsInputType
from .settings import (
    ApplicationConfig,
    ServerSettings,
    application_config_from_settings,
    load_application_config,
    server_settings_from_config,
)

API_KEY_SETTING = "translation.api_key"
INTEGER_FIELDS = {"port", "top_k", "max_tokens", "translation_cache_items"}
FLOAT_FIELDS = {
    "temperature",
    "top_p",
    "repeat_penalty",
    "request_timeout_seconds",
}
JSON_FIELDS = {"extra_headers", "extra_body"}
PATH_FIELDS = {"static_root", "books_root", "reader_data_path"}
OPTIONAL_FIELDS = {
    "chat_completions_url",
    "chat_model",
    "top_p",
    "top_k",
    "repeat_penalty",
}


class SettingsStoreError(Exception):
    """A safe local-settings error suitable for the web UI."""

    def __init__(
        self,
        message: str,
        status: HTTPStatus = HTTPStatus.BAD_REQUEST,
    ) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class SettingDefinition:
    name: str
    field_name: str
    label: str
    description: str
    group: str
    input_type: SettingsInputType
    note: str | None = None
    sensitive: bool = False


SETTING_DEFINITIONS = (
    SettingDefinition(
        "viewer.host",
        "host",
        "Server host",
        "Network interface used by the local viewer server.",
        "Viewer",
        "text",
    ),
    SettingDefinition(
        "viewer.port",
        "port",
        "Server port",
        "Local TCP port used to open the viewer in your browser.",
        "Viewer",
        "number",
    ),
    SettingDefinition(
        "viewer.static_root",
        "static_root",
        "Viewer files",
        "Directory containing the viewer's HTML, JavaScript, and CSS files.",
        "Viewer",
        "path",
    ),
    SettingDefinition(
        "viewer.books_root",
        "books_root",
        "Book library",
        "Directory containing the local collection of built book packages.",
        "Viewer",
        "path",
    ),
    SettingDefinition(
        "viewer.data_path",
        "reader_data_path",
        "Reading data",
        "SQLite file used for reading progress and other local reader data.",
        "Viewer",
        "path",
    ),
    SettingDefinition(
        "translation.chat_completions_url",
        "chat_completions_url",
        "Chat Completions URL",
        "Complete OpenAI-compatible Chat Completions endpoint used for live translation.",
        "Translation service",
        "url",
    ),
    SettingDefinition(
        "translation.model",
        "chat_model",
        "Model",
        "Provider model identifier sent with each live translation request.",
        "Translation service",
        "text",
    ),
    SettingDefinition(
        API_KEY_SETTING,
        "api_key",
        "API key",
        "Secret credential stored in the operating-system keyring and sent only by the local server.",
        "Translation service",
        "password",
        sensitive=True,
    ),
    SettingDefinition(
        "translation.auth.header",
        "api_key_header",
        "API key header",
        "HTTP header used to send the API key, normally Authorization.",
        "Translation service",
        "text",
    ),
    SettingDefinition(
        "translation.auth.scheme",
        "api_key_scheme",
        "API key scheme",
        "Authentication prefix placed before the API key; leave empty for an unprefixed key.",
        "Translation service",
        "text",
    ),
    SettingDefinition(
        "translation.auth.extra_headers",
        "extra_headers",
        "Extra headers",
        "JSON object of non-secret provider-specific HTTP headers.",
        "Translation service",
        "json",
    ),
    SettingDefinition(
        "translation.generation.temperature",
        "temperature",
        "Temperature",
        "Sampling temperature sent with live translation requests, from 0 to 2.",
        "Generation",
        "number",
    ),
    SettingDefinition(
        "translation.generation.top_p",
        "top_p",
        "Top P",
        "Optional nucleus-sampling probability threshold, from 0 to 1.",
        "Generation",
        "number",
    ),
    SettingDefinition(
        "translation.generation.top_k",
        "top_k",
        "Top K",
        "Optional number of highest-probability tokens retained for sampling.",
        "Generation",
        "number",
        note="This llama.cpp-specific parameter may be rejected by the official OpenAI API.",
    ),
    SettingDefinition(
        "translation.generation.max_tokens",
        "max_tokens",
        "Maximum tokens",
        "Legacy-compatible upper limit on tokens generated for one translation.",
        "Generation",
        "number",
    ),
    SettingDefinition(
        "translation.generation.repeat_penalty",
        "repeat_penalty",
        "Repetition penalty",
        "Optional penalty applied to repeated token sequences.",
        "Generation",
        "number",
        note="This llama.cpp-specific parameter may be rejected by the official OpenAI API.",
    ),
    SettingDefinition(
        "translation.generation.extra_body",
        "extra_body",
        "Extra request body",
        "JSON object of additional provider-specific Chat Completions parameters.",
        "Generation",
        "json",
    ),
    SettingDefinition(
        "translation.timeout_seconds",
        "request_timeout_seconds",
        "Request timeout",
        "Maximum seconds to wait for one live translation request.",
        "Performance",
        "number",
    ),
    SettingDefinition(
        "translation.cache_items",
        "translation_cache_items",
        "Translation cache size",
        "Maximum number of recent translations retained in memory.",
        "Performance",
        "number",
    ),
)


class ConfigSettingsStore:
    """Read config.toml and update it alongside the separate keyring secret."""

    def __init__(
        self,
        path: Path,
        credential_store: CredentialStore | None = None,
    ) -> None:
        expanded_path = path.expanduser()
        self.path = expanded_path if expanded_path.is_absolute() else Path.cwd() / expanded_path
        self.credentials = credential_store or KeyringCredentialStore()
        self._definitions = {definition.name: definition for definition in SETTING_DEFINITIONS}
        self._lock = threading.Lock()

    def read(self) -> SettingsDocument:
        with self._lock:
            return self._snapshot_unlocked(restart_required=False)

    def update(self, updates: Mapping[str, str | None]) -> SettingsDocument:
        with self._lock:
            unsupported_names = sorted(set(updates) - self._definitions.keys())
            if unsupported_names:
                raise SettingsStoreError(f"Unsupported settings: {', '.join(unsupported_names)}.")
            if not updates:
                return self._snapshot_unlocked(restart_required=False)

            config = self._load_config_unlocked()
            key_update = updates.get(API_KEY_SETTING) if API_KEY_SETTING in updates else ...
            old_key = self._read_api_key_unlocked(required=key_update is not ...)
            current = server_settings_from_config(config, self.path, old_key)
            candidate_values = current.model_dump()
            candidate_values.update(config_path=self.path, api_key=current.api_key)

            for name, raw_value in updates.items():
                definition = self._definitions[name]
                if definition.sensitive:
                    continue
                candidate_values[definition.field_name] = _parse_value(definition, raw_value)

            try:
                candidate = ServerSettings.model_validate(candidate_values)
                candidate_config = application_config_from_settings(candidate)
            except ValidationError as error:
                raise SettingsStoreError(_validation_message(error)) from error

            config_changed = candidate_config != config
            key_changed = key_update is not ... and key_update != old_key
            if not config_changed and not key_changed:
                return self._snapshot_unlocked(restart_required=False, api_key=old_key)

            if key_changed:
                self._update_api_key_unlocked(key_update)
            try:
                if config_changed:
                    self._write_config_unlocked(candidate_config)
            except Exception:
                if key_changed:
                    self._restore_api_key_unlocked(old_key)
                raise
            saved_key = old_key if key_update is ... else key_update
            return self._snapshot_unlocked(restart_required=True, api_key=saved_key)

    def _snapshot_unlocked(
        self,
        *,
        restart_required: bool,
        api_key: str | object | None = ...,
    ) -> SettingsDocument:
        config = self._load_config_unlocked()
        saved_names = self._configured_names_unlocked()
        secret = self._read_api_key_unlocked(required=False) if api_key is ... else api_key
        secret_value = secret if isinstance(secret, str) else None
        settings = server_settings_from_config(config, self.path, secret_value)
        fields = [
            _settings_field(definition, settings, saved_names) for definition in SETTING_DEFINITIONS
        ]
        return SettingsDocument(
            source=str(self.path),
            fields=fields,
            restartRequired=restart_required,
        )

    def _load_config_unlocked(self) -> ApplicationConfig:
        try:
            return load_application_config(self.path)
        except ValueError as error:
            raise SettingsStoreError(str(error)) from error

    def _configured_names_unlocked(self) -> set[str]:
        if not self.path.exists():
            return set()
        try:
            with self.path.open("rb") as config_file:
                values = tomllib.load(config_file)
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise SettingsStoreError(
                "The viewer could not read config.toml.",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            ) from error
        configured = {
            definition.name
            for definition in SETTING_DEFINITIONS
            if not definition.sensitive and _nested_key_exists(values, definition.name)
        }
        if "books_root" in values:
            configured.add("viewer.books_root")
        return configured

    def _read_api_key_unlocked(self, *, required: bool) -> str | None:
        try:
            return self.credentials.read_api_key()
        except CredentialStoreError as error:
            if required:
                raise SettingsStoreError(str(error), HTTPStatus.SERVICE_UNAVAILABLE) from error
            return None

    def _update_api_key_unlocked(self, value: str | object | None) -> None:
        try:
            if isinstance(value, str):
                if not value:
                    raise SettingsStoreError("The API key must not be empty.")
                self.credentials.write_api_key(value)
            else:
                self.credentials.delete_api_key()
        except CredentialStoreError as error:
            raise SettingsStoreError(str(error), HTTPStatus.SERVICE_UNAVAILABLE) from error

    def _restore_api_key_unlocked(self, value: str | None) -> None:
        try:
            if value is None:
                self.credentials.delete_api_key()
            else:
                self.credentials.write_api_key(value)
        except CredentialStoreError:
            return

    def _write_config_unlocked(self, config: ApplicationConfig) -> None:
        if self.path.is_symlink():
            raise SettingsStoreError(
                "config.toml must not be a symbolic link.", HTTPStatus.CONFLICT
            )
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            serialized_values: dict[str, object] = {
                "schema_version": config.schema_version,
                **config.model_dump(
                    mode="json",
                    exclude={"schema_version"},
                    exclude_defaults=True,
                    exclude_none=True,
                ),
            }
            serialized = tomli_w.dumps(serialized_values)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix="config.toml.",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_path.chmod(0o600)
                temporary_file.write(serialized)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            temporary_path.replace(self.path)
            temporary_path = None
            self.path.chmod(0o600)
        except (OSError, TypeError) as error:
            raise SettingsStoreError(
                "The viewer could not write config.toml.",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            ) from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def _parse_value(definition: SettingDefinition, value: str | None) -> object:
    field_name = definition.field_name
    if value is None:
        field = ServerSettings.model_fields[field_name]
        return field.get_default(call_default_factory=True)
    if value == "" and field_name in OPTIONAL_FIELDS:
        return None
    try:
        if field_name in INTEGER_FIELDS:
            return int(value)
        if field_name in FLOAT_FIELDS:
            return float(value)
        if field_name in JSON_FIELDS:
            return json.loads(value)
        if field_name in PATH_FIELDS:
            return Path(value).expanduser()
        return value
    except (ValueError, json.JSONDecodeError) as error:
        raise SettingsStoreError(f"Invalid value for {definition.name}.") from error


def _settings_field(
    definition: SettingDefinition,
    settings: ServerSettings,
    saved_names: set[str],
) -> SettingsField:
    raw_value = getattr(settings, definition.field_name)
    default = ServerSettings.model_fields[definition.field_name].get_default(
        call_default_factory=True
    )
    is_set = (
        settings.api_key is not None if definition.sensitive else definition.name in saved_names
    )
    return SettingsField(
        name=definition.name,
        label=definition.label,
        description=definition.description,
        note=definition.note,
        group=definition.group,
        inputType=definition.input_type,
        value=None if definition.sensitive else _format_value(raw_value),
        defaultValue=None if definition.sensitive else _format_value(default),
        isSet=is_set,
        sensitive=definition.sensitive,
    )


def _format_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, SecretStr):
        return None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _nested_key_exists(values: Mapping[str, object], dotted_name: str) -> bool:
    current: object = values
    for part in dotted_name.split("."):
        if not _is_string_mapping(current):
            return False
        if part not in current:
            return False
        current = current[part]
    return True


def _is_string_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _validation_message(error: ValidationError) -> str:
    issue = error.errors(include_url=False, include_context=False, include_input=False)[0]
    message = str(issue["msg"]).removeprefix("Value error, ")
    location = ".".join(str(part) for part in issue["loc"])
    if location:
        return f"Invalid value for {location}: {message}."
    return f"Invalid settings: {message}."
