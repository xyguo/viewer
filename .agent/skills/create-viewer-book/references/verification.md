# Build and verification

Read this reference before generating browser metadata or declaring a book complete.

Run commands from the viewer repository root. Use the project-specific uv environment and avoid global Python packages.

## Preflight

Verify that these exist:

- `books/<slug>/book.json`
- the manifest's source and target Markdown paths
- every local asset referenced by either Markdown file
- Pandoc on `PATH`

Before building, mechanically compare source and target:

- ordered segment IDs are identical and unique;
- top-level heading boundaries correspond;
- `\tag{...}` sequences are identical and unique;
- figure paths and order are identical;
- no placeholder or unfinished markers remain.

## Build

```sh
UV_CACHE_DIR=.uv-cache uv run --offline book-viewer-build \
  --manifest books/<slug>/book.json \
  --default-book <default-slug>
```

Omit `--offline` only when dependencies genuinely need to be resolved. Choose an existing default slug unless the user wants the new book to become the default.

The command builds the selected book and regenerates `books/catalog.js`. Catalog generation examines the external library, so incomplete manifests elsewhere under `books/` can make the final catalog step fail. Repair or temporarily move only files within the user's authorized scope; do not hide validation failures by weakening the schema.

## Validate

```sh
UV_CACHE_DIR=.uv-cache uv run --offline book-viewer-validate --books-dir books
scripts/check.sh
```

The first command validates every present external manifest against the latest viewer schema. The project gate checks formatting, linting, strict typing, tests, coverage, and library compatibility. Book content remains external and ignored by Git even though validation covers it.

## Browser smoke test

Start the local server when a browser check is possible:

```sh
UV_CACHE_DIR=.uv-cache uv run book-viewer-serve
```

Verify observable behavior:

1. The catalog lists the new title with correct source and target labels.
2. Opening the card loads the expected first chapter and segment count.
3. Chapter buttons and table-of-contents links load corresponding source and target chapters.
4. Representative inline and display mathematics render, including explicit equation numbers.
5. Representative figures load at nonzero dimensions.
6. Clicking a sentence highlights the same ID on both sides and aligns its counterpart.
7. One-language mode shows the mapped counterpart popup.
8. The browser console has no new errors caused by the book.

For large books, smoke-test the beginning, a middle chapter with formulas and figures, and the final chapter or bibliography. Deep-link at least one noninitial segment.

## Completion gate

The task is complete only when:

- the original document has full accounted coverage;
- `source.md` is a faithful transcription;
- `target.md` is a faithful one-to-one translation;
- the builder reports aligned segment and chapter counts;
- all current manifests validate;
- the repository quality gate passes when code or tracked contracts changed;
- the browser smoke test passes, or the exact unavailable check is reported;
- generated outputs are left untouched by hand;
- no book-specific files are force-added to Git against the repository's external-library policy.
