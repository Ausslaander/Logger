from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget


class FileAccessor:
    """
    Класс для взаимодействия приложения с файловой системой.
    """

    def select_open_file(self, parent: QWidget) -> str:
        """
        Открывает диалоговое окно для выбора существующего файла.

        :param parent: родительское Qt-окно.
        :return: путь к выбранному файлу или пустая строка,
                 если выбор был отменён.
        """
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            "Открыть файл",
            "",
            "SQLite database (*.sqlite)"
        )

        return file_path

    def select_save_file(self, parent: QWidget, exp_id: str = "") -> str:
        """
        Открывает диалоговое окно для выбора места сохранения файла.

        :param parent: родительское Qt-окно.
        :return: путь к выбранному файлу или пустая строка,
                 если сохранение было отменено.
        """
        dialog = QFileDialog(parent, "Сохранить испытание")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilter("SQLite database (*.sqlite)")
        dialog.setDefaultSuffix("sqlite")
        dialog.selectFile(exp_id.strip() or "Новое испытание")
        return dialog.selectedFiles()[0] if dialog.exec() else ""

    def select_save_as_file(
            self,
            parent: QWidget,
            exp_id: str = "",
    ) -> tuple[str, str]:
        """Выбирает путь и формат сохранения."""

        filters = {
            "SQLite database (*.sqlite)": "sqlite",
            "Excel Workbook (*.xlsx)": "xlsx",
        }

        default_name = exp_id.strip() or "Новое испытание"

        file_path, selected_filter = QFileDialog.getSaveFileName(
            parent,
            "Сохранить как",
            default_name,
            ";;".join(filters.keys()),
            "SQLite database (*.sqlite)",
        )

        if not file_path or selected_filter not in filters:
            return "", ""

        file_format = filters[selected_filter]
        extension = ".sqlite" if file_format == "sqlite" else ".xlsx"

        if not file_path.lower().endswith(extension):
            file_path += extension
            if Path(file_path).exists():
                buttons = QMessageBox.StandardButton
                if QMessageBox.question(
                    parent,
                    "Подтверждение замены",
                    f"Файл уже существует:\n{file_path}\n\nЗаменить его?",
                    buttons.Yes | buttons.No,
                    buttons.No,
                ) != buttons.Yes:
                    return "", ""

        return file_path, file_format
