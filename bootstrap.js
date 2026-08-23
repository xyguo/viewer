(() => {
  "use strict";

  const SUPPORTED_BOOK_SCHEMA_VERSION = 2;
  const MATHJAX_URLS = [
    "vendor/mathjax/es5/tex-chtml.js",
    "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js"
  ];
  const PRELOADED_TEX_PACKAGES = new Set([
    "ams", "autoload", "configmacros", "newcommand", "noundefined", "require"
  ]);
  const catalogPage = document.querySelector("#catalog-page");
  const catalogCount = document.querySelector("#catalog-count");
  const catalogAlert = document.querySelector("#catalog-alert");
  const catalogEmpty = document.querySelector("#catalog-empty");
  const catalogEmptyMessage = document.querySelector("#catalog-empty-message");
  const bookList = document.querySelector("#book-list");
  const readerShell = document.querySelector(".app-shell");
  const skipLink = document.querySelector("#skip-link");

  function fail(message) {
    window.BookViewer?.showLoadError(message);
  }

  function configureMathJax(documentData) {
    const packages = documentData.mathjax?.packages || [];
    const macros = documentData.mathjax?.macros || {};
    window.MathJax = {
      loader: {
        load: packages
          .filter((name) => !PRELOADED_TEX_PACKAGES.has(name.toLowerCase()))
          .map((name) => `[tex]/${name}`)
      },
      tex: {
        packages: { "[+]": packages },
        inlineMath: [["$", "$"], ["\\(", "\\)"]],
        displayMath: [["$$", "$$"], ["\\[", "\\]"]],
        tags: "ams",
        macros
      },
      options: {
        enableMenu: false,
        skipHtmlTags: ["script", "noscript", "style", "textarea", "pre", "code"]
      },
      startup: {
        typeset: false,
        ready() {
          window.MathJax.startup.defaultReady();
          window.MathJax.startup.promise.then(() => {
            window.dispatchEvent(new Event("mathjax-ready"));
          });
        }
      }
    };
  }

  function loadMathJax(urlIndex = 0) {
    const script = document.createElement("script");
    script.src = MATHJAX_URLS[urlIndex];
    script.defer = true;
    script.onerror = () => {
      script.remove();
      if (urlIndex + 1 < MATHJAX_URLS.length) {
        loadMathJax(urlIndex + 1);
        return;
      }
      console.error("MathJax could not be loaded; formulas will remain in LaTeX form.");
    };
    document.head.append(script);
  }

  function showCatalog(message = "") {
    const catalog = window.BOOK_VIEWER_CATALOG;
    const entries = Object.entries(catalog?.books || {})
      .filter(([, entry]) => entry?.title && entry?.dataFile)
      .sort(([leftSlug], [rightSlug]) => {
        if (leftSlug === catalog?.defaultBook) return -1;
        if (rightSlug === catalog?.defaultBook) return 1;
        return leftSlug.localeCompare(rightSlug);
      });

    document.title = "Library | Parallel Book Viewer";
    readerShell.hidden = true;
    catalogPage.hidden = false;
    skipLink.href = "#catalog-main";
    skipLink.textContent = "Skip to book catalog";
    catalogAlert.hidden = !message;
    catalogAlert.textContent = message;
    bookList.replaceChildren();

    const bookCount = entries.length;
    catalogCount.textContent = `${bookCount.toLocaleString()} ${bookCount === 1 ? "book" : "books"} available`;
    catalogEmpty.hidden = bookCount > 0;
    if (bookCount === 0 && message) {
      catalogEmptyMessage.textContent = "Rebuild the local catalog after adding or updating external books.";
    }

    entries.forEach(([slug, entry], index) => {
      bookList.append(createBookCard(slug, entry, index));
    });
  }

  function createBookCard(slug, entry, index) {
    const link = document.createElement("a");
    link.className = "book-card";
    link.href = `?book=${encodeURIComponent(slug)}`;
    link.setAttribute("aria-label", `Open ${entry.title}`);

    const topline = document.createElement("span");
    topline.className = "book-card-topline";

    const number = document.createElement("span");
    number.className = "book-number";
    number.textContent = String(index + 1).padStart(2, "0");
    topline.append(number);

    if (entry.sourceLabel && entry.targetLabel) {
      const languages = document.createElement("span");
      languages.className = "book-languages";
      languages.textContent = `${entry.sourceLabel} → ${entry.targetLabel}`;
      topline.append(languages);
    }

    const title = document.createElement("h2");
    title.textContent = entry.title;

    const description = document.createElement("p");
    description.textContent = entry.description || "Open the synchronized source and translation.";

    const action = document.createElement("span");
    action.className = "book-action";
    action.textContent = "Open reader →";

    link.append(topline, title, description, action);
    return link;
  }

  function showReader() {
    catalogPage.hidden = true;
    readerShell.hidden = false;
    skipLink.href = "#reader";
    skipLink.textContent = "Skip to reader";
  }

  function loadSelectedBook() {
    const catalog = window.BOOK_VIEWER_CATALOG;
    if (!catalog?.books || !catalog.defaultBook) {
      showCatalog("The local book catalog is missing or invalid.");
      return;
    }
    if (catalog.schemaVersion !== SUPPORTED_BOOK_SCHEMA_VERSION) {
      showCatalog("The local book catalog is incompatible with this viewer version.");
      return;
    }

    const requestedSlug = new URLSearchParams(location.search).get("book");
    if (!requestedSlug) {
      showCatalog();
      return;
    }

    const entry = catalog.books[requestedSlug];
    if (!entry?.dataFile) {
      showCatalog(`The requested book '${requestedSlug}' is not available.`);
      return;
    }

    showReader();
    const script = document.createElement("script");
    script.src = entry.dataFile;
    script.onload = () => {
      const documentData = window.BOOK_VIEWER_DOCUMENT;
      if (!documentData || documentData.slug !== requestedSlug) {
        fail(`The data loaded for '${requestedSlug}' is missing or inconsistent.`);
        return;
      }
      if (documentData.schemaVersion !== SUPPORTED_BOOK_SCHEMA_VERSION) {
        fail(`The data for '${requestedSlug}' is incompatible with this viewer version. Rebuild it.`);
        return;
      }
      configureMathJax(documentData);
      window.BookViewer.initialize(documentData);
      loadMathJax();
    };
    script.onerror = () => fail(`The data file for '${requestedSlug}' could not be loaded.`);
    document.head.append(script);
  }

  loadSelectedBook();
})();
