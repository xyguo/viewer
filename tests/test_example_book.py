"""Compatibility checks for the tracked canonical example package."""

from __future__ import annotations

from pathlib import Path

from book_viewer.models import BookCatalog, BookChunkPayload, BookDocumentPayload


def load_javascript_payload(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text.rsplit(" = ", maxsplit=1)[1].removesuffix(";\n")


def test_tracked_example_is_a_complete_current_book_package() -> None:
    viewer_root = Path(__file__).resolve().parents[1]
    example_root = viewer_root / "books" / "example"
    source_pdf = example_root / "source.pdf"
    figure_path = example_root / "assets" / "figures" / "bsg-figure-1.png"

    assert source_pdf.read_bytes().startswith(b"%PDF-")
    assert figure_path.is_file()
    assert (example_root / "source.md").is_file()
    assert (example_root / "target.md").is_file()

    catalog = BookCatalog.model_validate_json(load_javascript_payload(example_root / "catalog.js"))
    assert catalog.default_book == "example"
    assert list(catalog.books) == ["example"]

    document = BookDocumentPayload.model_validate_json(
        load_javascript_payload(example_root / "document-data.js")
    )
    assert document.slug == "example"
    assert document.segment_count == 101
    assert len(document.chapters) == 5

    rendered_html: list[str] = []
    for chapter in document.chapters:
        assert chapter.target_data_file is not None
        for language, data_file in (
            ("source", chapter.source_data_file),
            ("target", chapter.target_data_file),
        ):
            chunk_path = viewer_root / data_file
            chunk = BookChunkPayload.model_validate_json(load_javascript_payload(chunk_path))
            assert chunk.slug == "example"
            assert chunk.chapter_id == chapter.id
            assert chunk.language == language
            rendered_html.append(chunk.html)

    assert sum("bsg-figure-1.png" in html for html in rendered_html) == 2
