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

    # def select_save_excel_file(self, parent: QWidget) -> str:
    #     file_path, _ = QFileDialog.getSaveFileName(
    #         parent,
    #         "Экспорт в Excel",
    #         "",
    #         "Excel Workbook (*.xlsx)",
    #     )
    #
    #     if file_path and not file_path.lower().endswith(".xlsx"):
    #         file_path += ".xlsx"
    #
    #     return file_path

    def select_save_as_file(self, parent: QWidget) -> tuple[str, str]:
        """
        Выбирает путь и формат сохранения.

        Возвращает:
            (file_path, format_name), где format_name — 'sqlite' или 'xlsx'.
            При отмене возвращает ('', '').
        """
        filters = {
            "SQLite database (*.sqlite)": "sqlite",
            "Excel Workbook (*.xlsx)": "xlsx",
        }

        file_path, selected_filter = QFileDialog.getSaveFileName(
            parent,
            "Сохранить как",
            "",
            ";;".join(filters.keys()),
            "SQLite database (*.sqlite)",
        )

        if not file_path or selected_filter not in filters:
            return "", ""

        format_name = filters[selected_filter]
        extension = ".sqlite" if format_name == "sqlite" else ".xlsx"

        if not file_path.lower().endswith(extension):
            file_path += extension

        return file_path, format_name
