# Parallel Book Viewer

A lightweight local reader for language study. It allows you to easily access the translation of any sentence when reading an article (written in a foreign language). You can also read the bilingual version of the article side by side, with sentence-level synchronization.

| Bilingual reading | Translation popup |
| --- | --- |
| ![Source and translation displayed side by side](docs/assets/reader-side-by-side.png) | ![Single-language view with its corresponding translation](docs/assets/reader-translation-popup.png) |

## Install and run

Install [uv](https://docs.astral.sh/uv/), clone this repository, enter its root, and run:

```sh
uv run book-viewer-serve
```

The server opens `http://127.0.0.1:8000` in the default browser. Pass `--no-open` when
running it in a headless environment or when you want to open the URL yourself.

When run from source, the app reads its library from the repository's `books/` directory.

To build a platform-specific standalone executable, run:

```sh
scripts/build-binary.sh
```

After building, the script asks whether to install the viewer. You can also run the install
script manually:

```sh
scripts/install-local.sh
```

Remove a per-user installation with:

```sh
scripts/uninstall-local.sh
```

The uninstaller never removes the book library and preserves reading history unless you choose
to delete it.

### Dependencies

- **Python 3.12 or newer and uv:** run the source server, install its small Python dependency set, and execute the book-building tools. Neither is required by the standalone executable.
- **Pandoc:** required only when building or rebuilding a book. It converts the paired Markdown editions to static HTML and produces syntax-highlighting tokens. It is not bundled with the standalone executable and is not needed to view an already-built book.
- **MathJax:** renders equations in the browser. The viewer loads it from a CDN by default; a local copy can be installed for offline use.
- **OpenAI-compatible Chat Completions service:** optional and used only for live translation.

## Add a book

Create a `books/` folder in the repository and put the document (PDF/EPUB/...) you want to read in it. Then point an AI agent (e.g. Claude/Codex) at the repository and ask it to use the project skill at `.agent/skills/create-viewer-book` to convert the PDF into the format accepted by the viewer. Roughly speeking, the skill tells the agent to extract text from the input
document, segment it to sentence level, and save it as a markdown that will later be converted to html for rendering. You can optionally ask the agent to also translate the document to another language.

Except for the small tracked `books/example/` package, book source files, translations, metadata, generated browser data, and assets under `books/` remain local and are intentionally excluded from Git.

## Live translation

Live translation requires an OpenAI-compatible Chat Completions service. Copy the example configuration:

```sh
cp .env.example .env
```

Set `LLM_CHAT_COMPLETIONS_URL` and `LLM_MODEL`; add `LLM_API_KEY` only when the provider requires it. Restart `book-viewer-serve` after changing the configuration. See [.env.example](.env.example) for the optional settings.

## Offline Math rendering

The viewer uses MathJax to render equations, which requires to connect to their CDN. If you want to use the viewer without internet, you can install a thin local MathJax runtime:

```sh
uv run book-viewer-install-mathjax
```

Run this before `scripts/build-binary.sh` to include MathJax in the standalone executable. The installed files under `vendor/mathjax/` are intentionally excluded from Git.
