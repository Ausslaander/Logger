from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

import os
import sqlite3
import tempfile

from models.exp_data import ExpData


class DatabaseAccessor:
    """
    Отвечает за создание, открытие, чтение и сохранение
    SQLite-базы данных испытания.
    """

    def __init__(self):
        self.connection = None
        self.comments_dirty = False

    def create_database(self):
        """
            Создаёт новую базу данных SQLite в RAM.
            База данных пока не сохранена на ПК.
        """
        if self.connection is not None:
            self.connection.close()

        # Создаём базу данных в оперативной памяти.
        self.connection = sqlite3.connect(":memory:")
        self.comments_dirty = False

        # Создаём таблицу с общими данными испытания.
        self.connection.execute("""
            CREATE TABLE exp
            (
                id                 INTEGER PRIMARY KEY,
                exp_id             TEXT,
                product_name       TEXT,
                executor_name      TEXT,
                exp_date           TEXT,
                description        TEXT
            )
        """)

        self.connection.execute("""
            CREATE TABLE comments
            (
                id INTEGER PRIMARY KEY,
                created_at TEXT,
                last_edited TEXT,
                text TEXT
            )
        """)

        # Создаём одну запись для текущего испытания.
        self.connection.execute("""
            INSERT INTO exp (
                exp_id,
                product_name,
                executor_name,
                exp_date,
                description
            )
            VALUES (?, ?, ?, ?, ?)
        """, ("", "", "", "", ""))

        self.connection.commit()

    def open_database(self, file_path: str):
        """
        Загружает рабочую копию существующей базы SQLite в память.
        """
        source_path = Path(file_path).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(
                f"Файл базы данных не найден: {file_path}"
            )

        source_uri = source_path.as_uri() + "?mode=ro"
        new_connection = sqlite3.connect(":memory:")

        try:
            with closing(sqlite3.connect(source_uri, uri=True)) as source:
                self._backup(source, new_connection)
            self._validate_database(new_connection)
        except Exception:
            new_connection.close()
            raise

        # Новая база проверена. Теперь можно заменить соединение.
        old_connection = self.connection

        try:
            if old_connection is not None:
                old_connection.close()
        except Exception:
            new_connection.close()
            raise

        self.connection = new_connection
        self.comments_dirty = False

    @staticmethod
    def _backup(source: sqlite3.Connection, target: sqlite3.Connection):
        def check_progress(status, _remaining, _total):
            if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise sqlite3.OperationalError("Файл базы данных занят.")

        source.backup(target, progress=check_progress)

    @contextmanager
    def stage_measurements(self, journal):
        """Подмешивает журнал к копии базы на время сохранения."""
        if not journal.exists():
            yield
            return

        original = self.connection
        staged = sqlite3.connect(":memory:")
        try:
            self._backup(original, staged)
            journal.apply(staged)
            self.connection = staged
            yield
        except BaseException:
            self.connection = original
            staged.close()
            raise
        else:
            original.close()

    @staticmethod
    def _validate_database(connection: sqlite3.Connection):
        """
        Проверяет целостность и совместимость базы с приложением.
        Вызывает исключение, если база не подходит.
        """
        # Проверяем целостность файла SQLite.
        result = connection.execute(
            "PRAGMA quick_check"
        ).fetchone()

        if result is None or result[0] != "ok":
            details = result[0] if result else "нет результата"
            raise ValueError(
                f"Ошибка проверки целостности SQLite: {details}"
            )

        # Проверяем наличие необходимых таблиц.
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

        required_tables = {"exp", "comments"}
        missing_tables = required_tables - tables

        if missing_tables:
            raise ValueError(
                "В базе отсутствуют необходимые таблицы: "
                + ", ".join(sorted(missing_tables))
            )

        # Проверяем столбцы таблицы испытания.
        exp_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(exp)"
            )
        }

        required_exp_columns = {
            "id",
            "exp_id",
            "product_name",
            "executor_name",
            "exp_date",
            "description",
        }

        missing_exp_columns = required_exp_columns - exp_columns

        if missing_exp_columns:
            raise ValueError(
                "В таблице exp отсутствуют столбцы: "
                + ", ".join(sorted(missing_exp_columns))
            )

        # Проверяем столбцы таблицы комментариев.
        comments_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(comments)"
            )
        }

        required_comments_columns = {
            "id",
            "created_at",
            "last_edited",
            "text",
        }

        missing_comments_columns = (
                required_comments_columns - comments_columns
        )

        if missing_comments_columns:
            raise ValueError(
                "В таблице comments отсутствуют столбцы: "
                + ", ".join(sorted(missing_comments_columns))
            )

        # Проверяем наличие записи текущего испытания.
        exp_record = connection.execute(
            """
            SELECT exp_id, product_name, executor_name,
                   exp_date, description
            FROM exp
            WHERE id = 1
            """
        ).fetchone()

        if exp_record is None:
            raise ValueError(
                "В базе отсутствует запись испытания с id = 1"
            )

    def get_data(self) -> ExpData:
        """
            Получает общие данные текущего испытания из базы данных.

            result: данные испытания.
        """
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")

        cursor = self.connection.execute("""
            SELECT
                exp_id,
                product_name,
                executor_name,
                exp_date,
                description
            FROM exp
            WHERE id = 1
        """)

        result = cursor.fetchone()

        if result is None:
            raise RuntimeError("Данные испытания не найдены")

        return ExpData(
            exp_id=result[0],
            product_name=result[1],
            executor_name=result[2],
            exp_date=result[3],
            description=result[4]
        )

    def set_data(self, exp_data: ExpData):
        """
            Записывает общие данные текущего испытания в базу данных.

            exp_data: данные испытания.
        """
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")

        self._write_data(self.connection, exp_data)

    @staticmethod
    def _write_data(connection: sqlite3.Connection, exp_data: ExpData):
        with connection:
            connection.execute("""
                UPDATE exp
                SET exp_id = ?,
                    product_name = ?,
                    executor_name = ?,
                    exp_date = ?,
                    description = ?
                WHERE id = 1
            """, (
                exp_data.exp_id,
                exp_data.product_name,
                exp_data.executor_name,
                exp_data.exp_date,
                exp_data.description,
            ))

    def save_database(self, file_path: str):
        """Сохраняет рабочую копию в текущий SQLite-файл."""
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")

        destination = Path(file_path).resolve()
        if not destination.exists():
            self.save_database_as(file_path)
            return

        destination_uri = destination.as_uri() + "?mode=rw"
        with closing(sqlite3.connect(destination_uri, uri=True)) as target:
            self._backup(self.connection, target)
        self.comments_dirty = False

    def is_open(self) -> bool:
        """
        Проверяет, открыта ли в данный момент база данных.

        :return: True, если база данных открыта.
        """
        return self.connection is not None

    def get_comments(self):
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")

        cursor = self.connection.execute("""
            SELECT id, created_at, last_edited, text
            FROM comments
            -- Даты хранятся как ДД.ММ.ГГГГ ЧЧ:ММ:СС.
            ORDER BY substr(created_at, 7, 4),
                     substr(created_at, 4, 2),
                     substr(created_at, 1, 2),
                     substr(created_at, 12), id
        """)
        return cursor.fetchall()

    def insert_comment(self, text: str):
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")
        created_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        with self.connection:
            self.connection.execute("""
                INSERT INTO comments (created_at, last_edited, text)
                VALUES (?, ?, ?)
            """, (created_at, created_at, text))
        self.comments_dirty = True

    def update_comment(self, comment_id: int, text: str):
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")

        last_edited = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        with self.connection:
            result = self.connection.execute("""
                UPDATE comments
                SET last_edited = ?, text = ?
                WHERE id = ?
            """, (last_edited, text, comment_id))
        if result.rowcount:
            self.comments_dirty = True

    def delete_comment(self, comment_id: int):
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")

        with self.connection:
            result = self.connection.execute(
                "DELETE FROM comments WHERE id = ?", (comment_id,)
            )
        if result.rowcount:
            self.comments_dirty = True

    def save_database_as(self, file_path: str):
        """Сохраняет рабочую копию базы по новому пути."""
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")

        destination = Path(file_path).resolve()

        if not destination.parent.is_dir():
            raise FileNotFoundError(
                f"Каталог назначения не существует: {destination.parent}"
            )

        temporary_path = None

        try:
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{destination.stem}_",
                suffix=".sqlite",
                dir=destination.parent,
            )
            os.close(fd)
            temporary_path = Path(temp_name)

            target = sqlite3.connect(str(temporary_path), timeout=5)
            try:
                self._backup(self.connection, target)
                self._validate_database(target)
            finally:
                target.close()

            # Временная база уже закрыта.
            os.replace(temporary_path, destination)
            temporary_path = None

            self.comments_dirty = False

        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
