#!/usr/bin/env python3
"""Translate aligned viewer segments through an OpenAI-compatible API."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, cast

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    field_validator,
)

DEFAULT_SYSTEM_PROMPT = """You are a precise professional translator from
{{SOURCE_LANGUAGE}} to {{TARGET_LANGUAGE}}.

Translate every numbered item faithfully and naturally into {{TARGET_LANGUAGE}}.
Return exactly one item for each input item, in the same order, using the exact form
[1] translation
[2] translation

The numbered labels are protocol delimiters. Never copy a protocol label into the
translation itself. Do not merge, split, omit, explain, summarize, or add content.
Translate sentence fragments as fragments. Preserve every placeholder exactly once,
along with Markdown punctuation and inline HTML. The items may be nonadjacent; translate
each independently rather than using one item to complete another. Use established
terminology for the document's subject.

Terminology preferences:
{{GLOSSARY}}
"""

SEGMENT_RE = re.compile(
    r'<span class="segment" data-seg="(?P<id>[^"]+)">(?P<text>.*?)</span>',
    re.DOTALL,
)
OUTPUT_MARKER_RE = re.compile(r"(?m)^\s*\[(\d+)\][ \t]*")
LEADING_NUMBERED_LABEL_RE = re.compile(r"^\[(\d+)\]\s+")
PROTECTED_RE = re.compile(
    r"\$(?:\\.|[^$\n])+\$"
    r"|`[^`\n]+`"
    r"|https?://[^\s<>]+"
    r"|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
    r"|\[[0-9][0-9,;\-\u2013\s]*\]"
    r"|\(\d+(?:\.\d+)+(?:[a-z])?\)"
    r"|</?[A-Za-z][^>]*>"
)
TEXT_COMMAND_RE = re.compile(r"\\text\{([^{}]*)\}")
LATEX_PLACEHOLDER_RE = re.compile(r"\$?\\+llbracket\s+([KB]\d{3}(?:\.\d{3})?)\s+\\+rrbracket\$?")
RESERVED_REQUEST_FIELDS = frozenset({"model", "messages", "temperature", "max_tokens"})
EXTRA_BODY_ADAPTER = TypeAdapter(dict[str, JsonValue], config=ConfigDict(strict=True))
STRING_MAP_ADAPTER = TypeAdapter(dict[str, str], config=ConfigDict(strict=True))


class StrictModel(BaseModel):
    """Base model for validated script configuration and API data."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TranslationConfig(StrictModel):
    """Validated settings for one resumable translation run."""

    source: Path
    target: Path
    ledger: Path
    endpoint: AnyHttpUrl
    model: str = Field(min_length=1)
    source_language: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    max_chars: int = Field(default=2700, ge=100)
    stride: int = Field(default=4, ge=1)
    max_tokens: int = Field(default=1800, ge=1)
    temperature: float = Field(default=0.0, ge=0, le=2)
    timeout_seconds: float = Field(default=180.0, gt=0)
    retries: int = Field(default=5, ge=1, le=20)
    retry_delay_seconds: float = Field(default=1.0, ge=0)
    limit_batches: int | None = Field(default=None, ge=1)
    only_segments: tuple[str, ...] = ()
    override_json: Path | None = None
    prompt_file: Path | None = None
    glossary_file: Path | None = None
    latex_text_map_file: Path | None = None
    extra_body_file: Path | None = None
    api_key: str | None = None


class ChatMessage(StrictModel):
    role: Literal["assistant"]
    content: str


class ChatChoice(StrictModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow", frozen=True, strict=True)

    message: ChatMessage


class ChatCompletionResponse(StrictModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow", frozen=True, strict=True)

    choices: list[ChatChoice] = Field(min_length=1)


class TranslationLedger(StrictModel):
    """Persistent translations tied to one source and translation configuration."""

    schema_version: Literal[1] = 1
    source_sha256: str
    request_fingerprint: str
    endpoint: str
    model: str
    source_language: str
    target_language: str
    translations: dict[str, str]

    @field_validator("translations")
    @classmethod
    def validate_translations(cls, value: dict[str, str]) -> dict[str, str]:
        if any(
            not segment_id or not translation.strip() for segment_id, translation in value.items()
        ):
            raise ValueError("ledger translations must have nonempty IDs and content")
        return value


@dataclass(frozen=True, slots=True)
class Segment:
    segment_id: str
    text: str


@dataclass(frozen=True, slots=True)
class ProtectedText:
    text: str
    values: dict[str, str]


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Translate sentence-aligned viewer Markdown through an OpenAI-compatible "
            "Chat Completions endpoint."
        )
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("OPENAI_CHAT_COMPLETIONS_URL"),
        help="Chat Completions URL; defaults to OPENAI_CHAT_COMPLETIONS_URL",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL"),
        help="model name; defaults to OPENAI_MODEL",
    )
    parser.add_argument("--source-language", required=True)
    parser.add_argument("--target-language", required=True)
    parser.add_argument("--max-chars", type=int, default=2700)
    parser.add_argument(
        "--stride",
        type=int,
        default=4,
        help="partition segments before batching; values above 1 group nonadjacent items",
    )
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--retry-delay-seconds", type=float, default=1.0)
    parser.add_argument("--limit-batches", type=int)
    parser.add_argument("--only-segment", dest="only_segments", action="append", default=[])
    parser.add_argument("--override-json", type=Path)
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--glossary-file", type=Path)
    parser.add_argument("--latex-text-map-file", type=Path)
    parser.add_argument(
        "--extra-body-file",
        type=Path,
        help="JSON object containing provider-specific request fields",
    )
    parser.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="environment variable holding an optional bearer token",
    )
    return parser


def parse_config(argv: Sequence[str] | None = None) -> TranslationConfig:
    """Parse and validate command-line configuration."""

    parser = create_parser()
    namespace = parser.parse_args(argv)
    values = vars(namespace)
    api_key_env = cast(str, values.pop("api_key_env"))
    values["api_key"] = os.environ.get(api_key_env)
    values["only_segments"] = tuple(cast(list[str], values["only_segments"]))
    if values["endpoint"] is None:
        parser.error("--endpoint or OPENAI_CHAT_COMPLETIONS_URL is required")
    if values["model"] is None:
        parser.error("--model or OPENAI_MODEL is required")
    return TranslationConfig.model_validate(values)


def load_string_map(path: Path | None, option_name: str) -> dict[str, str]:
    """Load a strict JSON string map used for terminology or deterministic overrides."""

    if path is None:
        return {}
    try:
        values = STRING_MAP_ADAPTER.validate_json(path.read_bytes())
    except ValidationError as error:
        raise ValueError(f"{option_name} must contain a JSON string-to-string object") from error
    if any(not key or not value.strip() for key, value in values.items()):
        raise ValueError(f"{option_name} keys and values must be nonempty")
    return values


def load_extra_body(path: Path | None) -> dict[str, JsonValue]:
    """Load provider extensions without permitting core-field replacement."""

    if path is None:
        return {}
    try:
        extra_body = EXTRA_BODY_ADAPTER.validate_json(path.read_bytes())
    except ValidationError as error:
        raise ValueError("--extra-body-file must contain a JSON object") from error
    conflicts = RESERVED_REQUEST_FIELDS.intersection(extra_body)
    if conflicts:
        raise ValueError(f"Extra request body cannot override: {', '.join(sorted(conflicts))}")
    return extra_body


def load_prompt_template(path: Path | None) -> str:
    """Load the default or user-provided system prompt template."""

    if path is None:
        return DEFAULT_SYSTEM_PROMPT
    return path.read_text(encoding="utf-8")


def render_system_prompt(
    template: str,
    *,
    source_language: str,
    target_language: str,
    glossary: dict[str, str],
) -> str:
    """Render documented prompt placeholders without interpreting LaTeX braces."""

    glossary_text = "\n".join(f"- {source}: {target}" for source, target in glossary.items())
    if not glossary_text:
        glossary_text = "No terminology overrides were supplied."
    replacements = {
        "{{SOURCE_LANGUAGE}}": source_language,
        "{{TARGET_LANGUAGE}}": target_language,
        "{{GLOSSARY}}": glossary_text,
    }
    prompt = template
    for marker, value in replacements.items():
        prompt = prompt.replace(marker, value)
    return prompt


def source_hash(text: str) -> str:
    """Hash the exact source revision represented by a ledger."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def request_fingerprint(
    config: TranslationConfig,
    *,
    system_prompt: str,
    extra_body: dict[str, JsonValue],
) -> str:
    """Hash settings that can change translation semantics."""

    payload: dict[str, JsonValue] = {
        "endpoint": str(config.endpoint),
        "model": config.model,
        "source_language": config.source_language,
        "target_language": config.target_language,
        "temperature": config.temperature,
        "max_chars": config.max_chars,
        "stride": config.stride,
        "max_tokens": config.max_tokens,
        "system_prompt": system_prompt,
        "extra_body": extra_body,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def extract_segments(source: str) -> list[Segment]:
    """Extract unique, single-line aligned segments from viewer Markdown."""

    segments = [Segment(match["id"], match["text"]) for match in SEGMENT_RE.finditer(source)]
    ids = [segment.segment_id for segment in segments]
    if not segments:
        raise ValueError("source contains no aligned segments")
    if len(ids) != len(set(ids)):
        raise ValueError("source contains duplicate segment IDs")
    if any("\n" in segment.text for segment in segments):
        raise ValueError("source contains multiline segment contents")
    return segments


def load_ledger(path: Path, *, digest: str, fingerprint: str) -> dict[str, str]:
    """Load translations only when the source and request configuration match."""

    if not path.exists():
        return {}
    ledger = TranslationLedger.model_validate_json(path.read_bytes())
    if ledger.source_sha256 != digest:
        raise ValueError("translation ledger belongs to a different source revision")
    if ledger.request_fingerprint != fingerprint:
        raise ValueError("translation ledger belongs to a different translation configuration")
    return dict(ledger.translations)


def save_ledger(
    path: Path,
    *,
    config: TranslationConfig,
    digest: str,
    fingerprint: str,
    translations: dict[str, str],
) -> None:
    """Atomically persist completed translations."""

    ledger = TranslationLedger(
        source_sha256=digest,
        request_fingerprint=fingerprint,
        endpoint=str(config.endpoint),
        model=config.model,
        source_language=config.source_language,
        target_language=config.target_language,
        translations=translations,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(ledger.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def protect(text: str, item_index: int) -> ProtectedText:
    """Replace notation and protocol-sensitive spans with exact placeholders."""

    if "⟦K" in text or "⟦B" in text:
        raise ValueError("source segment contains a reserved translation placeholder")
    values: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        key = f"⟦K{item_index:03d}.{len(values):03d}⟧"
        values[key] = match.group(0)
        return key

    protected = PROTECTED_RE.sub(replace, text)
    boundary = f"⟦B{item_index:03d}⟧"
    values[boundary] = ""
    return ProtectedText(f"{protected} {boundary}", values)


def restore(text: str, protected: ProtectedText) -> str:
    """Restore placeholders and reject damaged or injected markup."""

    restored = LATEX_PLACEHOLDER_RE.sub(lambda match: f"⟦{match.group(1)}⟧", text)
    for key, value in protected.values.items():
        if restored.count(key) != 1:
            raise ValueError(f"placeholder {key} was not preserved exactly once")
        restored = restored.replace(key, value)
    if "⟦K" in restored or "⟦B" in restored:
        raise ValueError("translation contains an unknown placeholder")
    restored = " ".join(part.strip() for part in restored.splitlines() if part.strip())
    if "</span>" in restored:
        raise ValueError("translation contains a closing segment tag")
    return restored.strip().replace("\N{EM DASH}", "\N{EN DASH}")


def validate_translation(source: str, translation: str) -> None:
    """Reject empty output and leaked batch labels before writing a ledger entry."""

    if not translation:
        raise ValueError("translation is empty")
    source_label = LEADING_NUMBERED_LABEL_RE.match(source.strip())
    target_label = LEADING_NUMBERED_LABEL_RE.match(translation)
    if target_label is not None and (
        source_label is None or target_label.group(1) != source_label.group(1)
    ):
        raise ValueError(
            f"translation begins with an injected batch label: {target_label.group(0)!r}"
        )


def make_batches(segments: list[Segment], max_chars: int) -> list[list[Segment]]:
    """Pack complete segments without exceeding the preferred request size."""

    batches: list[list[Segment]] = []
    current: list[Segment] = []
    current_size = 0
    for segment in segments:
        item_size = len(segment.text) + 12
        if current and current_size + item_size > max_chars:
            batches.append(current)
            current = []
            current_size = 0
        current.append(segment)
        current_size += item_size
    if current:
        batches.append(current)
    return batches


def parse_numbered_output(output: str, expected: int) -> list[str]:
    """Parse exact numbered items and an optional end sentinel."""

    normalized = output.strip()
    markers = list(OUTPUT_MARKER_RE.finditer(normalized))
    numbers = [int(match.group(1)) for match in markers]
    required = list(range(1, expected + 1))
    if numbers not in (required, [*required, expected + 1]):
        raise ValueError(f"expected numbered outputs 1..{expected}, got {numbers}")
    if len(numbers) == expected + 1:
        sentinel = normalized[markers[-1].end() :].strip()
        if sentinel != "⟦END-BATCH⟧":
            raise ValueError("final numbered output is not the batch sentinel")
    values: list[str] = []
    for index, marker in enumerate(markers[:expected]):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(normalized)
        value = normalized[marker.end() : end].strip()
        if not value:
            raise ValueError(f"output item {index + 1} is empty")
        values.append(value)
    return values


def request_body(
    config: TranslationConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    extra_body: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Build a standard text Chat Completions request."""

    body: dict[str, JsonValue] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    body.update(extra_body)
    return body


def request_translation(
    config: TranslationConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    extra_body: dict[str, JsonValue],
) -> str:
    """Send one OpenAI-compatible Chat Completions request."""

    body = request_body(
        config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        extra_body=extra_body,
    )
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    request = urllib.request.Request(
        str(config.endpoint),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
        payload = ChatCompletionResponse.model_validate_json(response.read())
    return payload.choices[0].message.content


def translate_batch(
    config: TranslationConfig,
    *,
    batch: list[Segment],
    batch_index: int,
    system_prompt: str,
    extra_body: dict[str, JsonValue],
) -> list[str]:
    """Translate one protected batch with bounded retries."""

    protected = [protect(segment.text, index) for index, segment in enumerate(batch, start=1)]
    user_prompt = "\n".join(
        f"[{index}] {item.text}" for index, item in enumerate(protected, start=1)
    )
    user_prompt += f"\n[{len(batch) + 1}] ⟦END-BATCH⟧"
    last_error: Exception | None = None
    for attempt in range(1, config.retries + 1):
        try:
            output = request_translation(
                config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                extra_body=extra_body,
            )
            parsed = parse_numbered_output(output, len(batch))
            translations = [
                restore(value, protected_item)
                for value, protected_item in zip(parsed, protected, strict=True)
            ]
            for segment, translation in zip(batch, translations, strict=True):
                validate_translation(segment.text, translation)
            return translations
        except (
            OSError,
            TimeoutError,
            ValidationError,
            ValueError,
            urllib.error.HTTPError,
            urllib.error.URLError,
        ) as error:
            last_error = error
            print(
                f"batch {batch_index}: attempt {attempt}/{config.retries} failed: {error}",
                file=sys.stderr,
                flush=True,
            )
            if attempt < config.retries:
                time.sleep(config.retry_delay_seconds * min(2 ** (attempt - 1), 15))
    raise RuntimeError(
        f"batch {batch_index} failed after {config.retries} attempt(s)"
    ) from last_error


def translate_text_commands(markdown: str, translations: dict[str, str]) -> str:
    """Apply audited exact replacements inside simple LaTeX text commands."""

    def replace(match: re.Match[str]) -> str:
        content = match.group(1)
        replacement = translations.get(content.strip())
        if replacement is None:
            return match.group(0)
        leading = content[: len(content) - len(content.lstrip())]
        trailing = content[len(content.rstrip()) :]
        return f"\\text{{{leading}{replacement}{trailing}}}"

    return TEXT_COMMAND_RE.sub(replace, markdown)


def write_target(
    *,
    source: str,
    target_path: Path,
    translations: dict[str, str],
    latex_text_map: dict[str, str],
) -> None:
    """Replace only mapped segment contents and atomically write target Markdown."""

    def replace(match: re.Match[str]) -> str:
        segment_id = match["id"]
        translated = translations[segment_id]
        return f'<span class="segment" data-seg="{segment_id}">{translated}</span>'

    target = SEGMENT_RE.sub(replace, source)
    target = translate_text_commands(target, latex_text_map)
    if [segment.segment_id for segment in extract_segments(target)] != [
        segment.segment_id for segment in extract_segments(source)
    ]:
        raise ValueError("generated target changed the source segment contract")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = target_path.with_suffix(target_path.suffix + ".tmp")
    temporary.write_text(target, encoding="utf-8")
    temporary.replace(target_path)


def pending_batches(
    segments: list[Segment],
    *,
    translations: dict[str, str],
    selected: set[str],
    stride: int,
    max_chars: int,
) -> list[list[Segment]]:
    """Build deterministic batches from untranslated selected segments."""

    batches: list[list[Segment]] = []
    for offset in range(stride):
        pending = [
            segment
            for index, segment in enumerate(segments)
            if index % stride == offset
            and segment.segment_id not in translations
            and (not selected or segment.segment_id in selected)
        ]
        batches.extend(make_batches(pending, max_chars))
    return batches


def run(config: TranslationConfig) -> int:
    """Resume translation, persist each batch, and write a complete target."""

    if not config.source.is_file():
        raise FileNotFoundError(config.source)
    source = config.source.read_text(encoding="utf-8")
    segments = extract_segments(source)
    source_ids = {segment.segment_id for segment in segments}
    source_by_id = {segment.segment_id: segment.text for segment in segments}
    glossary = load_string_map(config.glossary_file, "--glossary-file")
    latex_text_map = load_string_map(config.latex_text_map_file, "--latex-text-map-file")
    extra_body = load_extra_body(config.extra_body_file)
    system_prompt = render_system_prompt(
        load_prompt_template(config.prompt_file),
        source_language=config.source_language,
        target_language=config.target_language,
        glossary=glossary,
    )
    digest = source_hash(source)
    fingerprint = request_fingerprint(
        config,
        system_prompt=system_prompt,
        extra_body=extra_body,
    )

    config.ledger.parent.mkdir(parents=True, exist_ok=True)
    lock_path = config.ledger.with_suffix(config.ledger.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"another translator owns {lock_path}", file=sys.stderr)
            return 2

        translations = load_ledger(config.ledger, digest=digest, fingerprint=fingerprint)
        unknown = set(translations) - source_ids
        if unknown:
            raise ValueError(f"ledger contains unknown segment IDs: {sorted(unknown)[:3]}")
        for segment_id, translation in translations.items():
            validate_translation(source_by_id[segment_id], translation)

        selected = set(config.only_segments)
        missing_selected = selected - source_ids
        if missing_selected:
            raise ValueError(f"requested unknown segment IDs: {sorted(missing_selected)[:3]}")

        overrides = load_string_map(config.override_json, "--override-json")
        unknown_overrides = set(overrides) - source_ids
        if unknown_overrides:
            raise ValueError(
                f"overrides contain unknown segment IDs: {sorted(unknown_overrides)[:3]}"
            )
        for segment_id, translation in overrides.items():
            validate_translation(source_by_id[segment_id], translation)
        if overrides:
            translations.update(overrides)
            save_ledger(
                config.ledger,
                config=config,
                digest=digest,
                fingerprint=fingerprint,
                translations=translations,
            )

        batches = pending_batches(
            segments,
            translations=translations,
            selected=selected,
            stride=config.stride,
            max_chars=config.max_chars,
        )
        if config.limit_batches is not None:
            batches = batches[: config.limit_batches]
        print(
            f"loaded {len(translations)}/{len(segments)} translations; "
            f"processing {len(batches)} batches",
            flush=True,
        )
        for batch_index, batch in enumerate(batches, start=1):
            translated = translate_batch(
                config,
                batch=batch,
                batch_index=batch_index,
                system_prompt=system_prompt,
                extra_body=extra_body,
            )
            for segment, value in zip(batch, translated, strict=True):
                translations[segment.segment_id] = value
            save_ledger(
                config.ledger,
                config=config,
                digest=digest,
                fingerprint=fingerprint,
                translations=translations,
            )
            print(
                f"batch {batch_index}/{len(batches)} complete; "
                f"{len(translations)}/{len(segments)} segments",
                flush=True,
            )

        if len(translations) == len(segments):
            write_target(
                source=source,
                target_path=config.target,
                translations=translations,
                latex_text_map=latex_text_map,
            )
            print(f"wrote complete target: {config.target}", flush=True)
        else:
            print(
                f"partial run complete: {len(translations)}/{len(segments)} segments",
                flush=True,
            )
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point."""

    raise SystemExit(run(parse_config(argv)))


if __name__ == "__main__":
    main()
