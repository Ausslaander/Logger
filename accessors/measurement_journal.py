import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class MeasurementRow:
    id: str
    device: str
    timestamp: str
    columns: tuple[str, ...]
    values: tuple
    note: str
    deleted: bool = False

    def cells(self, columns: tuple[str, ...]) -> tuple:
        values = dict(zip(self.columns, self.values))
        return (self.timestamp, *(values.get(column, "—") for column in columns), self.note)


class MeasurementJournal:
    """Хранит несохранённые строки и удаления рядом с файлом испытания."""

    def __init__(self, experiment_path: str | None):
        path = Path(experiment_path).resolve() if experiment_path else None
        self.path = path.with_name(path.name + ".measurements-pending") if path else None

    def exists(self) -> bool:
        return self.path is not None and self.path.exists()

    def clear(self):
        if self.path is not None:
            self.path.unlink(missing_ok=True)

    @staticmethod
    def _ensure_table(connection):
        connection.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id TEXT PRIMARY KEY, device TEXT NOT NULL, timestamp TEXT NOT NULL,
                columns_json TEXT NOT NULL, values_json TEXT NOT NULL,
                note TEXT NOT NULL, deleted INTEGER NOT NULL
            )
        """)

    @staticmethod
    def _write(connection, row: MeasurementRow):
        connection.execute("""
            INSERT INTO measurements VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET deleted = excluded.deleted
        """, (
            row.id, row.device, row.timestamp, json.dumps(row.columns, ensure_ascii=False),
            json.dumps(row.values, ensure_ascii=False), row.note, row.deleted,
        ))

    def append(self, rows: list[MeasurementRow]):
        if self.path is None:
            raise ValueError("Сначала сохраните испытание.")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self._ensure_table(connection)
            for row in rows:
                self._write(connection, row)

    def delete(self, row: MeasurementRow):
        self.append([replace(row, deleted=True)])

    @staticmethod
    def _read(connection) -> list[MeasurementRow]:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='measurements'"
        ).fetchone():
            return []
        return [
            MeasurementRow(row_id, device, timestamp, tuple(json.loads(columns)),
                           tuple(json.loads(values)), note, bool(deleted))
            for row_id, device, timestamp, columns, values, note, deleted in connection.execute("""
                SELECT id, device, timestamp, columns_json, values_json, note, deleted
                FROM measurements ORDER BY rowid
            """)
        ]

    def pending_rows(self) -> list[MeasurementRow]:
        if not self.exists():
            return []
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
            return self._read(connection)

    def rows(self, connection) -> list[MeasurementRow]:
        rows = {row.id: row for row in self._read(connection)}
        for row in self.pending_rows():
            if row.deleted:
                rows.pop(row.id, None)
            else:
                rows[row.id] = row
        return list(rows.values())

    def apply(self, connection):
        with connection:
            self._ensure_table(connection)
            for row in self.pending_rows():
                if row.deleted:
                    connection.execute("DELETE FROM measurements WHERE id = ?", (row.id,))
                else:
                    self._write(connection, row)
