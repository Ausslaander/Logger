from collections import defaultdict
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


class ExcelExporter:
    """Экспорт данных испытания в Excel."""

    @staticmethod
    def export(
        file_path: str,
        exp_data,
        comments: list[tuple],
        measurements=(),
    ):
        """
        Создаёт Excel-книгу с общими данными, комментариями и измерениями.

        Args:
            file_path: путь для сохранения XLSX-файла.
            exp_data: объект ExpData с данными испытания.
            comments: список комментариев из DatabaseAccessor.
                      Формат записи:
                      (id, created_at, last_edited, text).
        """

        workbook = Workbook()

        # Лист с общими данными испытания.
        general_sheet = workbook.active
        general_sheet.title = "Общие данные"

        general_sheet.append(["Параметр", "Значение"])

        general_data = [
            ("Номер испытания", exp_data.exp_id),
            ("Изделие", exp_data.product_name),
            ("Исполнитель", exp_data.executor_name),
            ("Дата испытания", exp_data.exp_date),
            ("Описание", exp_data.description),
        ]

        for parameter, value in general_data:
            general_sheet.append([parameter, value])

        # Лист с комментариями.
        comments_sheet = workbook.create_sheet("Комментарии")

        comments_sheet.append([
            "Время создания",
            "Последнее изменение",
            "Комментарий",
        ])

        for comment_id, created_at, last_edited, text in comments:
            comments_sheet.append([
                created_at,
                last_edited,
                text,
            ])

        groups = defaultdict(list)
        for row in measurements:
            groups[row.device].append(row)
        for device, rows in groups.items():
            title = re.sub(r"[\\/*?:\[\]]", " ", device.replace(" / ", " "))
            sheet = workbook.create_sheet(title[:31])
            columns = tuple(dict.fromkeys(column for row in rows for column in row.columns))
            sheet.append(("Временная метка", *columns, "Примечание"))
            for row in rows:
                sheet.append(row.cells(columns))

        for sheet in workbook.worksheets:
            for cell in sheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(
                    fill_type="solid",
                    fgColor="4472C4",
                )
                cell.alignment = Alignment(
                    horizontal="center",
                    vertical="center",
                    wrap_text=True,
                )

            sheet.freeze_panes = "A2"

            for row in sheet.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)

            for column in sheet.columns:
                column_letter = get_column_letter(column[0].column)

                max_length = max(
                    len(str(cell.value or ""))
                    for cell in column
                )

                sheet.column_dimensions[column_letter].width = min(
                    max(max_length + 2, 15),
                    60,
                )

        # Сохраняем книгу.
        workbook.save(file_path)
