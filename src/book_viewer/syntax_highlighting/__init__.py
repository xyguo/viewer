"""Static code-block highlighting layered on top of Pandoc output."""

from __future__ import annotations

import re
from collections.abc import Callable
from html import unescape as unescape_html

from .lean import highlight_lean

CODE_BLOCK_RE = re.compile(
    r"(?P<open><pre(?:\s[^>]*)?><code(?:\s[^>]*)?>)"
    r"(?P<body>.*?)"
    r"(?P<close></code></pre>)",
    re.DOTALL,
)
CLASS_ATTRIBUTE_RE = re.compile(r'\bclass="([^"]*)"')

CodeHighlighter = Callable[[str], list[str]]

CUSTOM_HIGHLIGHTERS: dict[str, CodeHighlighter] = {
    "lean": highlight_lean,
    "lean4": highlight_lean,
}


def _code_classes(opening_tags: str) -> list[str]:
    return [
        class_name
        for attribute in CLASS_ATTRIBUTE_RE.findall(opening_tags)
        for class_name in attribute.split()
    ]


def _wrap_lines(lines: list[str]) -> str:
    return "\n".join(f'<span class="code-line">{line or "&#8203;"}</span>' for line in lines)


def highlight_code_blocks(html: str) -> str:
    """Apply custom highlighters and line wrappers to Pandoc code blocks."""

    def highlight_block(match: re.Match[str]) -> str:
        body = match["body"]
        if re.search(r"<span\b", body):
            return match.group(0)

        highlighter = next(
            (
                CUSTOM_HIGHLIGHTERS[class_name]
                for class_name in _code_classes(match["open"])
                if class_name in CUSTOM_HIGHLIGHTERS
            ),
            None,
        )
        lines = highlighter(unescape_html(body)) if highlighter is not None else body.split("\n")
        return f"{match['open']}{_wrap_lines(lines)}{match['close']}"

    return CODE_BLOCK_RE.sub(highlight_block, html)
