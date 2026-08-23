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
