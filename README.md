# PCP Proof Reader

This is a lightweight, zero-build reader for the Japanese and English editions of *Proof of the PCP Theorem*.

## Open the offline reader

Open `index.html` directly in a browser. Both full documents are already embedded in `document-data.js`, so the Markdown files do not need to be fetched at runtime. MathJax is loaded from a CDN; an internet connection is needed for typeset mathematics unless you replace that script with a local MathJax copy.

The offline reader supports:

- sentence-aligned side-by-side reading;
- synchronized scrolling using the first visible sentence as the anchor;
- click-to-highlight and click-to-align behavior;
- Japanese-only and English-only reading with counterpart popovers;
- chapter and section navigation; and
- responsive keyboard-accessible controls.

## Sentence mapping

Both Markdown files use matching `<span class="segment" data-seg="...">` wrappers. The boundary rule is intentionally mechanical: headings and captions are one segment, while prose is split at ordinary Japanese or English sentence-final punctuation. A display formula is kept as one block between its surrounding prose segments. The same `data-seg` value identifies each Japanese unit and its English counterpart.

## Use live translation

Live mode uses a tiny local Python server as a same-origin proxy to a llama.cpp server exposed through an SSH tunnel. By default, it calls `http://127.0.0.1:8080/v1/chat/completions` with the model `tencent-hy-mt`. No API key is required.

First establish the SSH tunnel so the remote llama.cpp service is available on local port `8080`. Then start the reader server:

```sh
cd /Users/xyguo/Programs/Study/Language/textbook/viewer
python3 server.py
```

Open `http://127.0.0.1:8000` and select **Live translation**. The server sends the clicked Japanese sentence plus up to two sentences on either side as context, while requesting output for only the clicked sentence.

The backend can be overridden when needed:

```sh
LLAMA_CPP_BASE_URL="http://127.0.0.1:8080/v1" \
TRANSLATION_MODEL="tencent-hy-mt" \
python3 server.py
```

## Rebuild after editing the Markdown

The delivered page is already built. To regenerate its embedded document data after editing either Markdown file, run:

```sh
cd /Users/xyguo/Programs/Study/Language/textbook/viewer
python3 build_data.py
```

The rebuild script validates that the Japanese and English files have exactly the same ordered `data-seg` identifiers, then uses Pandoc to render their controlled Markdown into static HTML. Pandoc is a build-time tool only; the finished reader has no Node.js or Python runtime dependency in offline mode.
