"""Tests for versioned local reader-data persistence."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from book_viewer.models import ReadingStateUpdate
from book_viewer.reader_data import LATEST_SCHEMA_VERSION, ReaderDataStore


def test_store_preserves_and_merges_reading_state_across_restarts(tmp_path: Path) -> None:
    database_path = tmp_path / "reader-data.sqlite3"
    store = ReaderDataStore(database_path)

    opened = store.update_reading_state(
        ReadingStateUpdate(
            book_slug="compiler-book",
            last_opened_at=1_000,
            updated_at=1_000,
        )
    )
    positioned = store.update_reading_state(
        ReadingStateUpdate(
            book_slug="compiler-book",
            chapter_id="chapter-3",
            segment_id="segment-27",
            progress_percent=38,
            source_scroll_top=1240,
            target_scroll_top=1318,
            updated_at=1_100,
        )
    )

    assert opened.last_opened_at == 1_000
    assert positioned.last_opened_at == 1_000
    assert positioned.chapter_id == "chapter-3"
    assert positioned.source_scroll_top == 1240

    reopened = ReaderDataStore(database_path)
    assert reopened.get_reading_state("compiler-book") == positioned
    assert reopened.list_reading_states() == [positioned]
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == LATEST_SCHEMA_VERSION
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            ).fetchall()
        }
        assert {"reader_book", "reading_state"} <= tables


def test_store_ignores_out_of_order_updates(tmp_path: Path) -> None:
    store = ReaderDataStore(tmp_path / "reader-data.sqlite3")
    current = store.update_reading_state(
        ReadingStateUpdate(
            book_slug="sample-book",
            chapter_id="new-chapter",
            updated_at=200,
        )
    )

    result = store.update_reading_state(
        ReadingStateUpdate(
            book_slug="sample-book",
            chapter_id="old-chapter",
            updated_at=100,
        )
    )

    assert result == current
    assert store.get_reading_state("sample-book") == current


def test_store_refuses_a_database_from_a_newer_viewer(tmp_path: Path) -> None:
    database_path = tmp_path / "reader-data.sqlite3"
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION + 1}")

    with pytest.raises(RuntimeError, match="newer viewer version"):
        ReaderDataStore(database_path)
