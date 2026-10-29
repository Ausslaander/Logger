
import logging

from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtCore import QDate, QThread, Qt, pyqtSlot
from PyQt6.QtWidgets import QMainWindow

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
        self._closing = False

        # Загружаем интерфейс до обращения к его элементам.
        uic.loadUi(DEVICE_WINDOW_UI, self)

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
            self._stop_recording
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
            self.DeviceStatusLabel.setText("Запись данных")
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

        # Приостанавливаем опрос связи.
        self.device_monitor.pause_polling()

        self._is_recording = True

        self._update_recording_buttons()
        self._update_reconnect_buttons()

        self.DeviceStatusLabel.setText("Запись данных")

    def _stop_recording(self) -> None:
        if not self._is_recording:
            return

        self._is_recording = False

        # Возобновляем опрос связи.
        self.device_monitor.resume_polling()

        self._update_recording_buttons()
        self._update_reconnect_buttons()

        # Показываем актуальное состояние прибора.
        status_text = {
            DeviceState.FOUND: "Прибор найден",
            DeviceState.CONNECTING: "Подключение...",
            DeviceState.ONLINE: "На связи",
            DeviceState.CHECKING: "Проверка связи...",
            DeviceState.OFFLINE: "Нет связи",
            DeviceState.RECONNECTING: "Восстановление связи...",
            DeviceState.CONNECTION_ERROR: "Ошибка подключения",
        }

        self.DeviceStatusLabel.setText(
            status_text.get(
                self._current_device_state,
                "Неизвестное состояние",
            )
        )

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
            # Снимаем режим записи перед остановкой монитора.
            if self._is_recording:
                self._is_recording = False
                self.device_monitor.resume_polling()

            self.device_monitor.stop_monitoring()

        except Exception:
            logger.exception(
                "Ошибка при остановке мониторинга прибора %s",
                self.device_module.DEVICE_ID,
            )

        finally:
            self.closed.emit()
            event.accept()
