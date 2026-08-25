"""Versioned SQLite persistence for local reader data."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

from .models import ReadingState, ReadingStateUpdate

Migration = Callable[[sqlite3.Connection], None]


def _create_reading_state_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE reader_book (
            book_slug TEXT PRIMARY KEY NOT NULL,
            created_at INTEGER NOT NULL CHECK (created_at >= 0)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE reading_state (
            book_slug TEXT PRIMARY KEY NOT NULL
                REFERENCES reader_book(book_slug) ON DELETE CASCADE,
            chapter_id TEXT,
            segment_id TEXT,
            progress_percent INTEGER NOT NULL DEFAULT 0
                CHECK (progress_percent BETWEEN 0 AND 100),
            source_scroll_top REAL CHECK (source_scroll_top IS NULL OR source_scroll_top >= 0),
            target_scroll_top REAL CHECK (target_scroll_top IS NULL OR target_scroll_top >= 0),
            last_opened_at INTEGER NOT NULL DEFAULT 0 CHECK (last_opened_at >= 0),
            updated_at INTEGER NOT NULL CHECK (updated_at >= 0)
        )
        """
    )


MIGRATIONS: tuple[Migration, ...] = (_create_reading_state_schema,)
LATEST_SCHEMA_VERSION = len(MIGRATIONS)


class ReaderDataStore:
    """Own versioned reader data with one short-lived connection per operation."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("BEGIN EXCLUSIVE")
            current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current_version > LATEST_SCHEMA_VERSION:
                raise RuntimeError(
                    "Reader data was created by a newer viewer version "
                    f"({current_version} > {LATEST_SCHEMA_VERSION})."
                )
            for version, migration in enumerate(MIGRATIONS, start=1):
                if version <= current_version:
                    continue
                migration(connection)
                connection.execute(f"PRAGMA user_version = {version}")

    @staticmethod
    def _state_from_row(row: sqlite3.Row) -> ReadingState:
        return ReadingState.model_validate(dict(row))

    def list_reading_states(self) -> list[ReadingState]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM reading_state ORDER BY book_slug").fetchall()
        return [self._state_from_row(row) for row in rows]

    def get_reading_state(self, book_slug: str) -> ReadingState | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM reading_state WHERE book_slug = ?",
                (book_slug,),
            ).fetchone()
        return None if row is None else self._state_from_row(row)

    def update_reading_state(self, update: ReadingStateUpdate) -> ReadingState:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM reading_state WHERE book_slug = ?",
                (update.book_slug,),
            ).fetchone()
            existing = None if row is None else self._state_from_row(row)
            if existing is not None and update.updated_at < existing.updated_at:
                return existing

            values = (
                existing.model_dump()
                if existing is not None
                else ReadingState(
                    book_slug=update.book_slug,
                    updated_at=update.updated_at,
                ).model_dump()
            )
            changes = update.model_dump(exclude_unset=True, exclude_none=True)
            values.update(changes)
            state = ReadingState.model_validate(values)
            connection.execute(
                "INSERT OR IGNORE INTO reader_book (book_slug, created_at) VALUES (?, ?)",
                (state.book_slug, state.updated_at),
            )
            connection.execute(
                """
                INSERT INTO reading_state (
                    book_slug, chapter_id, segment_id, progress_percent,
                    source_scroll_top, target_scroll_top, last_opened_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_slug) DO UPDATE SET
                    chapter_id = excluded.chapter_id,
                    segment_id = excluded.segment_id,
                    progress_percent = excluded.progress_percent,
                    source_scroll_top = excluded.source_scroll_top,
                    target_scroll_top = excluded.target_scroll_top,
                    last_opened_at = excluded.last_opened_at,
                    updated_at = excluded.updated_at
                """,
                (
                    state.book_slug,
                    state.chapter_id,
                    state.segment_id,
                    state.progress_percent,
                    state.source_scroll_top,
                    state.target_scroll_top,
                    state.last_opened_at,
                    state.updated_at,
                ),
            )
        return state
