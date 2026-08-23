"""Strict environment-backed settings for the local viewer server."""

from __future__ import annotations

from pathlib import Path

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_STATIC_ROOT = Path(__file__).resolve().parents[2]


class ServerSettings(BaseSettings):
    """Runtime settings loaded from environment variables or explicit values."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra="ignore",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    host: str = Field(default="127.0.0.1", validation_alias="VIEWER_HOST", min_length=1)
    port: int = Field(default=8000, validation_alias="VIEWER_PORT", ge=0, le=65_535)
    static_root: Path = Field(default=DEFAULT_STATIC_ROOT, validation_alias="VIEWER_STATIC_ROOT")
    llama_cpp_base_url: AnyHttpUrl = Field(
        default=AnyHttpUrl("http://127.0.0.1:8080/v1"),
        validation_alias="LLAMA_CPP_BASE_URL",
    )
    translation_model: str = Field(
        default="tencent-hy-mt",
        validation_alias="TRANSLATION_MODEL",
        min_length=1,
        max_length=200,
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

    @field_validator("host", "translation_model")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("must not have surrounding whitespace")
        return value

    @property
    def chat_completions_endpoint(self) -> str:
        return f"{str(self.llama_cpp_base_url).rstrip('/')}/chat/completions"
