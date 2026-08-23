"""Contract tests for the static catalog and reader entry points."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


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


def load_markup(viewer_root: Path) -> MarkupInspector:
    inspector = MarkupInspector()
    inspector.feed((viewer_root / "index.html").read_text(encoding="utf-8"))
    return inspector


def test_catalog_is_the_visible_startup_surface() -> None:
    viewer_root = Path(__file__).resolve().parents[1]
    markup = load_markup(viewer_root)

    assert "hidden" not in markup.by_id("catalog-page").attributes
    assert "hidden" in next(
        element.attributes
        for element in markup.elements
        if "app-shell" in (element.attributes.get("class") or "").split()
    )
    assert markup.by_id("book-list").attributes["aria-label"] == "Available books"
    assert markup.by_id("skip-link").attributes["href"] == "#catalog-main"


def test_reader_links_back_to_catalog_and_bootstrap_routes_by_book() -> None:
    viewer_root = Path(__file__).resolve().parents[1]
    markup = load_markup(viewer_root)
    bootstrap = (viewer_root / "bootstrap.js").read_text(encoding="utf-8")

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
    assert "link.href = `?book=${encodeURIComponent(slug)}`" in bootstrap
