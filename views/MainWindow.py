
from datetime import datetime
import os

from PyQt6 import uic
from PyQt6.QtCore import QDate, Qt, pyqtSlot, QThread
from PyQt6.QtWidgets import (
    QMainWindow,
    QDialog,
    QTableWidgetItem,
    QAbstractItemView,
    QHeaderView,
)

from config import MAIN_WINDOW_UI
from accessors.file_accessor import FileAccessor
from accessors.database_accessor import DatabaseAccessor
from services.internal_logger import InternalLogger as Logger
from services.internal_logger import LogLevel
from services.excel_exporter import ExcelExporter
from models.exp_data import ExpData
from views.CommentDialog import CommentDialog
from views.DeleteCommentDialog import DeleteCommentDialog
from views.DeviceWindow import DeviceWindow
from hardware.device_registry import (
    get_available_devices,
    get_device_module,
)
from hardware.device_search_worker import DeviceSearchWorker


class MainWindow(QMainWindow):
    """Главное окно приложения для работы с испытаниями."""

    def __init__(self):
        """Загружает интерфейс и инициализирует компоненты приложения."""
        super().__init__()

        uic.loadUi(MAIN_WINDOW_UI, self)

        self.file_accessor = FileAccessor()
        self.database_accessor = DatabaseAccessor()
        self.current_file_path = None

        self._device_search_thread = None
        self._device_search_worker = None
        self._found_device = None

        self._device1_window = None

        Logger.initialize(self.InternalLoggerWindow)

        self.CreateExp.clicked.connect(self.create_exp)
        self.OpenExp.clicked.connect(self.open_exp)
        self.SaveExp.clicked.connect(self.save_exp)
        self.SaveAsButton.clicked.connect(self.save_as_exp)
        self.Device1WindowButton.clicked.connect(self.device1_window)

        self.GenerateExpId.clicked.connect(self.generate_exp_id)
        self.TakeCurrentDate.clicked.connect(self.take_current_date)

        self.AddCommentButton.clicked.connect(self.add_comment)
        self.EditCommentButton.clicked.connect(self.edit_comment)
        self.DeleteCommentButton.clicked.connect(self.delete_comment)

        self.setup_comments_table()
        self.setup_device1_search()
        self.set_exp_editable(False)

    def setup_comments_table(self):
        """Настраивает отображение таблицы комментариев."""
        self.CommentsTable.setColumnCount(2)
        self.CommentsTable.setHorizontalHeaderLabels(
            ["Последнее изменение", "Комментарий"]
        )

        self.CommentsTable.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.CommentsTable.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.CommentsTable.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        header = self.CommentsTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 230)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.CommentsTable.setWordWrap(True)
        self.CommentsTable.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )

    def setup_device1_search(self):
        """Инициализирует интерфейс поиска прибора № 1."""
        self.Device1ComboBox.clear()
        self.Device1ComboBox.addItem("Выберите прибор", None)

        for device_id, display_name in get_available_devices():
            self.Device1ComboBox.addItem(display_name, device_id)

        self.Device1SearchButton.setEnabled(False)
        self.Device1WindowButton.setEnabled(False)
        self.Device1SearchStatusLine.setText("Прибор не выбран")

        self.Device1ComboBox.currentIndexChanged.connect(
            self.on_device1_selection_changed
        )
        self.Device1SearchButton.clicked.connect(self.search_device1)

    def set_exp_editable(self, editable: bool):
        """Управляет доступностью интерфейса испытания."""
        self.TabWidget.setEnabled(editable)

        self.SaveExp.setEnabled(editable)
        self.SaveAsButton.setEnabled(editable)

        self.ExpId.setReadOnly(not editable)
        self.ProductName.setReadOnly(not editable)
        self.ExecutorName.setReadOnly(not editable)
        self.ExpDescription.setReadOnly(not editable)

        self.GenerateExpId.setEnabled(editable)
        self.TakeCurrentDate.setEnabled(editable)
        self.ExpDate.setEnabled(editable)

        self.CommentsTable.setEnabled(editable)
        self.AddCommentButton.setEnabled(editable)
        self.EditCommentButton.setEnabled(editable)
        self.DeleteCommentButton.setEnabled(editable)

    def create_exp(self):
        """Создаёт новое испытание в оперативной памяти."""
        try:
            self.database_accessor.create_database()
        except Exception as error:
            Logger.log(
                f"Ошибка при создании испытания: {error}",
                LogLevel.ERROR,
            )
            return

        self.current_file_path = None
        self.CurrentExp.setText("Новый файл")

        self.ExpId.clear()
        self.ProductName.clear()
        self.ExecutorName.clear()
        self.ExpDescription.clear()
        self.ExpDate.setDate(QDate.currentDate())

        self.set_comments_to_ui([])
        self.set_exp_editable(True)

        Logger.log("Создано новое испытание")

    def open_exp(self):
        """Открывает SQLite-файл и загружает данные испытания."""
        file_path = self.file_accessor.select_open_file(self)

        if not file_path:
            Logger.log("Открытие файла отменено")
            return

        try:
            self.database_accessor.open_database(file_path)

            exp_data = self.database_accessor.get_data()
            comments = self.database_accessor.get_comments()

            self.set_exp_data_to_ui(exp_data)
            self.set_comments_to_ui(comments)

            self.current_file_path = file_path
            self.CurrentExp.setText(file_path)

            self.set_exp_editable(True)

            Logger.log(f"Открыто испытание: {file_path}")

        except Exception as error:
            Logger.log(
                f"Ошибка при открытии файла: {error}",
                LogLevel.ERROR,
            )

    def save_exp(self):
        """Сохраняет испытание в текущий файл."""
        if not self.database_accessor.is_open():
            Logger.log(
                "Невозможно сохранить испытание: нет открытого испытания",
                LogLevel.ERROR,
            )
            return

        if self.current_file_path is None:
            self.save_as_exp()
            return

        try:
            exp_data = self.get_exp_data_from_ui()
            self.database_accessor.set_data(exp_data)
            self.database_accessor.save_database(self.current_file_path)

            Logger.log(f"Испытание сохранено: {self.current_file_path}")

        except Exception as error:
            Logger.log(
                f"Ошибка при сохранении испытания: {error}",
                LogLevel.ERROR,
            )

    def save_as_exp(self):
        """Сохраняет испытание в выбранном формате и месте."""
        if not self.database_accessor.is_open():
            Logger.log(
                "Невозможно сохранить испытание: нет открытого испытания",
                LogLevel.ERROR,
            )
            return

        file_path, file_format = self.file_accessor.select_save_as_file(
            self,
            self.ExpId.text(),
        )

        if not file_path:
            Logger.log("Сохранение отменено", LogLevel.WARNING)
            return

        try:
            exp_data = self.get_exp_data_from_ui()

            if file_format == "sqlite":
                self.database_accessor.set_data(exp_data)

                same_path = (
                    self.current_file_path is not None
                    and os.path.normcase(os.path.abspath(file_path))
                    == os.path.normcase(
                        os.path.abspath(self.current_file_path)
                    )
                )

                if same_path or self.current_file_path is None:
                    self.database_accessor.save_database(file_path)
                else:
                    self.database_accessor.save_database_as(file_path)

                self.current_file_path = file_path
                self.CurrentExp.setText(file_path)

                Logger.log(f"Испытание сохранено: {file_path}")

            elif file_format == "xlsx":
                comments = self.database_accessor.get_comments()

                ExcelExporter.export(
                    file_path=file_path,
                    exp_data=exp_data,
                    comments=comments,
                )

                Logger.log(f"Экспорт в Excel завершён: {file_path}")

            else:
                raise ValueError(
                    f"Неподдерживаемый формат: {file_format}"
                )

        except Exception as error:
            Logger.log(
                f"Ошибка при сохранении испытания: {error}",
                LogLevel.ERROR,
            )

    def get_exp_data_from_ui(self) -> ExpData:
        """Собирает общие данные испытания из интерфейса."""
        return ExpData(
            exp_id=self.ExpId.text(),
            product_name=self.ProductName.text(),
            executor_name=self.ExecutorName.text(),
            exp_date=self.ExpDate.date().toString("dd.MM.yyyy"),
            description=self.ExpDescription.toPlainText(),
        )

    def set_exp_data_to_ui(self, exp_data: ExpData):
        """Отображает общие данные испытания в интерфейсе."""
        self.ExpId.setText(exp_data.exp_id)
        self.ProductName.setText(exp_data.product_name)
        self.ExecutorName.setText(exp_data.executor_name)
        self.ExpDescription.setPlainText(exp_data.description)

        date = QDate.fromString(exp_data.exp_date, "dd.MM.yyyy")

        if date.isValid():
            self.ExpDate.setDate(date)

    def generate_exp_id(self):
        """Генерирует номер испытания на основе текущих даты и времени."""
        exp_id = datetime.now().strftime("EXP-%Y%m%d-%H%M%S")
        self.ExpId.setText(exp_id)

        Logger.log(f"Сгенерирован номер испытания: {exp_id}")

    def take_current_date(self):
        """Устанавливает текущую дату в поле даты испытания."""
        current_date = QDate.currentDate()
        self.ExpDate.setDate(current_date)

        Logger.log(
            "Установлена текущая дата: "
            f"{current_date.toString('dd.MM.yyyy')}"
        )

    def set_comments_to_ui(self, comments):
        """Заполняет таблицу комментариев данными из базы."""
        self.CommentsTable.setRowCount(0)

        for comment_id, created_at, last_edited, text in comments:
            row = self.CommentsTable.rowCount()
            self.CommentsTable.insertRow(row)

            last_edited_item = QTableWidgetItem(last_edited)
            text_item = QTableWidgetItem(text)

            last_edited_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter
            )
            text_item.setData(
                Qt.ItemDataRole.UserRole,
                comment_id,
            )

            self.CommentsTable.setItem(row, 0, last_edited_item)
            self.CommentsTable.setItem(row, 1, text_item)

    def add_comment(self):
        """Создаёт новый комментарий к испытанию."""
        if not self.database_accessor.is_open():
            return

        dialog = CommentDialog(
            parent=self,
            window_title="Новый комментарий",
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            Logger.log("Создание комментария отменено")
            return

        text = dialog.CommentText.toPlainText()
        self.database_accessor.insert_comment(text)

        self.set_comments_to_ui(
            self.database_accessor.get_comments()
        )
        Logger.log("Успешно создан новый комментарий")

    def get_selected_comment_id(self):
        """Возвращает ID выбранного комментария либо None."""
        selected_row = self.CommentsTable.currentRow()

        if selected_row < 0:
            return None

        item = self.CommentsTable.item(selected_row, 1)

        if item is None:
            return None

        return item.data(Qt.ItemDataRole.UserRole)

    def edit_comment(self):
        """Редактирует выбранный комментарий."""
        selected_row = self.CommentsTable.currentRow()

        if selected_row < 0:
            Logger.log(
                "Комментарий для редактирования не выбран",
                LogLevel.WARNING,
            )
            return

        comment_id = self.get_selected_comment_id()

        if comment_id is None:
            Logger.log(
                "Не удалось определить ID комментария",
                LogLevel.ERROR,
            )
            return

        text_item = self.CommentsTable.item(selected_row, 1)

        if text_item is None:
            return

        dialog = CommentDialog(
            text=text_item.text(),
            parent=self,
            window_title="Редактирование комментария",
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            Logger.log("Изменение комментария отменено")
            return

        new_text = dialog.CommentText.toPlainText()

        self.database_accessor.update_comment(
            comment_id,
            new_text,
        )

        self.set_comments_to_ui(
            self.database_accessor.get_comments()
        )
        Logger.log("Комментарий успешно изменён")

    def delete_comment(self):
        """Удаляет выбранный комментарий после подтверждения."""
        comment_id = self.get_selected_comment_id()

        if comment_id is None:
            Logger.log(
                "Комментарий для удаления не выбран",
                LogLevel.WARNING,
            )
            return

        selected_row = self.CommentsTable.currentRow()
        text_item = self.CommentsTable.item(selected_row, 1)

        if text_item is None:
            return

        if text_item.text().strip():
            dialog = DeleteCommentDialog()

            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

        self.database_accessor.delete_comment(comment_id)

        self.set_comments_to_ui(
            self.database_accessor.get_comments()
        )
        Logger.log("Комментарий удалён")

    @pyqtSlot(int)
    def on_device1_selection_changed(self, index: int):
        """Обновляет состояние элементов поиска при выборе прибора."""
        device_id = self.Device1ComboBox.currentData()

        self._found_device = None
        self.Device1WindowButton.setEnabled(False)

        searching = self._device_search_thread is not None
        self.Device1SearchButton.setEnabled(
            device_id is not None and not searching
        )

        if device_id is None:
            self.Device1SearchStatusLine.setText("Прибор не выбран")
        else:
            self.Device1SearchStatusLine.setText("Готов к поиску")

    @pyqtSlot()
    def search_device1(self):
        """Запускает поиск выбранного прибора в отдельном потоке."""
        if self._device_search_thread is not None:
            return

        device_id = self.Device1ComboBox.currentData()
        device_module = get_device_module(device_id)

        if device_module is None:
            Logger.log(
                "Не удалось определить выбранный тип прибора.",
                LogLevel.ERROR,
            )
            return

        self.Device1SearchButton.setEnabled(False)
        self.Device1WindowButton.setEnabled(False)
        self.Device1ComboBox.setEnabled(False)
        self.Device1SearchStatusLine.setText("Выполняется поиск...")
        self._found_device = None

        thread = None
        worker = None

        try:
            thread = QThread(self)
            worker = DeviceSearchWorker(device_module)
            worker.moveToThread(thread)

            self._device_search_thread = thread
            self._device_search_worker = worker

            worker.log_message.connect(self._write_device_search_log)
            worker.finished.connect(self._on_device_search_finished)
            worker.failed.connect(self._on_device_search_failed)

            worker.finished.connect(thread.quit)
            worker.failed.connect(thread.quit)

            thread.started.connect(worker.run)

            worker.finished.connect(worker.deleteLater)
            worker.failed.connect(worker.deleteLater)

            thread.finished.connect(
                self._on_device_search_thread_finished
            )
            thread.finished.connect(thread.deleteLater)

            thread.start()

        except Exception as error:
            Logger.log(
                f"Не удалось запустить поиск прибора: {error}",
                LogLevel.ERROR,
            )

            self._device_search_thread = None
            self._device_search_worker = None

            if thread is not None and thread.isRunning():
                thread.quit()
                thread.wait()

            self.Device1ComboBox.setEnabled(True)
            self.Device1SearchButton.setEnabled(
                self.Device1ComboBox.currentData() is not None
            )
            self.Device1SearchStatusLine.setText("Ошибка запуска поиска")

    @pyqtSlot(str, object)
    def _write_device_search_log(self, message, level):
        """Передаёт сообщения рабочего потока в основной логгер."""
        Logger.log(message, level)

    @pyqtSlot(list)
    def _on_device_search_finished(self, devices: list):
        """Обрабатывает результаты поиска прибора."""
        if not devices:
            self._found_device = None
            self.Device1SearchStatusLine.setText("Прибор не найден")
            self.Device1WindowButton.setEnabled(False)
            return

        self._found_device = devices[0]
        device = self._found_device

        self.Device1SearchStatusLine.setText(
            f"Найден: {device['port']}, ID {device['slave_id']}"
        )
        self.Device1WindowButton.setEnabled(True)

        if len(devices) > 1:
            Logger.log(
                f"Найдено устройств: {len(devices)}. "
                "Выбрано первое найденное устройство.",
                LogLevel.WARNING,
            )

    @pyqtSlot(str)
    def _on_device_search_failed(self, error_message: str):
        """Обрабатывает ошибку поиска прибора."""
        self._found_device = None
        self.Device1SearchStatusLine.setText("Ошибка поиска")
        self.Device1WindowButton.setEnabled(False)

        Logger.log(
            f"Ошибка поиска прибора: {error_message}",
            LogLevel.ERROR,
        )

    @pyqtSlot()
    def _on_device_search_thread_finished(self):
        """Освобождает ссылки на завершившийся поток поиска."""
        self._device_search_thread = None
        self._device_search_worker = None

        self.Device1ComboBox.setEnabled(True)
        self.Device1SearchButton.setEnabled(
            self.Device1ComboBox.currentData() is not None
        )

    def device1_window(self):
        """Открывает окно измерений найденного прибора."""
        if self._found_device is None:
            return

        if self._device1_window is None:
            device_id = self.Device1ComboBox.currentData()
            device_module = get_device_module(device_id)

            if device_module is None:
                return

            self._device1_window = DeviceWindow(
                device_module=device_module,
                found_device=self._found_device,
                parent=self,
            )

            self._device1_window.closed.connect(
                self._on_device1_window_closed
            )

        self._device1_window.show()
        self._device1_window.raise_()
        self._device1_window.activateWindow()

    def _on_device1_window_closed(self):
        """Сбрасывает ссылку на закрытое окно измерений."""
        self._device1_window = None
