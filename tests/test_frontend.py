"""Contract tests for the static catalog and reader entry points."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from book_viewer.models import SUPPORTED_LIVE_TARGET_LANGUAGES

VIEWER_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class Element:
    tag: str
    attributes: dict[str, str | None]


class MarkupInspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[Element] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.elements.append(Element(tag=tag, attributes=dict(attrs)))

    def by_id(self, element_id: str) -> Element:
        return next(
            element for element in self.elements if element.attributes.get("id") == element_id
        )


def read_asset(name: str) -> str:
    return (VIEWER_ROOT / name).read_text(encoding="utf-8")


def load_markup() -> MarkupInspector:
    inspector = MarkupInspector()
    inspector.feed(read_asset("index.html"))
    return inspector


def test_catalog_is_the_visible_startup_surface() -> None:
    markup = load_markup()

    assert "hidden" not in markup.by_id("catalog-page").attributes
    assert "hidden" in next(
        element.attributes
        for element in markup.elements
        if "app-shell" in (element.attributes.get("class") or "").split()
    )
    assert markup.by_id("book-list").attributes["aria-label"] == "Available books"
    assert markup.by_id("skip-link").attributes["href"] == "#catalog-main"


def test_reader_links_back_to_catalog_and_bootstrap_routes_by_book() -> None:
    markup = load_markup()
    bootstrap = read_asset("bootstrap.js")

    library_links = [
        element
        for element in markup.elements
        if "library-link" in (element.attributes.get("class") or "").split()
    ]
    assert len(library_links) == 1
    assert library_links[0].attributes["href"] == "index.html"
    assert 'new URLSearchParams(location.search).get("book")' in bootstrap
    assert "if (!requestedSlug)" in bootstrap
    assert "showCatalog();" in bootstrap
    assert 'const LOCAL_CATALOG_URL = "books/catalog.js";' in bootstrap
    assert 'const EXAMPLE_CATALOG_URL = "books/example/catalog.js";' in bootstrap
    assert "loadCatalogScript(LOCAL_CATALOG_URL" in bootstrap
    assert "loadCatalogScript(EXAMPLE_CATALOG_URL" in bootstrap
    assert "link.href = `?book=${encodeURIComponent(slug)}`" in bootstrap
    assert "typeset: false" in bootstrap
    assert '"vendor/mathjax/es5/tex-chtml.js"' in bootstrap
    assert "cdn.jsdelivr.net/npm/mathjax@3.2.2" in bootstrap
    assert "PRELOADED_TEX_PACKAGES" in bootstrap
    assert "loadMathJax(urlIndex + 1)" in bootstrap
    assert markup.by_id("previous-chapter").attributes["aria-label"] == "Previous chapter"
    assert markup.by_id("next-chapter").attributes["aria-label"] == "Next chapter"


def test_reader_uses_independent_viewport_scrollers() -> None:
    styles = read_asset("styles.css")

    assert ".app-shell {\n  height: 100%;\n  height: 100dvh;" in styles
    assert "grid-template-rows: auto auto minmax(0, 1fr);" in styles
    assert ".workspace {\n  min-height: 0;" in styles
    assert "overflow-y: auto;\n  overscroll-behavior: contain;" in styles
    assert ".pane-scroll {\n  min-height: 0;\n  height: auto;\n  overflow: auto;" in styles


def test_reader_loads_chapters_and_avoids_linear_scroll_scans() -> None:
    app = read_asset("app.js")

    assert "window.BOOK_VIEWER_CHUNKS" in app
    assert "function loadChapter(" in app
    assert "function prefetchAdjacentChapters(" in app
    assert "function firstVisibleSegment(" in app
    assert "while (low <= high)" in app
    assert "originSegments.find" not in app


def test_reader_persists_library_recency_and_reading_position() -> None:
    markup = load_markup()
    preferences = read_asset("preferences.js")
    bootstrap = read_asset("bootstrap.js")
    app = read_asset("app.js")
    binary_spec = read_asset("book-viewer.spec")
    scripts = [
        element.attributes.get("src")
        for element in markup.elements
        if element.tag == "script" and element.attributes.get("src")
    ]

    assert scripts[-5:] == ["dom.js", "preferences.js", "settings.js", "app.js", "bootstrap.js"]
    assert 'const STORAGE_PREFIX = "book-viewer-reading:v1:";' in preferences
    assert 'const READING_STATES_URL = "/api/reading-states";' in preferences
    assert "localStorage.getItem(storageKey(slug))" in preferences
    assert "localStorage.setItem(storageKey(slug)" in preferences
    assert "keepalive: true" in preferences
    assert "BookViewerPreferences.ready.then(loadCatalog)" in bootstrap
    assert "lastOpenedAt: Date.now()" in preferences
    assert "function progressPercent(slug)" in preferences
    assert "BookViewerPreferences.lastOpenedAt(slug)" in bootstrap
    assert "BookViewerPreferences.progressPercent(slug)" in bootstrap
    assert "rightOpenedAt - leftOpenedAt" in bootstrap
    assert "BookViewerPreferences.touch(requestedSlug)" in bootstrap
    assert "state.resumePosition = requestedSegment ? null : savedReadingPosition();" in app
    assert "sourceScrollTop: sourceScroll.scrollTop" in app
    assert "targetScrollTop: hasOfflineTranslation() ? targetScroll.scrollTop : null" in app
    assert "progressPercent: readingProgressPercent(segmentId)" in app
    assert 'window.addEventListener("pagehide", flushReadingPosition)' in app
    assert '(str(project_root / "preferences.js"), ".")' in binary_spec
    assert '(str(project_root / "settings.js"), ".")' in binary_spec
    assert '(str(project_root / "dom.js"), ".")' in binary_spec
    assert '(str(project_root / "catalog.css"), ".")' in binary_spec
    assert '(str(project_root / "settings.css"), ".")' in binary_spec

    catalog_styles = read_asset("catalog.css")
    assert "progress.textContent = `${progressPercent}% read`" in bootstrap
    assert ".book-card-footer" in catalog_styles
    assert ".book-progress" in catalog_styles


def test_reader_styles_numbered_highlighted_code_blocks() -> None:
    styles = read_asset("styles.css")

    assert ".document-content pre code > span::before" in styles
    assert "content: counter(code-line);" in styles
    assert ".document-content pre code .kw" in styles
    assert ".document-content pre code .st" in styles
    assert ".document-content pre code .co" in styles


def test_live_translation_exposes_supported_target_languages() -> None:
    markup = load_markup()
    app = read_asset("app.js")

    language_group = markup.by_id("live-language-controls")
    language_select = markup.by_id("live-target-language")
    option_values = [
        element.attributes.get("value") for element in markup.elements if element.tag == "option"
    ]

    assert "hidden" in language_group.attributes
    assert language_select.attributes["aria-label"] == "Live translation target language"
    assert option_values == list(SUPPORTED_LIVE_TARGET_LANGUAGES)
    assert "state.liveTargetLanguage" in app
    assert "const targetLanguage = state.liveTargetLanguage;" in app
    assert "target_language: targetLanguage" in app
    assert 'liveTargetLanguageSelect.addEventListener("change"' in app
    assert "book-viewer-live:${data.slug}:${targetLanguage}" in app


def test_settings_page_is_accessible_and_protects_api_keys() -> None:
    markup = load_markup()
    settings_script = read_asset("settings.js")

    settings_buttons = [
        element for element in markup.elements if "data-settings-open" in element.attributes
    ]
    assert len(settings_buttons) == 2
    assert all(button.attributes["aria-label"] == "Open settings" for button in settings_buttons)
    assert markup.by_id("settings-dialog").tag == "dialog"
    assert markup.by_id("settings-form").tag == "form"
    assert markup.by_id("settings-restart-dialog").tag == "dialog"
    assert 'const SETTINGS_URL = "/api/settings";' in settings_script
    assert (
        'if (field.sensitive || field.inputType === "password") return "password";'
        in settings_script
    )
    assert "Stored value hidden; enter to replace" in settings_script
    assert "A key is stored in your OS keyring" in settings_script
    assert 'note.className = "settings-note";' in settings_script
    assert "restartDialog.showModal()" in settings_script


def test_source_only_books_force_live_translation_mode() -> None:
    app = read_asset("app.js")
    bootstrap = read_asset("bootstrap.js")

    assert "data.hasOfflineTranslation !== false" in app
    assert 'state.mode = offlineTranslationAvailable ? "offline" : "online";' in app
    assert 'state.view = offlineTranslationAvailable ? "both" : "source";' in app
    assert 'if (mode === "offline" && !hasOfflineTranslation()) return;' in app
    assert (
        'button.disabled = button.dataset.modeChoice === "offline" && !hasOfflineTranslation();'
        in app
    )
    assert 'hasOfflineTranslation()\n        ? loadChunk(chapter, "target")' in app
    assert "entry.targetLabel\n        ? `${entry.sourceLabel} → ${entry.targetLabel}`" in bootstrap
