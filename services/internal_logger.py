
from enum import Enum
from datetime import datetime

from PyQt6.QtWidgets import QPlainTextEdit
from PyQt6.QtGui import QTextCursor


class LogLevel(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class InternalLogger:
    """Класс для вывода сообщений во внутренний журнал."""

    _output: QPlainTextEdit | None = None
    _status_message: str | None = None

    @staticmethod
    def initialize(output: QPlainTextEdit):
        """Устанавливает виджет для вывода сообщений."""
        InternalLogger._output = output
        InternalLogger._status_message = None

    @staticmethod
    def _format_message(
        message: str,
        level: LogLevel | None = LogLevel.INFO,
    ) -> str:
        """Форматирует сообщение с текущим временем и уровнем."""
        time = datetime.now().strftime("%H:%M:%S")

        if level is None:
            return f"[{time}] {message}"

        return f"[{time}] [{level.value}] {message}"

    @staticmethod
    def _remove_status():
        """Удаляет ранее выведенную строку статуса."""
        output = InternalLogger._output

        if output is None or InternalLogger._status_message is None:
            return

        cursor = output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Удаляем последнюю строку, если это статусное сообщение.
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)

        if cursor.selectedText() == InternalLogger._status_message:
            cursor.removeSelectedText()
            cursor.deleteChar()

        InternalLogger._status_message = None
        output.setTextCursor(cursor)

    @staticmethod
    def log(message: str, level: LogLevel = LogLevel.INFO):
        """Добавляет обычное сообщение в журнал."""
        output = InternalLogger._output

        if output is None:
            return

        # Перед обычным сообщением удаляем временный статус.
        InternalLogger._remove_status()

        formatted_message = InternalLogger._format_message(
            message,
            level,
        )
        output.appendPlainText(formatted_message)

    @staticmethod
    def update_status(message: str):
        """
        Выводит временный статус или заменяет предыдущий.
        Не добавляет новую строку при каждом обновлении.
        """
        output = InternalLogger._output

        if output is None:
            return

        InternalLogger._remove_status()

        formatted_message = InternalLogger._format_message(
            message,
            level=None,
        )

        output.appendPlainText(formatted_message)
        InternalLogger._status_message = formatted_message

    @staticmethod
    def clear_status():
        """Удаляет временный статус из журнала."""
        InternalLogger._remove_status()



