"""Strict configuration for the local viewer server."""

from __future__ import annotations

import logging
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

from .credentials import CredentialStore, CredentialStoreError, KeyringCredentialStore

APP_DIRECTORY_NAME = "Parallel Book Viewer"
CONFIG_SCHEMA_VERSION = 1
HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
RESERVED_EXTRA_BODY_FIELDS = {
    "max_tokens",
    "messages",
    "model",
    "repeat_penalty",
    "stream",
    "temperature",
    "top_k",
    "top_p",
}


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


class ConfigModel(BaseModel):
    """Strict base model for values persisted in config.toml."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ViewerConfig(ConfigModel):
    """Viewer paths and local HTTP server configuration."""

    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=0, le=65_535)
    static_root: Path = DEFAULT_STATIC_ROOT
    books_root: Path = DEFAULT_BOOKS_ROOT
    data_path: Path = Field(default_factory=default_reader_data_path)

    @field_validator("static_root", "books_root", "data_path", mode="before")
    @classmethod
    def expand_paths(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value).expanduser()
        return value

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("must not have surrounding whitespace")
        return value

    @model_validator(mode="after")
    def require_absolute_paths(self) -> Self:
        for field_name in ("static_root", "books_root", "data_path"):
            if not getattr(self, field_name).is_absolute():
                raise ValueError(f"viewer.{field_name} must be an absolute path")
        return self


class TranslationAuthConfig(ConfigModel):
    """Non-secret authentication metadata for the translation service."""

    header: str = Field(default="Authorization", pattern=r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
    scheme: str = "Bearer"
    extra_headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("scheme")
    @classmethod
    def validate_scheme(cls, value: str) -> str:
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


class GenerationConfig(ConfigModel):
    """Sampling parameters sent to the OpenAI-compatible backend."""

    temperature: float = Field(default=0.0, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    top_k: int | None = Field(default=None, ge=0, le=100_000)
    max_tokens: int = Field(default=900, ge=1, le=100_000)
    repeat_penalty: float | None = Field(default=None, gt=0, le=100)
    extra_body: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("extra_body")
    @classmethod
    def reject_core_request_overrides(
        cls,
        values: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        reserved = sorted(RESERVED_EXTRA_BODY_FIELDS.intersection(values))
        if reserved:
            raise ValueError(f"extra_body cannot override: {', '.join(reserved)}")
        return values


class TranslationConfig(ConfigModel):
    """Translation backend, generation, timeout, and cache configuration."""

    chat_completions_url: AnyHttpUrl | None = None
    model: str | None = Field(default=None, min_length=1, max_length=200)
    timeout_seconds: float = Field(default=90.0, gt=0, le=600)
    cache_items: int = Field(default=512, ge=1, le=10_000)
    auth: TranslationAuthConfig = Field(default_factory=TranslationAuthConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)

    @field_validator("model")
    @classmethod
    def reject_untrimmed_model(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("must not have surrounding whitespace")
        return value

    @model_validator(mode="after")
    def require_complete_backend(self) -> Self:
        if (self.chat_completions_url is None) != (self.model is None):
            raise ValueError(
                "translation.chat_completions_url and translation.model must be configured together"
            )
        return self


class ApplicationConfig(ConfigModel):
    """Versioned config.toml document."""

    schema_version: Literal[1] = CONFIG_SCHEMA_VERSION
    viewer: ViewerConfig = Field(default_factory=ViewerConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)


class ServerSettings(ConfigModel):
    """Immutable effective runtime settings loaded from config.toml and the keyring."""

    config_path: Path = Field(default_factory=default_config_path, exclude=True)
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=0, le=65_535)
    static_root: Path = DEFAULT_STATIC_ROOT
    books_root: Path = DEFAULT_BOOKS_ROOT
    reader_data_path: Path = Field(default_factory=default_reader_data_path)
    chat_completions_url: AnyHttpUrl | None = None
    chat_model: str | None = Field(default=None, min_length=1, max_length=200)
    api_key: SecretStr | None = Field(default=None, exclude=True)
    api_key_header: str = Field(
        default="Authorization",
        pattern=r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$",
    )
    api_key_scheme: str = "Bearer"
    extra_headers: dict[str, str] = Field(default_factory=dict)
    temperature: float = Field(default=0.0, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    top_k: int | None = Field(default=None, ge=0, le=100_000)
    max_tokens: int = Field(default=900, ge=1, le=100_000)
    repeat_penalty: float | None = Field(default=None, gt=0, le=100)
    extra_body: dict[str, JsonValue] = Field(default_factory=dict)
    request_timeout_seconds: float = Field(default=90.0, gt=0, le=600)
    translation_cache_items: int = Field(default=512, ge=1, le=10_000)

    @field_validator("host", "chat_model")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("must not have surrounding whitespace")
        return value

    @field_validator("api_key_scheme")
    @classmethod
    def validate_api_key_scheme(cls, value: str) -> str:
        return TranslationAuthConfig.validate_scheme(value)

    @field_validator("extra_headers")
    @classmethod
    def validate_extra_headers(cls, values: dict[str, str]) -> dict[str, str]:
        return TranslationAuthConfig.validate_extra_headers(values)

    @field_validator("extra_body")
    @classmethod
    def reject_core_request_overrides(
        cls,
        values: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        return GenerationConfig.reject_core_request_overrides(values)

    @model_validator(mode="after")
    def validate_settings(self) -> Self:
        if (self.chat_completions_url is None) != (self.chat_model is None):
            raise ValueError(
                "translation.chat_completions_url and translation.model must be configured together"
            )
        normalized_headers = {name.casefold() for name in self.extra_headers}
        if self.api_key_header.casefold() in normalized_headers:
            raise ValueError("the API key header must not duplicate an extra header")
        for field_name in ("static_root", "books_root", "reader_data_path"):
            if not getattr(self, field_name).is_absolute():
                raise ValueError(f"{field_name} must be an absolute path")
        return self

    @property
    def translation_backend_configured(self) -> bool:
        return self.chat_completions_url is not None and self.chat_model is not None

    @property
    def chat_completions_endpoint(self) -> str | None:
        return None if self.chat_completions_url is None else str(self.chat_completions_url)

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


def _upgrade_legacy_config(values: dict[str, object]) -> dict[str, object]:
    """Accept the old installer-only top-level books_root during migration."""

    if "books_root" not in values:
        return values
    upgraded = dict(values)
    books_root = upgraded.pop("books_root")
    viewer = upgraded.get("viewer")
    if viewer is not None:
        raise ValueError("books_root is configured both at the top level and under viewer")
    upgraded["viewer"] = {"books_root": books_root}
    upgraded.setdefault("schema_version", CONFIG_SCHEMA_VERSION)
    return upgraded


def load_application_config(path: Path) -> ApplicationConfig:
    """Read and validate one config.toml document, or return defaults when absent."""

    selected_path = path.expanduser()
    if selected_path.is_symlink():
        raise ValueError(f"Viewer configuration must not be a symbolic link: {selected_path}")
    if not selected_path.exists():
        return ApplicationConfig()
    try:
        with selected_path.open("rb") as config_file:
            values = tomllib.load(config_file)
        return ApplicationConfig.model_validate(_upgrade_legacy_config(values))
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as error:
        raise ValueError(f"Invalid viewer configuration in {selected_path}: {error}") from error


def application_config_from_settings(settings: ServerSettings) -> ApplicationConfig:
    """Create the canonical persisted document from effective runtime settings."""

    return ApplicationConfig(
        viewer=ViewerConfig(
            host=settings.host,
            port=settings.port,
            static_root=settings.static_root,
            books_root=settings.books_root,
            data_path=settings.reader_data_path,
        ),
        translation=TranslationConfig(
            chat_completions_url=settings.chat_completions_url,
            model=settings.chat_model,
            timeout_seconds=settings.request_timeout_seconds,
            cache_items=settings.translation_cache_items,
            auth=TranslationAuthConfig(
                header=settings.api_key_header,
                scheme=settings.api_key_scheme,
                extra_headers=settings.extra_headers,
            ),
            generation=GenerationConfig(
                temperature=settings.temperature,
                top_p=settings.top_p,
                top_k=settings.top_k,
                max_tokens=settings.max_tokens,
                repeat_penalty=settings.repeat_penalty,
                extra_body=settings.extra_body,
            ),
        ),
    )


def server_settings_from_config(
    config: ApplicationConfig,
    path: Path,
    api_key: str | None,
) -> ServerSettings:
    """Combine validated non-secret configuration with a separately stored secret."""

    translation = config.translation
    return ServerSettings(
        config_path=path,
        host=config.viewer.host,
        port=config.viewer.port,
        static_root=config.viewer.static_root,
        books_root=config.viewer.books_root,
        reader_data_path=config.viewer.data_path,
        chat_completions_url=translation.chat_completions_url,
        chat_model=translation.model,
        api_key=None if api_key is None else SecretStr(api_key),
        api_key_header=translation.auth.header,
        api_key_scheme=translation.auth.scheme,
        extra_headers=translation.auth.extra_headers,
        temperature=translation.generation.temperature,
        top_p=translation.generation.top_p,
        top_k=translation.generation.top_k,
        max_tokens=translation.generation.max_tokens,
        repeat_penalty=translation.generation.repeat_penalty,
        extra_body=translation.generation.extra_body,
        request_timeout_seconds=translation.timeout_seconds,
        translation_cache_items=translation.cache_items,
    )


def load_server_settings(
    *,
    books_root: Path | None = None,
    config_path: Path | None = None,
    credential_store: CredentialStore | None = None,
) -> ServerSettings:
    """Load config.toml plus the API key, with an optional temporary library override."""

    selected_path = (config_path or default_config_path()).expanduser()
    if not selected_path.is_absolute():
        selected_path = (Path.cwd() / selected_path).resolve()
    config = load_application_config(selected_path)
    credentials = credential_store or KeyringCredentialStore()
    try:
        api_key = credentials.read_api_key()
    except CredentialStoreError as error:
        logging.warning("Could not read the translation API key from the OS keyring: %s", error)
        api_key = None
    settings = server_settings_from_config(config, selected_path, api_key)
    if books_root is not None:
        settings = settings.model_copy(update={"books_root": books_root.expanduser().resolve()})
    return settings
