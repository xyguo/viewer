# AGENTS.md

## Scope

Parallel Book Viewer is a lightweight static reader with a small typed Python server and build toolchain. Keep the browser application book-independent and keep ordinary book packages external under the ignored `books/` directory. The sole tracked exception is the canonical `books/example/` fixture.

`README.md` is the concise user quick start. Put contributor workflow and repository architecture here. Put document ingestion, translation, alignment, manifest, and book verification instructions in `.agent/skills/create-viewer-book/`.

## Project layout

- `index.html`, `bootstrap.js`, `app.js`, and `styles.css`: generic catalog and reader frontend.
- `src/book_viewer/`: strict Pydantic models, book builder, library discovery, settings, translation client, MathJax installer, HTTP server, and command-line entry points.
- `schemas/book.schema.json`: generated, tracked manifest contract.
- `tests/`: Python, HTTP, frontend-contract, and project-skill tests.
- `scripts/check.sh`: complete quality gate used locally and by pre-commit.
- `scripts/build-binary.sh` and `book-viewer.spec`: standalone executable build.
- `.agent/skills/create-viewer-book/`: canonical agent workflow for creating and updating book packages.
- `docs/assets/`: tracked images used by repository documentation.
- `books/`: ignored external library. `books/.gitkeep` and the complete `books/example/` fixture are tracked.
- `vendor/mathjax/`: ignored thin local MathJax installation.

## Book and metadata contracts

Use `.agent/skills/create-viewer-book/` whenever work creates, translates, rebuilds, or repairs a book. Its references define the current package layout, mechanical sentence mapping, equation and asset handling, build commands, and completion checks.

Treat `src/book_viewer/models.py`, `schemas/book.schema.json`, and `src/book_viewer/builder.py` as the application authority. `book.json` must declare the supported `schema_version`. Generated catalogs, chapter indexes, and chapter payloads carry that version, and the viewer rejects incompatible data.

Generated `document-data.js`, `document-data-chunks/`, per-book `catalog.js`, and the library-level `books/catalog.js` are build outputs. Correct source Markdown, target Markdown, assets, manifests, or builder code and regenerate them instead of editing generated JavaScript. The local server discovers built books and serializes its catalog in memory on every `/books/catalog.js` request; the generated catalog files remain the static and portable fallbacks.

When deliberately changing `BookManifest`, regenerate the tracked schema:

```sh
UV_CACHE_DIR=.uv-cache uv run --offline book-viewer-schema --output schemas/book.schema.json
```

Keep ordinary book packages and installed MathJax out of version control. The tracked `books/example/` package is the compatibility fixture and must contain its source PDF, aligned Markdown editions, assets, and generated browser metadata. Validate all locally present manifests so application changes remain compatible with the current external library.

## Development workflow

Use uv and the project-specific `.venv`:

```sh
UV_CACHE_DIR=.uv-cache uv sync --all-groups --locked
```

Keep Python boundaries strictly typed, validate external data with Pydantic, and add focused tests for behavior changes. Preserve the lightweight frontend and chapter-lazy rendering model when refactoring.

Install the commit hook once per clone:

```sh
UV_CACHE_DIR=.uv-cache uv run pre-commit install
```

Run the complete gate before committing:

```sh
scripts/check.sh
```

The gate synchronizes locked dependencies, checks Ruff formatting and linting, runs Pyright in strict mode, runs Pytest with branch coverage and an 80% minimum, and validates every external manifest currently under `books/`.

Build distributable artifacts with `scripts/build-binary.sh`. Install the optional thin offline MathJax runtime with `uv run book-viewer-install-mathjax` before building when the executable must render equations without network access.
