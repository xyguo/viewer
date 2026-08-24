"""Small build-time syntax highlighter for Lean 4 code."""

from __future__ import annotations

from html import escape as escape_html

DECLARATION_KEYWORDS = frozenset(
    {
        "abbrev",
        "axiom",
        "class",
        "def",
        "elab",
        "inductive",
        "lemma",
        "macro",
        "namespace",
        "opaque",
        "structure",
        "syntax",
        "theorem",
    }
)
KEYWORDS = DECLARATION_KEYWORDS | frozenset(
    {
        "as",
        "by",
        "decreasing_by",
        "deriving",
        "do",
        "else",
        "end",
        "example",
        "export",
        "extends",
        "for",
        "forall",
        "from",
        "fun",
        "have",
        "if",
        "import",
        "in",
        "include",
        "infix",
        "infixl",
        "infixr",
        "instance",
        "let",
        "match",
        "mutual",
        "noncomputable",
        "open",
        "partial",
        "private",
        "protected",
        "return",
        "section",
        "show",
        "suffices",
        "termination_by",
        "then",
        "universe",
        "unsafe",
        "variable",
        "where",
        "with",
    }
)
BUILTIN_TYPES = frozenset(
    {
        "Bool",
        "Char",
        "Float",
        "Int",
        "List",
        "Nat",
        "Option",
        "Prop",
        "Sort",
        "String",
        "Type",
        "UInt8",
        "UInt16",
        "UInt32",
        "UInt64",
        "Unit",
    }
)
CONSTANTS = frozenset({"admit", "false", "sorry", "true"})
OPERATOR_CHARS = frozenset("!#$%&*+,-./:;<=>?@\\^|~")
UNICODE_OPERATOR_CHARS = frozenset("→←∀∃λ⊢⟨⟩")


def _code_span(class_name: str, value: str) -> str:
    return f'<span class="{class_name}">{escape_html(value)}</span>'


def _consume_block_comment(line: str, start: int, depth: int) -> tuple[int, int]:
    index = start
    if depth == 0:
        depth = 1
        index += 2
    while index < len(line):
        if line.startswith("/-", index):
            depth += 1
            index += 2
        elif line.startswith("-/", index):
            depth -= 1
            index += 2
            if depth == 0:
                break
        else:
            index += 1
    return index, depth


def _consume_quoted_literal(line: str, start: int, quote: str) -> int:
    index = start + 1
    escaped = False
    while index < len(line):
        character = line[index]
        index += 1
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == quote:
            break
    return index


def _highlight_line(line: str, block_comment_depth: int) -> tuple[str, int]:
    output: list[str] = []
    index = 0
    expect_declaration_name = False
    while index < len(line):
        if block_comment_depth or line.startswith("/-", index):
            end, block_comment_depth = _consume_block_comment(line, index, block_comment_depth)
            output.append(_code_span("co", line[index:end]))
            index = end
            continue

        if line.startswith("--", index):
            output.append(_code_span("co", line[index:]))
            break

        character = line[index]
        if character == '"':
            end = _consume_quoted_literal(line, index, character)
            output.append(_code_span("st", line[index:end]))
            index = end
            continue
        if character == "'":
            end = _consume_quoted_literal(line, index, character)
            output.append(_code_span("ch", line[index:end]))
            index = end
            continue

        if character == "#" and index + 1 < len(line) and line[index + 1].isalpha():
            end = index + 2
            while end < len(line) and (line[end].isalnum() or line[end] in "_'"):
                end += 1
            output.append(_code_span("pp", line[index:end]))
            index = end
            continue

        if character.isdigit():
            end = index + 1
            while end < len(line) and (line[end].isalnum() or line[end] in "._"):
                end += 1
            output.append(_code_span("dv", line[index:end]))
            index = end
            continue

        if character.isalpha() or character == "_":
            end = index + 1
            while end < len(line) and (line[end].isalnum() or line[end] in "_'"):
                end += 1
            identifier = line[index:end]
            if expect_declaration_name:
                output.append(_code_span("fu", identifier))
                expect_declaration_name = False
            elif identifier in KEYWORDS:
                output.append(_code_span("kw", identifier))
                expect_declaration_name = identifier in DECLARATION_KEYWORDS
            elif identifier in BUILTIN_TYPES:
                output.append(_code_span("dt", identifier))
            elif identifier in CONSTANTS:
                output.append(_code_span("cn", identifier))
            else:
                output.append(escape_html(identifier))
            index = end
            continue

        if character in OPERATOR_CHARS or character in UNICODE_OPERATOR_CHARS:
            end = index + 1
            while end < len(line) and (
                line[end] in OPERATOR_CHARS or line[end] in UNICODE_OPERATOR_CHARS
            ):
                end += 1
            output.append(_code_span("op", line[index:end]))
            index = end
            continue

        output.append(escape_html(character))
        index += 1

    return "".join(output), block_comment_depth


def highlight_lean(code: str) -> list[str]:
    """Return escaped, statically highlighted HTML for each Lean source line."""

    block_comment_depth = 0
    highlighted_lines: list[str] = []
    for line in code.split("\n"):
        highlighted, block_comment_depth = _highlight_line(line, block_comment_depth)
        highlighted_lines.append(highlighted)
    return highlighted_lines
