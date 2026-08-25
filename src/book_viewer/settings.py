"""Strict environment-backed settings for the local viewer server."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Self

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIRECTORY_NAME = "Parallel Book Viewer"
CONFIG_ENVIRONMENT_VARIABLE = "VIEWER_CONFIG_FILE"


def _running_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _default_static_root() -> Path:
    module_path = Path(__file__).resolve()
    return module_path.parents[1] if _running_frozen() else module_path.parents[2]


def _default_books_root(static_root: Path) -> Path:
    if _running_frozen():
        return Path(sys.executable).resolve().parent / "books"
    return static_root / "books"


DEFAULT_STATIC_ROOT = _default_static_root()
DEFAULT_BOOKS_ROOT = _default_books_root(DEFAULT_STATIC_ROOT)
HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


class ViewerConfig(BaseModel):
    """Small persistent configuration written by the local installer."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    books_root: Path

    @field_validator("books_root", mode="before")
    @classmethod
    def expand_books_root(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value).expanduser()
        return value

    @model_validator(mode="after")
    def require_absolute_books_root(self) -> Self:
        if not self.books_root.is_absolute():
            raise ValueError("books_root must be an absolute path")
        return self


def default_config_path() -> Path:
    """Return the platform-appropriate per-user configuration path."""

    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIRECTORY_NAME / "config.toml"
    if sys.platform == "win32":
        config_home = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return config_home / APP_DIRECTORY_NAME / "config.toml"
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return config_home / "parallel-book-viewer" / "config.toml"


def default_reader_data_path() -> Path:
    """Return the platform-appropriate persistent reader database path."""

    home = Path.home()
    if sys.platform == "darwin":
        data_home = home / "Library" / "Application Support" / APP_DIRECTORY_NAME
    elif sys.platform == "win32":
        data_home = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        data_home /= APP_DIRECTORY_NAME
    else:
        data_home = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
        data_home /= "parallel-book-viewer"
    return data_home / "reader-data.sqlite3"


def load_viewer_config(config_path: Path | None = None) -> ViewerConfig | None:
    """Load a strict optional user configuration file."""

    configured_path = os.environ.get(CONFIG_ENVIRONMENT_VARIABLE)
    selected_path = config_path or (Path(configured_path) if configured_path else None)
    is_explicit = selected_path is not None
    path = (selected_path or default_config_path()).expanduser()
    if not path.is_file():
        if is_explicit:
            raise FileNotFoundError(f"Viewer configuration file does not exist: {path}")
        return None
    try:
        with path.open("rb") as config_file:
            values = tomllib.load(config_file)
        return ViewerConfig.model_validate(values)
    except (tomllib.TOMLDecodeError, ValidationError) as error:
        raise ValueError(f"Invalid viewer configuration in {path}: {error}") from error


class ServerSettings(BaseSettings):
    """Runtime settings loaded from environment variables or explicit values."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    host: str = Field(default="127.0.0.1", validation_alias="VIEWER_HOST", min_length=1)
    port: int = Field(default=8000, validation_alias="VIEWER_PORT", ge=0, le=65_535)
    static_root: Path = Field(default=DEFAULT_STATIC_ROOT, validation_alias="VIEWER_STATIC_ROOT")
    books_root: Path = Field(default=DEFAULT_BOOKS_ROOT, validation_alias="VIEWER_BOOKS_ROOT")
    reader_data_path: Path = Field(
        default_factory=default_reader_data_path,
        validation_alias="VIEWER_DATA_PATH",
    )
    chat_completions_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias="LLM_CHAT_COMPLETIONS_URL",
    )
    chat_model: str | None = Field(
        default=None,
        validation_alias="LLM_MODEL",
        min_length=1,
        max_length=200,
    )
    api_key: SecretStr | None = Field(default=None, validation_alias="LLM_API_KEY")
    api_key_header: str = Field(
        default="Authorization",
        validation_alias="LLM_API_KEY_HEADER",
        pattern=r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$",
    )
    api_key_scheme: str = Field(default="Bearer", validation_alias="LLM_API_KEY_SCHEME")
    extra_headers: dict[str, str] = Field(
        default_factory=dict,
        validation_alias="LLM_EXTRA_HEADERS",
    )
    temperature: float = Field(
        default=0.0,
        validation_alias="LLM_TEMPERATURE",
        ge=0,
        le=2,
    )
    max_tokens: int = Field(
        default=900,
        validation_alias="LLM_MAX_TOKENS",
        ge=1,
        le=100_000,
    )
    request_timeout_seconds: float = Field(
        default=90.0,
        validation_alias="TRANSLATION_TIMEOUT_SECONDS",
        gt=0,
        le=600,
    )
    translation_cache_items: int = Field(
        default=512,
        validation_alias="TRANSLATION_CACHE_ITEMS",
        ge=1,
        le=10_000,
    )

    @field_validator("host", "chat_model")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value != value.strip():
            raise ValueError("must not have surrounding whitespace")
        return value

    @field_validator("api_key_scheme")
    @classmethod
    def validate_api_key_scheme(cls, value: str) -> str:
        if value != value.strip() or "\r" in value or "\n" in value:
            raise ValueError("must be trimmed and must not contain line breaks")
        return value

    @field_validator("extra_headers")
    @classmethod
    def validate_extra_headers(cls, values: dict[str, str]) -> dict[str, str]:
        normalized_names: set[str] = set()
        for name, value in values.items():
            normalized_name = name.casefold()
            if normalized_name == "content-type":
                raise ValueError("Content-Type is managed by the client")
            if normalized_name in normalized_names:
                raise ValueError("header names must be unique ignoring case")
            if not HEADER_NAME_RE.fullmatch(name):
                raise ValueError("header names must use valid HTTP token characters")
            if not value or "\r" in value or "\n" in value:
                raise ValueError("header values must be non-empty and single-line")
            normalized_names.add(normalized_name)
        return values

    @model_validator(mode="after")
    def validate_backend_configuration(self) -> Self:
        has_url = self.chat_completions_url is not None
        has_model = self.chat_model is not None
        if has_url != has_model:
            raise ValueError("LLM_CHAT_COMPLETIONS_URL and LLM_MODEL must be configured together")
        if not has_url and (self.api_key is not None or self.extra_headers):
            raise ValueError("LLM authentication and headers require a configured backend")
        if self.api_key is not None:
            reserved_names = {name.casefold() for name in self.extra_headers}
            if self.api_key_header.casefold() in reserved_names:
                raise ValueError("LLM_API_KEY_HEADER must not duplicate an extra header")
        return self

    @property
    def translation_backend_configured(self) -> bool:
        return self.chat_completions_url is not None and self.chat_model is not None

    @property
    def chat_completions_endpoint(self) -> str | None:
        if self.chat_completions_url is None:
            return None
        return str(self.chat_completions_url)

    @property
    def translation_backend_identity(self) -> str:
        return "\n".join(
            (
                self.chat_completions_endpoint or "unconfigured",
                self.chat_model or "unconfigured",
            )
        )

    def request_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key is not None:
            secret = self.api_key.get_secret_value()
            value = f"{self.api_key_scheme} {secret}" if self.api_key_scheme else secret
            headers[self.api_key_header] = value
        return headers


def load_server_settings(
    *,
    config_path: Path | None = None,
    books_root: Path | None = None,
) -> ServerSettings:
    """Load server settings with CLI, environment, config, then default precedence."""

    if books_root is not None:
        return ServerSettings(books_root=books_root.expanduser().resolve())
    environment_settings = ServerSettings()
    if "books_root" in environment_settings.model_fields_set:
        return environment_settings
    config = load_viewer_config(config_path)
    if config is not None:
        return environment_settings.model_copy(update={"books_root": config.books_root})
    return environment_settings
