# Parallel Book Viewer

Parallel Book Viewer is a lightweight, sentence-aligned reader for translated books. The browser application and Python tooling are book-independent. Each book supplies only a strict manifest, generated document data, and its assets under `books/`.

The bundled book is the Japanese and English edition of *Proof of the PCP Theorem*.

## Project layout

```text
viewer/
├── app.js, bootstrap.js, index.html, styles.css  # generic static reader
├── books/
│   ├── catalog.js                               # available books
│   └── proof-of-pcp/                            # one isolated book package
│       ├── book.json                            # source and presentation manifest
│       ├── document-data.js                     # generated browser payload
│       └── assets/                              # book-specific figures
├── src/book_viewer/                             # typed builder and local server
├── tests/                                       # Python unit and HTTP tests
├── pyproject.toml                               # dependencies and quality policy
└── uv.lock                                      # reproducible dependency lock
```

## Set up the project

Install [uv](https://docs.astral.sh/uv/), then run:

```sh
cd /Users/xyguo/Programs/Study/Language/textbook/viewer
UV_CACHE_DIR=.uv-cache uv sync --all-groups --locked
```

uv creates and manages the project-specific `.venv` automatically. Python dependencies must not be installed globally.

Pandoc is also required when rebuilding a book. It is a build-time executable, not a Python or browser dependency.

## Read a book

For offline mode, open `index.html` directly. The complete source and target editions are embedded in the selected book's `document-data.js`. MathJax is loaded from a CDN, so typeset mathematics requires network access unless the script is vendored locally.

The default book comes from `books/catalog.js`. Select another catalog entry with a query parameter:

```text
index.html?book=another-book
```

The reader supports synchronized scrolling, sentence highlighting, counterpart popovers in one-language mode, and chapter navigation.

## Use live translation

Live mode needs the local server because browsers must not receive provider credentials or call the translation service directly. The only backend contract is an OpenAI-compatible Chat Completions API.

Copy the example configuration and set the complete endpoint URL and model identifier supplied by your provider:

```sh
cp .env.example .env
```

`.env` is loaded automatically and ignored by Git. Then run:

```sh
UV_CACHE_DIR=.uv-cache uv run book-viewer-serve
```

Open `http://127.0.0.1:8000`. There is deliberately no default backend. Without `LLM_CHAT_COMPLETIONS_URL` and `LLM_MODEL`, the static reader still works and live translation returns a configuration error.

The clicked source sentence is the only user message. Up to two neighboring sentences on each side are included in the system message as translation context.

For the current llama.cpp SSH tunnel, use:

```sh
VIEWER_HOST=127.0.0.1 \
VIEWER_PORT=8000 \
LLM_CHAT_COMPLETIONS_URL=http://127.0.0.1:8080/v1/chat/completions \
LLM_MODEL=tencent-hy-mt \
TRANSLATION_TIMEOUT_SECONDS=90 \
UV_CACHE_DIR=.uv-cache \
uv run book-viewer-serve
```

For a hosted provider using standard Bearer authentication, configure:

```sh
LLM_CHAT_COMPLETIONS_URL=https://provider.example/v1/chat/completions \
LLM_MODEL=provider-model-name \
LLM_API_KEY=replace-me \
UV_CACHE_DIR=.uv-cache \
uv run book-viewer-serve
```

Provider configuration:

- `LLM_CHAT_COMPLETIONS_URL`: complete Chat Completions endpoint; required with `LLM_MODEL`.
- `LLM_MODEL`: provider model identifier; required with the endpoint.
- `LLM_API_KEY`: optional secret, sent only by the local server.
- `LLM_API_KEY_HEADER`: authentication header name, defaulting to `Authorization`.
- `LLM_API_KEY_SCHEME`: authentication prefix, defaulting to `Bearer`; set it to an empty value for an unprefixed key.
- `LLM_EXTRA_HEADERS`: optional JSON object for provider-specific headers.
- `LLM_TEMPERATURE` and `LLM_MAX_TOKENS`: optional generation controls.
- `TRANSLATION_TIMEOUT_SECONDS`: upstream request timeout.

For example, a service expecting `api-key: <key>` can use `LLM_API_KEY_HEADER=api-key` and an empty `LLM_API_KEY_SCHEME`. No provider SDK is required.

## Add another book

Create `books/<slug>/book.json`. All book-specific values, including titles, language labels, Markdown paths, asset mapping, and MathJax macros, belong in this file.

```json
{
  "slug": "another-book",
  "title": "Another Book",
  "reader_title": "Another Book Reader",
  "description": "A sentence-aligned source and translation.",
  "source": {
    "language": "Japanese",
    "label": "日本語",
    "html_lang": "ja",
    "markdown": "../../../another-book-jp.md",
    "html_id_prefix": "source"
  },
  "target": {
    "language": "English",
    "label": "English",
    "html_lang": "en",
    "markdown": "../../../another-book-en.md",
    "html_id_prefix": "target"
  },
  "data_file": "document-data.js",
  "asset_rewrites": {
    "viewer/assets/": "books/another-book/assets/"
  },
  "mathjax": {
    "packages": ["ams"],
    "macros": {}
  }
}
```

Both Markdown editions must use matching wrappers such as:

```html
<span class="segment" data-seg="chapter-01-sentence-0001">Sentence text.</span>
```

The boundary rule is intentionally mechanical: headings and captions are one segment, prose is split at ordinary sentence-final punctuation, and a display formula remains one block between neighboring prose segments. Only the ordered `data-seg` values define the mapping. The builder rejects missing, duplicate, or differently ordered IDs, mismatched equation tags, mismatched figures, and missing local assets.

Put book-specific figures under `books/<slug>/assets/`. `asset_rewrites` maps paths found in the Markdown to paths relative to the generic `index.html`.

Add the new slug and generated data path to `books/catalog.js`, then build it:

```sh
UV_CACHE_DIR=.uv-cache uv run book-viewer-build --manifest books/another-book/book.json
```

Equation numbers written with LaTeX `\tag{...}` are preserved and checked across both editions.

## Quality gates

Run every required gate with:

```sh
scripts/check.sh
```

The gate performs:

- Ruff formatting verification and linting;
- Pyright in strict mode;
- Pytest with branch coverage; and
- an 80% minimum total coverage threshold enforced by `pyproject.toml`.

Individual commands are also available:

```sh
UV_CACHE_DIR=.uv-cache uv run --offline ruff format --check src tests
UV_CACHE_DIR=.uv-cache uv run --offline ruff check src tests
UV_CACHE_DIR=.uv-cache uv run --offline pyright
UV_CACHE_DIR=.uv-cache uv run --offline pytest
```
