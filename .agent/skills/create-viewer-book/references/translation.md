# Segment translation

Read this reference when translating an aligned `source.md` through an
OpenAI-compatible Chat Completions service.

## Precondition

Finish and audit `source.md` before translation. Every visible translatable unit must already
have a unique `data-seg` value, and display equations must sit outside segment spans. Translation
preserves those IDs and the surrounding Markdown structure rather than repairing source layout.

## Reusable translator

Use [`scripts/translate_segments.py`](../scripts/translate_segments.py). It protects inline math,
citations, URLs, code, and HTML; translates approximately sentence-sized segments in bounded
batches; writes an atomic resumable ledger after every successful batch; and creates `target.md`
only after every source segment has a translation.

Run it from the viewer repository with explicit languages and paths:

```sh
OPENAI_CHAT_COMPLETIONS_URL=https://provider.example/v1/chat/completions \
OPENAI_MODEL=translation-model \
OPENAI_API_KEY=secret \
uv run python .agent/skills/create-viewer-book/scripts/translate_segments.py \
  --source books/example/source.md \
  --target books/example/target.md \
  --ledger /path/to/work-dir/translations.json \
  --source-language German \
  --target-language English
```

The API key is optional for unauthenticated local services. Keep the ledger and other temporary
translation state outside the final book package. Rerun the same command after interruption; the
ledger is accepted only when the source revision and translation-affecting request settings match.

The default `--stride 4` places nonadjacent segments together to reduce accidental continuation
between items. Use `--stride 1` when adjacent context materially improves translation quality, and
audit boundary fidelity more closely. Tune `--max-chars` and `--max-tokens` to the model's context
and output limits. Use `--limit-batches` for a quality trial and `--only-segment ID` for repairs.

## Provider extensions

The standard request is provider-neutral. Put optional provider fields in a JSON object and pass
it with `--extra-body-file`; core Chat Completions fields cannot be replaced. For example, a
llama.cpp deployment that supports Qwen's template option can disable reasoning with:

```json
{
  "chat_template_kwargs": {
    "enable_thinking": false
  }
}
```

Benchmark a representative range before changing reasoning behavior or models. Keep the faster
setting only when formulas, qualifiers, terminology, and segment boundaries remain faithful.

## Terminology and mathematical text

Pass `--glossary-file` when recurring terms need fixed translations. The file is a JSON
string-to-string object included in the system prompt:

```json
{
  "Satz": "theorem",
  "Beweis": "proof"
}
```

Inline math is protected from model edits. If prose inside simple `\text{...}` commands must be
translated, audit those labels and pass exact replacements through `--latex-text-map-file`:

```json
{
  "mit": "with",
  "sonst": "otherwise"
}
```

Use `--prompt-file` only when the generic prompt is inadequate. A custom UTF-8 template may use
`{{SOURCE_LANGUAGE}}`, `{{TARGET_LANGUAGE}}`, and `{{GLOSSARY}}`. Changing the prompt invalidates
an existing ledger intentionally.

For audited corrections, pass a JSON string map from segment ID to complete translated content
with `--override-json`. Overrides are validated against the source IDs and persisted in the ledger.

## Quality controls

The script retries malformed output, damaged placeholders, and injected batch-number labels.
These checks protect structure, not meaning. Before accepting `target.md`:

- compare every target segment with its source ID for omissions, additions, and mistranslation;
- check numbers, negation, citations, formula references, and deliberate repetition;
- search for residual source-language prose and protocol or placeholder residue;
- compare ordered IDs, heading boundaries, equation tags, and figure paths mechanically;
- review representative early, middle, difficult, and final sections in the viewer.

Treat manual overrides and LaTeX text maps as book-specific work files. Reuse the script and its
contract, not one book's terminology or corrections.
