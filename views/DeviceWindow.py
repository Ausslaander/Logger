
import logging
from datetime import datetime
from uuid import uuid4

from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QHeaderView, QMainWindow, QMessageBox, QTableWidgetItem,
)

from accessors.measurement_journal import MeasurementRow
from config import DEVICE_WINDOW_UI
from hardware.device_monitor import DeviceMonitor
from hardware.device_state import DeviceState


logger = logging.getLogger(__name__)


class DeviceWindow(QMainWindow):
    closed = pyqtSignal()

    def __init__(self, device_module, found_device, parent=None):
        super().__init__(parent)

        self.setAttribute(
            Qt.WidgetAttribute.WA_DeleteOnClose,
            True,
        )

        self.device_module = device_module
        self.found_device = found_device

        self._current_device_state = None
        self._manual_reconnect_active = False
        self._is_recording = False
        self._link_lost = False
        self._closing = False
        self._rows = []
        self.device_key = f"{device_module.DEVICE_ID} / {found_device['port']} / {found_device['slave_id']}"

        # Загружаем интерфейс до обращения к его элементам.
        uic.loadUi(DEVICE_WINDOW_UI, self)
        self.MeasurementsTable.setColumnCount(len(device_module.MEASUREMENT_COLUMNS) + 2)
        self.MeasurementsTable.setHorizontalHeaderLabels(
            ("Временная метка", *device_module.MEASUREMENT_COLUMNS, "Примечание")
        )
        self.MeasurementsTable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.MeasurementsTable.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.MeasurementsTable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.MeasurementsTable.horizontalHeader()
        header.setMinimumSectionSize(100)
        header.resizeSections(QHeaderView.ResizeMode.ResizeToContents)
        self.MeasurementsTable.setColumnWidth(0, 245)
        self.MeasurementsTable.setColumnWidth(len(device_module.MEASUREMENT_COLUMNS) + 1, 280)
        self.MeasurementsTable.hide()
        self.DeleteMeasurementButton.setEnabled(False)
        self.DeleteMeasurementButton.clicked.connect(self._delete_measurement)
        self.MeasurementsTable.itemSelectionChanged.connect(self._update_delete_button)
        for row in parent.measurement_rows():
            if row.device == self.device_key:
                self._show_row(row)

        # Настраиваем подписи окна.
        self.DeviceNameLabel.setText(
            self.device_module.DISPLAY_NAME
        )
        self.setWindowTitle(
            f"Окно измерений — {self.device_module.DISPLAY_NAME}"
        )
        self.DeviceStatusLabel.setText(
            f"Обнаружен: {self.found_device['port']}, "
            f"ID {self.found_device['slave_id']}"
        )

        # Подключаем кнопки записи.
        self.StartRecordingButton.clicked.connect(
            self._start_recording
        )
        self.StopRecordingButton.clicked.connect(
            self.stop_recording
        )

        self.StartRecordingButton.setEnabled(False)
        self.StopRecordingButton.setEnabled(False)

        # Начальное состояние кнопок переподключения.
        self.StartReconnectingButton.setEnabled(False)
        self.StopReconnectingButton.setEnabled(False)

        # Создаём монитор прибора.
        self.device_monitor = DeviceMonitor(
            device_module=self.device_module,
            found_device=self.found_device,
            interval=1.0,
            max_failures=3,
            parent=self,
        )

        # Подключаем сигналы монитора.
        self.device_monitor.state_changed.connect(
            self._on_device_state_changed
        )
        self.device_monitor.error_occurred.connect(
            self._on_device_error
        )
        self.device_monitor.manual_reconnect_changed.connect(
            self._on_manual_reconnect_changed
        )
        self.device_monitor.measurement_read.connect(self._on_measurement_read)
        self.device_monitor.finished.connect(self._on_monitor_finished)

        # Подключаем кнопки переподключения.
        self.StartReconnectingButton.clicked.connect(
            self.device_monitor.start_reconnecting
        )
        self.StopReconnectingButton.clicked.connect(
            self.device_monitor.stop_reconnecting
        )

        # Запускаем мониторинг.
        self.device_monitor.start_monitoring()

    def _on_device_state_changed(self, state: DeviceState):
        self._current_device_state = state

        status_text = {
            DeviceState.FOUND: "Прибор найден",
            DeviceState.CONNECTING: "Подключение...",
            DeviceState.ONLINE: "На связи",
            DeviceState.CHECKING: "Проверка связи...",
            DeviceState.OFFLINE: "Нет связи",
            DeviceState.RECONNECTING: "Восстановление связи...",
            DeviceState.CONNECTION_ERROR: "Ошибка подключения",
        }

        if self._is_recording:
            self.DeviceStatusLabel.setText(
                "Нет связи. Ожидание прибора" if state != DeviceState.ONLINE else "Запись данных"
            )
        else:
            self.DeviceStatusLabel.setText(
                status_text.get(state, "Неизвестное состояние")
            )

        self._update_reconnect_buttons()
        self._update_recording_buttons()

    def _on_manual_reconnect_changed(self, active: bool):
        self._manual_reconnect_active = active
        self._update_reconnect_buttons()

    def _update_reconnect_buttons(self):
        if self._closing:
            self.StartReconnectingButton.setEnabled(False)
            self.StopReconnectingButton.setEnabled(False)
            return

        state = self._current_device_state

        self.StartReconnectingButton.setEnabled(
            state == DeviceState.OFFLINE
            and not self._manual_reconnect_active
            and not self._is_recording
        )

        self.StopReconnectingButton.setEnabled(
            state == DeviceState.RECONNECTING
            and self._manual_reconnect_active
            and not self._is_recording
        )

    def _on_device_error(self, message: str):
        logger.warning(
            "Ошибка взаимодействия с прибором %s: %s",
            self.device_module.DEVICE_ID,
            message,
        )

    def _start_recording(self) -> None:
        if self._closing or self._is_recording:
            return

        if self._current_device_state != DeviceState.ONLINE:
            return

        if not self.parent().ensure_measurement_file():
            return
        if self._closing or self._current_device_state != DeviceState.ONLINE:
            return
        if not self._append_rows([self._new_row(note="Начало записи")]):
            return

        self._link_lost = False
        self._is_recording = True
        self.device_monitor.recording_session = object()

        self._update_recording_buttons()
        self._update_reconnect_buttons()

        self.DeviceStatusLabel.setText("Запись данных")

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def stop_recording(self) -> None:
        if not self._is_recording:
            return

        self.device_monitor.recording_session = None
        self._is_recording = False
        self._append_rows([self._new_row(note="Конец записи")])
        self._on_device_state_changed(self._current_device_state)

    def _new_row(self, timestamp=None, values=(), note=""):
        return MeasurementRow(
            uuid4().hex, self.device_key,
            timestamp or datetime.now().astimezone().isoformat(timespec="milliseconds"),
            self.device_module.MEASUREMENT_COLUMNS, values, note,
        )

    def _append_rows(self, rows):
        try:
            self.parent().measurement_journal().append(rows)
        except Exception as error:
            self.device_monitor.recording_session = None
            self._is_recording = False
            self._on_device_state_changed(self._current_device_state)
            QMessageBox.warning(self, "Ошибка журнала измерений", str(error))
            return False
        for row in rows:
            self._show_row(row)
        return True

    def _show_row(self, row):
        table = self.MeasurementsTable
        scroll = table.verticalScrollBar()
        follow = scroll.value() == scroll.maximum()
        index = table.rowCount()
        table.insertRow(index)
        self._rows.append(row)
        for column, value in enumerate(row.cells(self.device_module.MEASUREMENT_COLUMNS)):
            table.setItem(index, column, QTableWidgetItem(str(value)))
        table.show()
        if follow:
            table.scrollToBottom()

    def _on_measurement_read(self, session, timestamp, values):
        if session is not self.device_monitor.recording_session:
            return
        if values is None:
            if not self._link_lost:
                self._link_lost = True
                self._append_rows([self._new_row(timestamp, note="Связь потеряна")])
            return

        rows = []
        if self._link_lost:
            rows.append(self._new_row(timestamp, note="Связь восстановлена после обрыва"))
            self._link_lost = False
        rows.append(self._new_row(timestamp, values))
        self._append_rows(rows)

    def _on_monitor_finished(self):
        if not self._closing:
            self._current_device_state = DeviceState.OFFLINE
            self.stop_recording()
            self._on_device_state_changed(DeviceState.OFFLINE)

    def _update_delete_button(self):
        index = self.MeasurementsTable.currentRow()
        self.DeleteMeasurementButton.setEnabled(
            0 <= index < len(self._rows) and not self._rows[index].note
        )

    def _delete_measurement(self):
        index = self.MeasurementsTable.currentRow()
        if not 0 <= index < len(self._rows) or self._rows[index].note:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Удаление измерения")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText("Удалить выбранное измерение?")
        delete = dialog.addButton("Удалить", QMessageBox.ButtonRole.DestructiveRole)
        cancel = dialog.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        if dialog.clickedButton() is not delete:
            return
        try:
            self.parent().measurement_journal().delete(self._rows[index])
        except Exception as error:
            QMessageBox.warning(self, "Ошибка удаления", str(error))
            return
        self._rows.pop(index)
        self.MeasurementsTable.removeRow(index)
        self._update_delete_button()

    def _update_recording_buttons(self) -> None:
        online = (
            self._current_device_state == DeviceState.ONLINE
        )

        self.StartRecordingButton.setEnabled(
            online
            and not self._is_recording
            and not self._closing
        )

        self.StopRecordingButton.setEnabled(
            self._is_recording
            and not self._closing
        )

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return

        self._closing = True

        self.StartRecordingButton.setEnabled(False)
        self.StopRecordingButton.setEnabled(False)
        self.StartReconnectingButton.setEnabled(False)
        self.StopReconnectingButton.setEnabled(False)

        try:
            self.stop_recording()
            self.device_monitor.stop_monitoring()

        except Exception:
            logger.exception(
                "Ошибка при остановке мониторинга прибора %s",
                self.device_module.DEVICE_ID,
            )

        finally:
            self.closed.emit()
            event.accept()
