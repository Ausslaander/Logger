
import logging
from datetime import datetime
from uuid import uuid4

from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QMainWindow, QMessageBox

from accessors.measurement_journal import MeasurementRow
from config import DEVICE_WINDOW_UI
from hardware.device_monitor import DeviceMonitor
from hardware.device_state import DeviceState
from services.internal_logger import InternalLogger
from views.MeasurementPlot import MeasurementPlot


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
        self._recording_notice = None
        self._experiment_start_time = None
        self._plot_elapsed = 0.0
        self.device_key = f"{device_module.DEVICE_ID} / {found_device['port']} / {found_device['slave_id']}"

        # Загружаем интерфейс до обращения к его элементам.
        uic.loadUi(DEVICE_WINDOW_UI, self)
        self.measurement_plots = []
        for index in range(10):
            plot = MeasurementPlot(device_module.PLOT_PARAMETERS, self)
            self.PlotsLayout.addWidget(plot, index // 2, index % 2)
            self.measurement_plots.append(plot)
        self.PlotsLayout.setColumnStretch(0, 1)
        self.PlotsLayout.setColumnStretch(1, 1)

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
        self.DeviceStatusLabel.setFont(self.DeviceNameLabel.font())
        self.DeviceStatusIndicator.setToolTip(self.DeviceStatusLabel.text())

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
        status_colors = {
            DeviceState.FOUND: "#808080",
            DeviceState.CONNECTING: "#d99000",
            DeviceState.ONLINE: "#249447",
            DeviceState.CHECKING: "#d99000",
            DeviceState.OFFLINE: "#d63c3c",
            DeviceState.RECONNECTING: "#d99000",
            DeviceState.CONNECTION_ERROR: "#d63c3c",
        }
        color = status_colors.get(state, "#808080")

        if self._is_recording:
            self.DeviceStatusLabel.setText(
                "Нет связи. Ожидание прибора" if state != DeviceState.ONLINE else "Запись данных"
            )
            if state == DeviceState.ONLINE:
                color = "#3489df"
        else:
            self.DeviceStatusLabel.setText(
                status_text.get(state, "Неизвестное состояние")
            )

        self.DeviceStatusIndicator.setStyleSheet(
            f"background-color: {color}; border-radius: 7px;"
        )
        self.DeviceStatusIndicator.setToolTip(self.DeviceStatusLabel.text())
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
        start_row = self._new_row(note="Начало записи")
        try:
            start_time = self.parent().measurement_start_time()
            if start_time is None:
                start_time = datetime.fromisoformat(start_row.timestamp).timestamp()
        except Exception as error:
            QMessageBox.warning(self, "Ошибка истории измерений", str(error))
            return
        if not self._append_rows([start_row]):
            return

        self._experiment_start_time = start_time
        for plot in self.measurement_plots:
            plot.clear()
        self._link_lost = False
        self._is_recording = True
        self.device_monitor.recording_session = object()

        self._on_device_state_changed(self._current_device_state)

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
            self._log_measurement(row)
        return True

    def _log_measurement(self, row):
        message = row.note or "; ".join(
            f"{column} = {value}"
            for column, value in zip(row.columns, row.values)
        )
        InternalLogger.log(f"{row.device} [{row.timestamp}] {message}")

    def _on_measurement_read(self, session, timestamp, values):
        if session is not self.device_monitor.recording_session:
            return
        if values is None:
            self._update_plots(timestamp, {})
            if not self._link_lost:
                self._link_lost = True
                self._append_rows([self._new_row(timestamp, note="Связь потеряна")])
            return

        rows = []
        if self._link_lost:
            rows.append(self._new_row(timestamp, note="Связь восстановлена после обрыва"))
            self._link_lost = False
        rows.append(self._new_row(timestamp, values))
        if self._append_rows(rows):
            self._update_plots(timestamp, dict(zip(self.device_module.MEASUREMENT_COLUMNS, values)))

    def _update_plots(self, timestamp, values):
        sample_time = datetime.fromisoformat(timestamp).timestamp()
        # Все графики используют одинаковое время даже при коррекции часов ПК.
        self._plot_elapsed = max(
            self._plot_elapsed, sample_time - self._experiment_start_time, 0.0
        )
        for plot in self.measurement_plots:
            plot.add_sample(self._plot_elapsed, values)

    def _on_monitor_finished(self):
        if not self._closing:
            self._current_device_state = DeviceState.OFFLINE
            self.stop_recording()
            self._on_device_state_changed(DeviceState.OFFLINE)

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

    def show_recording_notice(self):
        if self._recording_notice is None:
            self._recording_notice = QMessageBox(self)
            self._recording_notice.setWindowTitle("Идёт запись измерений")
            self._recording_notice.setIcon(QMessageBox.Icon.Information)
            self._recording_notice.setModal(False)
            self._recording_notice.setText(
                "Идёт активная запись измерений. Закрыть окно невозможно. "
                "Сначала нажмите «Остановить запись»."
            )
            self._recording_notice.addButton("Понятно", QMessageBox.ButtonRole.AcceptRole)
        self._recording_notice.show()
        self._recording_notice.raise_()
        self._recording_notice.activateWindow()

    def closeEvent(self, event):
        if self._is_recording:
            event.ignore()
            self.show_recording_notice()
            return

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
