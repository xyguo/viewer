# Viewer book contract

Read this reference for every book creation, translation, rebuild, or repair task.

## Source of truth

From the viewer repository root, inspect these before writing metadata:

- `schemas/book.schema.json`: checked-in manifest schema.
- `src/book_viewer/models.py`: strict Pydantic data contracts and current schema version.
- `src/book_viewer/builder.py`: Markdown rendering, alignment, chapter, equation-tag, and asset invariants.
- `AGENTS.md`: repository boundaries, development workflow, and metadata maintenance policy.

Repository code wins if an example in this skill has become stale.

## Final directory

```text
books/<slug>/
|-- book.json
|-- source.md
|-- target.md
|-- catalog.js                       generated one-book catalog
|-- assets/
|   `-- figures/
|       `-- <book-specific images>
|-- document-data.js                 generated
`-- document-data-chunks/            generated
    |-- 001-source.js
    |-- 001-target.js
    `-- ...
```

The library-level `books/catalog.js` is also generated. Keep all book-specific files under `books/<slug>/`. Ordinary packages are ignored external data; `books/example/` is the sole tracked fixture and includes its source PDF and generated metadata.

## Manifest

Use the schema version and constraints currently declared by `schemas/book.schema.json`. A current version 2 manifest has this shape:

```json
{
  "$schema": "../../schemas/book.schema.json",
  "schema_version": 2,
  "slug": "example-book",
  "title": "Example Book",
  "reader_title": "Example Book Reader",
  "description": "A faithful sentence-aligned source and translation.",
  "source": {
    "language": "Japanese",
    "label": "日本語",
    "html_lang": "ja",
    "markdown": "source.md",
    "html_id_prefix": "source"
  },
  "target": {
    "language": "English",
    "label": "English",
    "html_lang": "en",
    "markdown": "target.md",
    "html_id_prefix": "target"
  },
  "data_file": "document-data.js",
  "asset_rewrites": {
    "assets/": "books/example-book/assets/"
  },
  "mathjax": {
    "packages": ["ams", "newcommand", "mathtools"],
    "macros": {}
  }
}
```

Use a lowercase hyphenated slug. Use valid BCP 47 values for `html_lang`, human-readable labels for controls, and distinct lowercase HTML ID prefixes. Add only MathJax packages and macros the document needs.

## Metadata compatibility

`schema_version` is mandatory. Use the version currently declared by the checked-in schema and models; do not copy a version from an older book without verifying it. The manifest, catalog entry, chapter index, and chapter payloads share this compatibility version, and the viewer intentionally rejects stale generated data.

`schemas/book.schema.json` is generated from the strict Pydantic `BookManifest` model. Application developers changing that model must regenerate the schema with:

```sh
UV_CACHE_DIR=.uv-cache uv run --offline book-viewer-schema --output schemas/book.schema.json
```

Book creation work must validate the complete external library against the checked-out application before completion. Repair an incompatible manifest and rebuild its generated metadata; do not weaken validation or hand-edit the schema to accept stale data.

## Markdown dialect

The builder renders with Pandoc using GitHub-flavored Markdown, dollar-delimited TeX math, raw HTML, and MathJax. Use UTF-8.

### Segments

The ordered `data-seg` values are the sentence mapping contract:

```markdown
<span class="segment" data-seg="EX-p012-0007">A source sentence.</span>
```

```markdown
<span class="segment" data-seg="EX-p012-0007">Its faithful translation.</span>
```

Required invariants:

- Source and target contain the same IDs in exactly the same order.
- IDs are non-empty and unique across the whole book.
- Each segment is approximately one sentence. A heading, caption, list item, table cell, short footnote, or other indivisible visible unit may be one segment.
- Translation preserves the segment boundary. One source segment maps to one target segment, even when the target language would naturally split or merge the sentence.
- Segment spans contain inline content. Keep block structures such as paragraphs, lists, tables, and display equations outside the span wrapper.
- Give every visible translatable unit a segment ID. Do not use an unsegmented paragraph as a workaround for difficult alignment.

For paginated input, prefer IDs such as `<PREFIX>-p<page>-<ordinal>`, with zero-padded ordinals. For non-paginated input, use a stable structural form such as `<PREFIX>-c<chapter>-<ordinal>`. Once assigned, preserve IDs through corrections so existing links remain valid.

Use mechanical sentence boundaries: ordinary sentence-final punctuation such as `.`, `?`, `!`, `。`, `？`, or `！`, while keeping abbreviations, decimal points, citations, and inline mathematics attached to their sentence. When punctuation is genuinely ambiguous, keep the neighboring text together rather than inventing a semantic split.

### Structure and chapters

Preserve corresponding Markdown heading levels in both editions. Every top-level `#` heading starts an independently loadable viewer chapter, so source and target must have the same top-level chapter boundaries and order. Put the heading text itself inside its segment:

```markdown
# <span class="segment" data-seg="EX-p001-0001">Chapter 1</span>
```

Use `##`, `###`, and `####` for lower levels as the source structure requires. The viewer table of contents uses rendered heading segments from levels 1 through 3.

### Mathematics

Preserve inline and display mathematics as LaTeX. Keep mathematical identifiers, operators, delimiters, cases, arrays, and references structurally equivalent between editions. Translate prose inside `\text{...}` when it belongs to the surrounding language.

Explicit equation numbers must use `\tag{...}` in both files, in identical order:

```markdown
$$
E = mc^2 \tag{2.4}
$$
```

Keep a display equation as its own block between adjacent prose segments. The builder validates `\tag` values and order, but the transcription audit must also catch unnumbered formulas that were dropped or changed.

### Code blocks

Preserve consecutive source code as fenced Markdown instead of wrapping individual lines in sentence segments. Add a language label so the existing Pandoc build step can produce static syntax tokens without a browser dependency:

````markdown
```c
int main(void) {
  return 0;
}
```
````

The viewer provides lightweight syntax colors and line numbers for C (`c`), C++ (`cpp`), Python (`python`), shell (`bash` or `zsh`), Rust (`rust`), Haskell (`haskell`), Go (`go`), assembly (`asm`, `fasm`, or `nasm`), JavaScript (`javascript` or `js`), TypeScript (`typescript` or `ts`), Lean (`lean` or `lean4`), OCaml (`ocaml` or `ml`), Scala (`scala`), Java (`java`), and HTML (`html`). Unlabeled fenced blocks still render as consecutive numbered code, but without syntax colors.

### Figures and other assets

Store assets under the book directory and reference them with the same path and order in both editions:

```markdown
![Source-language caption](assets/figures/EX-p012-fig-1.png)

<span class="segment" data-seg="EX-p012-0008">Figure 2. Caption text.</span>
```

The alt text may be translated, but the image path must be identical. Keep the visible caption as a mapped segment. Crop figures to include the intended diagram while excluding unrelated neighboring text; preserve labels needed to understand the source.

## Generated metadata

`book-viewer-build` validates the manifest and Markdown, renders both editions, splits at top-level headings, and writes the browser payloads. Never edit these directly:

- `document-data.js`: book metadata, table of contents, chapter index, segment index, and MathJax configuration.
- `document-data-chunks/*.js`: source and target HTML for lazily loaded chapters.
- `catalog.js`: a portable one-entry catalog for opening the book without a library catalog.
- `books/catalog.js`: catalog of all currently valid, built books.

If generated data is wrong, fix `book.json`, Markdown, assets, or builder code as appropriate, then rebuild.
