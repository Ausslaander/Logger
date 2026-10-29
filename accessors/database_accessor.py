import sqlite3

from models.exp_data import ExpData
from datetime import datetime
from pathlib import Path

import os
import sqlite3
import tempfile


class DatabaseAccessor:
    """
    Отвечает за создание, открытие, чтение и сохранение
    SQLite-базы данных испытания.
    """

    def __init__(self):
        self.connection = None
        self.in_memory_database = False

    def create_database(self):
        """
            Создаёт новую базу данных SQLite в RAM.
            База данных пока не сохранена на ПК.
        """
        if self.connection is not None:
            self.connection.close()

        # Создаём базу данных в оперативной памяти.
        self.connection = sqlite3.connect(":memory:")
        self.in_memory_database = True

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
        Открывает существующую базу данных SQLite.

        Новое соединение становится текущим только после проверки
        структуры базы и наличия данных испытания.
        При ошибке прежнее соединение сохраняется.
        """
        if not Path(file_path).is_file():
            raise FileNotFoundError(
                f"Файл базы данных не найден: {file_path}"
            )

        new_connection = None

        try:
            new_connection = sqlite3.connect(
                file_path,
                timeout=5,
            )

            self._validate_database(new_connection)

        except Exception:
            if new_connection is not None:
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
        self.in_memory_database = False

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

        self.connection.execute("""
            UPDATE exp
            SET
                exp_id             = ?,
                product_name       = ?,
                executor_name      = ?,
                exp_date           = ?,
                description        = ?
            WHERE id = 1
        """, (
            exp_data.exp_id,
            exp_data.product_name,
            exp_data.executor_name,
            exp_data.exp_date,
            exp_data.description
        ))

        self.connection.commit()

    def save_database(self, file_path: str):
        """
        Сохраняет текущую базу данных.

        Для базы в RAM:
        1. Создаёт временный SQLite-файл.
        2. Копирует в него данные.
        3. Проверяет корректность базы.
        4. Атомарно заменяет файл назначения.
        5. Переключается на файловое соединение.

        Для уже файловой базы фиксирует изменения через commit().
        """
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")

        # Для уже сохранённой базы достаточно зафиксировать изменения.
        if not self.in_memory_database:
            self.connection.commit()
            return

        destination_path = Path(file_path).resolve()
        destination_dir = destination_path.parent

        if not destination_dir.is_dir():
            raise FileNotFoundError(
                f"Каталог назначения не существует: {destination_dir}"
            )

        temporary_path = None
        new_connection = None

        try:
            # Временный файл создаётся в том же каталоге,
            # чтобы os.replace() мог выполнить атомарную замену.
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination_path.stem}_",
                suffix=".sqlite",
                dir=destination_dir,
            )
            os.close(file_descriptor)
            temporary_path = Path(temporary_name)

            # Копируем базу во временный файл.
            target = sqlite3.connect(str(temporary_path), timeout=5)

            try:
                self.connection.backup(target)
                self._validate_database(target)
            finally:
                # В Windows обязательно закрываем соединение
                # до попытки заменить файл.
                target.close()

            # К этому моменту временная база уже закрыта.
            os.replace(temporary_path, destination_path)
            temporary_path = None

            # Проверяем возможность открыть итоговый файл.
            new_connection = sqlite3.connect(
                str(destination_path),
                timeout=5,
            )
            self._validate_database(new_connection)

            # Переключаемся на файловую базу только после проверки.
            old_connection = self.connection
            old_connection.close()

            self.connection = new_connection
            self.in_memory_database = False
            new_connection = None

        finally:
            if new_connection is not None:
                new_connection.close()

            # Удаляем временный файл, если он ещё существует.
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass


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
            ORDER BY created_at
        """)
        return cursor.fetchall()

    def insert_comment(self, text: str):
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")
        created_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        last_edited = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        self.connection.execute("""
                                INSERT INTO comments (created_at, last_edited, text)
                                VALUES (?, ?, ?)
                                """, (created_at, last_edited, text))

        self.connection.commit()

    def update_comment(self, comment_id: int, text: str):
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")

        last_edited = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        self.connection.execute("""
                                UPDATE comments
                                SET last_edited = ?,
                                    text        = ?
                                WHERE id = ?
                                """, (last_edited, text, comment_id))

        self.connection.commit()

    def delete_comment(self, comment_id: int):
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")

        self.connection.execute("""
                                DELETE
                                FROM comments
                                WHERE id = ?
                                """, (comment_id,))

        self.connection.commit()