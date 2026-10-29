from PyQt6.QtWidgets import QFileDialog, QWidget


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

    def select_save_file(self, parent: QWidget) -> str:
        """
        Открывает диалоговое окно для выбора места сохранения файла.

        :param parent: родительское Qt-окно.
        :return: путь к выбранному файлу или пустая строка,
                 если сохранение было отменено.
        """
        file_path, _ = QFileDialog.getSaveFileName(
            parent,
            "Сохранить файл",
            "",
            "SQLite database (*.sqlite)"
        )

        return file_path

    def select_save_excel_file(self, parent: QWidget) -> str:
        file_path, _ = QFileDialog.getSaveFileName(
            parent,
            "Экспорт в Excel",
            "",
            "Excel Workbook (*.xlsx)",
        )

        if file_path and not file_path.lower().endswith(".xlsx"):
            file_path += ".xlsx"

        return file_path
