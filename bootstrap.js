(() => {
  "use strict";

  const SUPPORTED_BOOK_SCHEMA_VERSION = 1;
  const MATHJAX_URL = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js";

  function fail(message) {
    window.BookViewer?.showLoadError(message);
  }

  function configureMathJax(documentData) {
    const packages = documentData.mathjax?.packages || [];
    const macros = documentData.mathjax?.macros || {};
    window.MathJax = {
      loader: { load: packages.map((name) => `[tex]/${name}`) },
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
        ready() {
          window.MathJax.startup.defaultReady();
          window.MathJax.startup.promise.then(() => {
            window.dispatchEvent(new Event("mathjax-ready"));
          });
        }
      }
    };
  }

  function loadMathJax() {
    const script = document.createElement("script");
    script.src = MATHJAX_URL;
    script.defer = true;
    script.onerror = () => {
      console.error("MathJax could not be loaded; formulas will remain in LaTeX form.");
    };
    document.head.append(script);
  }

  function loadSelectedBook() {
    const catalog = window.BOOK_VIEWER_CATALOG;
    if (!catalog?.books || !catalog.defaultBook) {
      fail("The book catalog is missing or invalid.");
      return;
    }
    if (catalog.schemaVersion !== SUPPORTED_BOOK_SCHEMA_VERSION) {
      fail("The local book catalog is incompatible with this viewer version. Rebuild it.");
      return;
    }

    const requestedSlug = new URLSearchParams(location.search).get("book");
    const slug = requestedSlug || catalog.defaultBook;
    const entry = catalog.books[slug];
    if (!entry?.dataFile) {
      fail(`The requested book '${slug}' is not in the catalog.`);
      return;
    }

    const script = document.createElement("script");
    script.src = entry.dataFile;
    script.onload = () => {
      const documentData = window.BOOK_VIEWER_DOCUMENT;
      if (!documentData || documentData.slug !== slug) {
        fail(`The data loaded for '${slug}' is missing or inconsistent.`);
        return;
      }
      if (documentData.schemaVersion !== SUPPORTED_BOOK_SCHEMA_VERSION) {
        fail(`The data for '${slug}' is incompatible with this viewer version. Rebuild it.`);
        return;
      }
      configureMathJax(documentData);
      window.BookViewer.initialize(documentData);
      loadMathJax();
    };
    script.onerror = () => fail(`The data file for '${slug}' could not be loaded.`);
    document.head.append(script);
  }

  loadSelectedBook();
})();
