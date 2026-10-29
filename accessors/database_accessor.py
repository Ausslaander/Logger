import sqlite3

from models.exp_data import ExpData
from datetime import datetime


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
            Открывает существующий SQLite-файл.

            file_path: путь к SQLite-файлу.
        """
        if self.connection is not None:
            self.connection.close()

        self.connection = sqlite3.connect(file_path)
        self.in_memory_database = False

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
            Сохраняет текущую базу данных в указанный файл.
            Если БД находится в RAM, то она копируется в указанный файл.
            Если БД уже связана с файлом (работаем с существующей БД), то изменения уже внесены на моменте
            использования set_data, условие if не выполнится.

            file_path: путь к файлу SQLite, в который будет сохранена БД.
        """
        if self.connection is None:
            raise RuntimeError("Нет открытой базы данных")

        if self.in_memory_database:
            destination = sqlite3.connect(file_path)
            print("Создали destination")

            try:
                self.connection.backup(destination)
                print("Успешно сделали backup")
            finally:
                destination.close()

            self.connection.close()
            print("Закрыли соединение")
            self.connection = sqlite3.connect(file_path, timeout=5)
            print("Открыли соединение с файлом")
            self.in_memory_database = False


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