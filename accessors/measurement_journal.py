import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime
from math import isfinite
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

    def append(self, rows: list[MeasurementRow], timeout: float = 5):
        if self.path is None:
            raise ValueError("Сначала сохраните испытание.")
        with closing(sqlite3.connect(self.path, timeout=timeout)) as connection, connection:
            self._ensure_table(connection)
            for row in rows:
                self._write(connection, row)

    def delete(self, row: MeasurementRow):
        self.append([replace(row, deleted=True)])

    @staticmethod
    def validate_row(row: MeasurementRow):
        try:
            if not all(isinstance(value, str) for value in (
                row.id, row.device, row.timestamp, row.note,
            )):
                raise ValueError("неверный формат текстовых полей")
            datetime.fromisoformat(row.timestamp).timestamp()
            if not isinstance(row.columns, (list, tuple)) or not all(
                isinstance(column, str) for column in row.columns
            ):
                raise ValueError("неверные названия параметров")
            if not isinstance(row.values, (list, tuple)):
                raise ValueError("неверный формат значений")
            if len(row.values) != len(row.columns) and not (row.note and not row.values):
                raise ValueError("количество значений не соответствует параметрам")
            for value in row.values:
                if not isinstance(value, (int, float, str, type(None))):
                    raise ValueError("неверный тип показания")
                if isinstance(value, (int, float)) and not isfinite(value):
                    raise ValueError("нечисловое или бесконечное показание")
            if row.deleted not in (False, True):
                raise ValueError("неверная отметка удаления")
        except (ValueError, TypeError, OverflowError, OSError) as error:
            raise ValueError(f"Некорректная запись измерения {row.id!r}: {error}") from error

    @staticmethod
    def _read(connection) -> list[MeasurementRow]:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='measurements'"
        ).fetchone():
            return []
        rows = []
        try:
            records = connection.execute("""
                SELECT id, device, timestamp, columns_json, values_json, note, deleted
                FROM measurements ORDER BY rowid
            """)
            for row_id, device, timestamp, columns, values, note, deleted in records:
                row = MeasurementRow(
                    row_id, device, timestamp, json.loads(columns),
                    json.loads(values), note, deleted,
                )
                MeasurementJournal.validate_row(row)
                rows.append(replace(row, columns=tuple(row.columns), values=tuple(row.values)))
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise ValueError(f"Не удалось прочитать измерения: {error}") from error
        return rows

    def pending_rows(self) -> list[MeasurementRow]:
        if not self.exists():
            return []
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
            return self._read(connection)

    def rows(self, connection, pending=None) -> list[MeasurementRow]:
        rows = {row.id: row for row in self._read(connection)}
        for row in self.pending_rows() if pending is None else pending:
            if row.deleted:
                rows.pop(row.id, None)
            else:
                rows[row.id] = row
        return list(rows.values())

    def apply(self, connection, pending=None):
        with connection:
            self._ensure_table(connection)
            for row in self.pending_rows() if pending is None else pending:
                if row.deleted:
                    connection.execute("DELETE FROM measurements WHERE id = ?", (row.id,))
                else:
                    self._write(connection, row)
