---
name: create-viewer-book
description: Convert a source document into a faithful, sentence-aligned bilingual book package under books/ for the Parallel Book Viewer. Use when ingesting, OCRing, transcribing, translating, rebuilding, or repairing viewer book content and metadata; do not use for viewer application development alone.
---

# Create Viewer Book

Produce a complete external book package that the current viewer can build and render. Treat the repository's Pydantic models, JSON Schema, and builder as the authority whenever this skill differs from the checked-out code.

## Load the applicable contract

1. Read [references/book-contract.md](references/book-contract.md) before creating or changing any book files.
2. For PDF, scan, image, or layout-sensitive input, also read [references/document-ingestion.md](references/document-ingestion.md) before transcription.
3. For LLM-assisted sentence translation, read [references/translation.md](references/translation.md) before creating `target.md`.
4. Read [references/verification.md](references/verification.md) before building or declaring completion.

## Workflow

1. Locate the viewer repository root by finding `schemas/book.schema.json`, `src/book_viewer/`, and `books/`. Inspect the current schema and builder before choosing fields or commands.
2. Resolve the requested source language, target language, title, and book slug from the user's request and source document. Ask only when a missing choice would materially change the output.
3. Create `books/<slug>/book.json`, `source.md`, `target.md`, and any book-local assets. Keep temporary OCR or translation fragments outside the final book package.
4. Transcribe the complete source document into `source.md`. Preserve its heading hierarchy, lists, tables, captions, footnotes, citations, mathematical notation, display equations, explicit equation numbers, and figure order to the degree supported by Markdown and MathJax.
5. Assign deterministic segment IDs to approximately sentence-sized source units. Translate each unit faithfully into exactly one target unit with the same ID and order. Preserve technical meaning, notation, references, and deliberate repetition.
6. Audit completeness against the input document, then audit source and target mechanically. Resolve every missing page or section, duplicate or mismatched segment, altered equation tag, missing asset, placeholder, and untranslated passage.
7. Run the repository builder. It generates `document-data.js`, chapter chunk scripts, and the catalog. Generated JavaScript is build output and must not be hand-authored.
8. Run manifest validation, the project quality gate, and a browser smoke test. Finish only when the book opens from the catalog and its structure, mathematics, figures, navigation, and sentence mapping work.

## Completion report

Report the book directory, source and target Markdown paths, aligned segment count, chapter count, validation results, and any source limitations that remain. Book data under `books/` is intentionally external and Git-ignored; preserve that policy unless the user explicitly changes it.
