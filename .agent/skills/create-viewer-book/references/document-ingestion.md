# Document ingestion

Read this reference when the input is a PDF, scan, image set, or another format where text extraction may lose layout or notation.

## Inventory first

Record the input filename, page count, source language, title, authors, visible section hierarchy, page-number offset, and whether the file has an extractable text layer. Make a page or section coverage ledger before dividing work. Completion means every content page is accounted for exactly once, including front matter, appendices, bibliography, and index when they are part of the requested book.

## Extract and inspect

1. Extract the embedded text layer when available. Treat it as an OCR aid, not as authoritative structure.
2. Render representative pages and every difficult page containing mathematics, tables, multiple columns, figures, footnotes, or unusual typography.
3. Compare extracted text against the rendered page. Correct reading order, ligatures, hyphenation, superscripts, subscripts, accents, punctuation, and characters that OCR commonly confuses.
4. Reconstruct formulas from the visual source. Verify symbols, indices, operator names, matrix dimensions, cases, relation signs, and printed equation numbers.
5. Extract or crop each figure into `assets/figures/` with deterministic names tied to the source page or section. Verify the resulting image visually.

## Reusable PDF transcription

For page-wise vision transcription, use
[`scripts/transcribe_pdf.py`](../scripts/transcribe_pdf.py). It renders the PDF with Poppler,
adds the text layer as an OCR aid, sends each selected page to an OpenAI-compatible multimodal
Chat Completions endpoint, and writes resumable fragments under `source-pages/`.

Run it from the viewer repository with explicit document and service settings:

```sh
OPENAI_CHAT_COMPLETIONS_URL=https://provider.example/v1/chat/completions \
OPENAI_MODEL=vision-model \
OPENAI_API_KEY=secret \
uv run python .agent/skills/create-viewer-book/scripts/transcribe_pdf.py \
  /path/to/input.pdf /path/to/work-dir --source-language German --workers 4
```

The API key is optional for unauthenticated local services. Use one work directory per PDF.
Existing nonempty page fragments are cached; pass `--force` only for pages that need replacement.
Use `--pages 12-18,24` for a repair run. Run `--help` for rendering, retry, prompt, and text-layer
controls.

The request body uses standard multimodal Chat Completions fields. If a provider supports useful
extensions, pass a JSON object with `--extra-body-file`. For example, a llama.cpp deployment that
supports Qwen's template switch can receive:

```json
{
  "chat_template_kwargs": {
    "enable_thinking": false
  }
}
```

Treat the fragments as OCR candidates. Perform the coverage and visual audits below before
assembling `source.md`; rerun flagged pages with a stronger model or a tailored prompt.

When parallel workers or multiple models are available, assign disjoint page ranges and a single shared contract for IDs, Markdown, terminology, and output filenames. Require each worker to report its exact coverage. Assemble only after checking that ranges are contiguous and non-overlapping.

## Transcribe before translating

Create a faithful source edition first. Preserve the document's language; normalize only extraction artifacts. Keep deliberate spelling, notation, and bibliographic titles unless there is clear OCR evidence of an error.

Assign segment IDs during source transcription. Maintain a terminology ledger for recurring technical terms, names, abbreviations, theorem labels, and notation. This ledger guides translation but does not replace sentence-level review.

## Translate by segment

Translate only the human-language content of each source segment. Copy its ID unchanged. Use neighboring segments for context, but do not merge them into the output or repeat them. Preserve inline math, display math, citations, URLs, code, labels, and equation references.

Faithful means the target retains every claim, qualification, connective, definition, and reference from the source. Prefer established terminology in the target field. Preserve sentence-to-sentence mapping over stylistic rewriting.

For text embedded inside a diagram, either preserve the source figure and translate its visible caption, or create a translated figure only when the user requests it. Record any source labels that remain untranslated.

## Audits

Run both passes:

- **Coverage audit:** compare the source Markdown against the original page by page or section by section. Check first and last lines of every range, all headings, figures, tables, equations, footnotes, and bibliography entries.
- **Translation audit:** compare each target segment with its source ID. Check omissions, additions, residual source-language prose, terminology consistency, negation, numbers, citations, and mathematical text.

Automated checks complement visual review. Search for placeholder markers, replacement characters, suspicious OCR tokens, and common source-language function words in the target. Treat search results as candidates requiring judgment rather than automatic errors.
