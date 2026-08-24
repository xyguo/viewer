#!/usr/bin/env python3
"""Transcribe PDF pages to Markdown with an OpenAI-compatible vision model."""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
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
)

DEFAULT_PROMPT = r"""Transcribe physical page {{PAGE_NUMBER}} of {{PAGE_COUNT}} from a
{{SOURCE_LANGUAGE}} document into faithful Markdown.

Requirements:
- Preserve every visible content item in reading order: headings, prose, definitions,
  examples, remarks, lists, tables, figure captions, footnotes, citations, and formulas.
- Preserve the original wording and language exactly. Join words split only by line wrapping.
  Do not translate, summarize, silently correct, or explain.
- Omit only running page headers, running footers, and bare page numbers.
- Use Markdown heading levels that reflect the visible hierarchy. Do not invent a heading from
  a running header.
- Render inline math as $...$ and display math as $$...$$ using MathJax-compatible LaTeX.
- Put each printed equation number inside its display as \tag{...}. Do not invent numbers.
- Use aligned inside one display for multiline equations when appropriate.
- Insert a line containing exactly [[FIGURE N]] immediately before each figure caption,
  numbering figures from 1 on this physical page. Preserve the printed caption, but do not
  describe unlabeled visual details.
- Compact decorative table-of-contents dot leaders to `...` while retaining every entry and
  page number.
- If the page begins or ends mid-sentence, preserve the visible fragment exactly so adjacent
  pages can be joined later.
- If no transcribable content remains after omitting running matter, return exactly
  <!-- blank page -->.
- Return only Markdown, without a code fence or commentary. Cover the full page before ending.

The PDF text layer follows. It may be incomplete or lossy. Use it as a spelling reference for
prose, but trust the image for reading order, structure, mathematics, and symbols.

--- TEXT LAYER ---
{{TEXT_LAYER}}
--- END TEXT LAYER ---
"""

IMAGE_PATTERN = re.compile(r"^page-(\d+)\.jpg$")
PAGE_RANGE_PATTERN = re.compile(r"^(\d+)(?:-(\d+))?$")
RESERVED_REQUEST_FIELDS = frozenset({"model", "messages", "temperature", "max_tokens"})
EXTRA_BODY_ADAPTER = TypeAdapter(dict[str, JsonValue], config=ConfigDict(strict=True))


class StrictModel(BaseModel):
    """Base model for validated script configuration and API data."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TranscriptionConfig(StrictModel):
    """Validated settings for one resumable transcription run."""

    pdf: Path
    work_dir: Path
    endpoint: AnyHttpUrl
    model: str = Field(min_length=1)
    source_language: str = Field(min_length=1)
    workers: int = Field(default=1, ge=1)
    image_size: int = Field(default=1400, ge=640, le=4096)
    jpeg_quality: int = Field(default=90, ge=1, le=100)
    timeout_seconds: float = Field(default=240.0, gt=0)
    retries: int = Field(default=3, ge=1, le=20)
    retry_delay_seconds: float = Field(default=3.0, ge=0)
    max_tokens: int = Field(default=6500, ge=1)
    temperature: float = Field(default=0.0, ge=0, le=2)
    text_layer_limit: int = Field(default=12_000, ge=0)
    pages: str = "all"
    prompt_file: Path | None = None
    extra_body_file: Path | None = None
    api_key: str | None = None
    force: bool = False


class ChatMessage(StrictModel):
    role: Literal["assistant"]
    content: str


class ChatChoice(StrictModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow", frozen=True, strict=True)

    message: ChatMessage


class ChatCompletionResponse(StrictModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow", frozen=True, strict=True)

    choices: list[ChatChoice] = Field(min_length=1)


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Render a PDF and transcribe each selected page with an OpenAI-compatible "
            "multimodal Chat Completions endpoint."
        )
    )
    parser.add_argument("pdf", type=Path, help="input PDF")
    parser.add_argument("work_dir", type=Path, help="directory for images and page Markdown")
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("OPENAI_CHAT_COMPLETIONS_URL"),
        help="Chat Completions URL; defaults to OPENAI_CHAT_COMPLETIONS_URL",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL"),
        help="vision model name; defaults to OPENAI_MODEL",
    )
    parser.add_argument("--source-language", required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--image-size", type=int, default=1400)
    parser.add_argument("--jpeg-quality", type=int, default=90)
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay-seconds", type=float, default=3.0)
    parser.add_argument("--max-tokens", type=int, default=6500)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--text-layer-limit", type=int, default=12_000)
    parser.add_argument(
        "--pages",
        default="all",
        help="physical pages, for example '1-12,15,20-22'; defaults to all",
    )
    parser.add_argument("--prompt-file", type=Path, help="custom UTF-8 prompt template")
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
    parser.add_argument("--force", action="store_true", help="replace cached page Markdown")
    return parser


def parse_config(argv: Sequence[str] | None = None) -> TranscriptionConfig:
    """Parse and validate command-line configuration."""

    parser = create_parser()
    namespace = parser.parse_args(argv)
    values = vars(namespace)
    api_key_env = cast(str, values.pop("api_key_env"))
    values["api_key"] = os.environ.get(api_key_env)
    if values["endpoint"] is None:
        parser.error("--endpoint or OPENAI_CHAT_COMPLETIONS_URL is required")
    if values["model"] is None:
        parser.error("--model or OPENAI_MODEL is required")
    return TranscriptionConfig.model_validate(values)


def require_program(name: str) -> None:
    """Fail early when a required Poppler program is unavailable."""

    if shutil.which(name) is None:
        raise RuntimeError(f"Required program is not on PATH: {name}")


def page_count(pdf_path: Path) -> int:
    """Read the physical page count with pdfinfo."""

    completed = subprocess.run(
        ["pdfinfo", str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    match = re.search(r"^Pages:\s+(\d+)\s*$", completed.stdout, re.MULTILINE)
    if match is None:
        raise RuntimeError("pdfinfo did not report a page count")
    return int(match.group(1))


def extract_text_pages(pdf_path: Path, text_path: Path, expected_count: int) -> list[str]:
    """Extract and split the optional PDF text layer."""

    subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), str(text_path)],
        check=True,
    )
    pages = text_path.read_text(encoding="utf-8", errors="replace").split("\f")
    if len(pages) == expected_count + 1 and not pages[-1].strip():
        pages.pop()
    if len(pages) < expected_count:
        pages.extend("" for _ in range(expected_count - len(pages)))
    if len(pages) != expected_count:
        raise RuntimeError(
            f"Text-layer page mismatch: expected {expected_count}, found {len(pages)}"
        )
    return pages


def discover_page_images(image_dir: Path) -> dict[int, Path]:
    """Index rendered page images by physical page number."""

    images: dict[int, Path] = {}
    for path in image_dir.glob("page-*.jpg"):
        match = IMAGE_PATTERN.fullmatch(path.name)
        if match is None:
            continue
        number = int(match.group(1))
        if number in images:
            raise RuntimeError(f"Duplicate image for physical page {number}")
        images[number] = path
    return images


def render_pages(config: TranscriptionConfig, expected_count: int) -> dict[int, Path]:
    """Render all PDF pages once and reuse a complete image cache."""

    image_dir = config.work_dir / "pages"
    image_dir.mkdir(parents=True, exist_ok=True)
    expected_numbers = set(range(1, expected_count + 1))
    images = discover_page_images(image_dir)
    if set(images) == expected_numbers:
        return images

    subprocess.run(
        [
            "pdftoppm",
            "-jpeg",
            "-jpegopt",
            f"quality={config.jpeg_quality},optimize=y",
            "-scale-to",
            str(config.image_size),
            str(config.pdf),
            str(image_dir / "page"),
        ],
        check=True,
    )
    images = discover_page_images(image_dir)
    if set(images) != expected_numbers:
        missing = sorted(expected_numbers - set(images))
        unexpected = sorted(set(images) - expected_numbers)
        raise RuntimeError(f"Rendered page mismatch; missing={missing}, unexpected={unexpected}")
    return images


def parse_page_selection(expression: str, total_pages: int) -> list[int]:
    """Expand a one-based page expression into sorted unique page numbers."""

    if expression.strip().lower() == "all":
        return list(range(1, total_pages + 1))
    selected: set[int] = set()
    for raw_part in expression.split(","):
        part = raw_part.strip()
        match = PAGE_RANGE_PATTERN.fullmatch(part)
        if match is None:
            raise ValueError(f"Invalid page selection component: {part!r}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start > end:
            raise ValueError(f"Descending page range is not allowed: {part!r}")
        if start < 1 or end > total_pages:
            raise ValueError(f"Page selection is outside 1-{total_pages}: {part!r}")
        selected.update(range(start, end + 1))
    if not selected:
        raise ValueError("At least one page must be selected")
    return sorted(selected)


def load_prompt(config: TranscriptionConfig) -> str:
    """Load the default or user-provided prompt template."""

    if config.prompt_file is None:
        return DEFAULT_PROMPT
    return config.prompt_file.read_text(encoding="utf-8")


def make_prompt(
    template: str,
    *,
    source_language: str,
    physical_page: int,
    total_pages: int,
    text_layer: str,
    text_layer_limit: int,
) -> str:
    """Fill the documented prompt placeholders without interpreting LaTeX braces."""

    replacements = {
        "{{SOURCE_LANGUAGE}}": source_language,
        "{{PAGE_NUMBER}}": str(physical_page),
        "{{PAGE_COUNT}}": str(total_pages),
        "{{TEXT_LAYER}}": text_layer[:text_layer_limit],
    }
    prompt = template
    for marker, value in replacements.items():
        prompt = prompt.replace(marker, value)
    return prompt


def load_extra_body(path: Path | None) -> dict[str, JsonValue]:
    """Load provider-specific request fields without permitting core-field replacement."""

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


def strip_markdown_fence(text: str) -> str:
    """Remove one accidental outer Markdown fence from model output."""

    stripped = text.strip()
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def request_body(
    config: TranscriptionConfig,
    *,
    prompt: str,
    image_data: str,
    extra_body: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Build a standard multimodal Chat Completions request."""

    body: dict[str, JsonValue] = {
        "model": config.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                    },
                ],
            }
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    body.update(extra_body)
    return body


def transcribe_page(
    config: TranscriptionConfig,
    *,
    image_path: Path,
    output_path: Path,
    physical_page: int,
    total_pages: int,
    text_layer: str,
    prompt_template: str,
    extra_body: dict[str, JsonValue],
) -> tuple[int, str]:
    """Transcribe one page, retry transient failures, and atomically cache the result."""

    if output_path.exists() and output_path.stat().st_size > 0 and not config.force:
        return physical_page, "cached"

    image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = make_prompt(
        prompt_template,
        source_language=config.source_language,
        physical_page=physical_page,
        total_pages=total_pages,
        text_layer=text_layer,
        text_layer_limit=config.text_layer_limit,
    )
    body = request_body(config, prompt=prompt, image_data=image_data, extra_body=extra_body)
    encoded_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    last_error: Exception | None = None
    for attempt in range(1, config.retries + 1):
        request = urllib.request.Request(
            str(config.endpoint),
            data=encoded_body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                payload = ChatCompletionResponse.model_validate_json(response.read())
            content = strip_markdown_fence(payload.choices[0].message.content)
            if not content:
                raise RuntimeError("Transcription response was empty")
            temporary_path = output_path.with_suffix(output_path.suffix + ".part")
            temporary_path.write_text(content + "\n", encoding="utf-8")
            temporary_path.replace(output_path)
            return physical_page, f"written ({len(content)} chars)"
        except (
            OSError,
            RuntimeError,
            TimeoutError,
            ValidationError,
            urllib.error.HTTPError,
            urllib.error.URLError,
        ) as error:
            last_error = error
            if attempt < config.retries:
                time.sleep(config.retry_delay_seconds * attempt)
    raise RuntimeError(
        f"Physical page {physical_page} failed after {config.retries} attempt(s)"
    ) from last_error


def run(config: TranscriptionConfig) -> None:
    """Prepare the PDF, run selected page jobs, and report every failure."""

    if not config.pdf.is_file():
        raise FileNotFoundError(config.pdf)
    require_program("pdfinfo")
    require_program("pdftotext")
    require_program("pdftoppm")

    config.work_dir.mkdir(parents=True, exist_ok=True)
    output_dir = config.work_dir / "source-pages"
    output_dir.mkdir(parents=True, exist_ok=True)
    total_pages = page_count(config.pdf)
    selected_pages = parse_page_selection(config.pages, total_pages)
    text_pages = extract_text_pages(
        config.pdf,
        config.work_dir / "text-layer.txt",
        total_pages,
    )
    page_images = render_pages(config, total_pages)
    prompt_template = load_prompt(config)
    extra_body = load_extra_body(config.extra_body_file)
    output_width = max(4, len(str(total_pages)))

    failures: list[str] = []
    futures: list[concurrent.futures.Future[tuple[int, str]]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.workers) as executor:
        for physical_page in selected_pages:
            futures.append(
                executor.submit(
                    transcribe_page,
                    config,
                    image_path=page_images[physical_page],
                    output_path=output_dir / f"page-{physical_page:0{output_width}d}.md",
                    physical_page=physical_page,
                    total_pages=total_pages,
                    text_layer=text_pages[physical_page - 1],
                    prompt_template=prompt_template,
                    extra_body=extra_body,
                )
            )
        for completed, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            try:
                physical_page, status = future.result()
                print(
                    f"[{completed:04d}/{len(futures):04d}] page {physical_page:04d}: {status}",
                    flush=True,
                )
            except RuntimeError as error:
                failures.append(str(error))
                print(f"[{completed:04d}/{len(futures):04d}] FAILED: {error}", flush=True)
    if failures:
        raise RuntimeError(f"{len(failures)} page(s) failed: {'; '.join(failures)}")


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point."""

    run(parse_config(argv))


if __name__ == "__main__":
    main()
