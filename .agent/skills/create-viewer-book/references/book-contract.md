# Viewer book contract

Read this reference for every book creation, translation, rebuild, or repair task.

## Source of truth

From the viewer repository root, inspect these before writing metadata:

- `schemas/book.schema.json`: checked-in manifest schema.
- `src/book_viewer/models.py`: strict Pydantic data contracts and current schema version.
- `src/book_viewer/builder.py`: Markdown rendering, alignment, chapter, equation-tag, and asset invariants.
- `README.md`, section `Add another book`: supported build commands and current layout.

Repository code wins if an example in this skill has become stale.

## Final directory

```text
books/<slug>/
|-- book.json
|-- source.md
|-- target.md
|-- assets/
|   `-- figures/
|       `-- <book-specific images>
|-- document-data.js                 generated
`-- document-data-chunks/            generated
    |-- 001-source.js
    |-- 001-target.js
    `-- ...
```

`books/catalog.js` is also generated. Keep all of these book-specific files under `books/<slug>/`; the repository intentionally ignores `books/*`.

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
- `books/catalog.js`: catalog of all currently valid, built books.

If generated data is wrong, fix `book.json`, Markdown, assets, or builder code as appropriate, then rebuild.
