
import logging

from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal
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
        self._closing = False

        uic.loadUi(DEVICE_WINDOW_UI, self)

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

        self.StartRecordingButton.setEnabled(False)
        self.StopRecordingButton.setEnabled(False)
        self.StartReconnectingButton.setEnabled(False)
        self.StopReconnectingButton.setEnabled(False)

        self.device_monitor = DeviceMonitor(
            device_module=self.device_module,
            found_device=self.found_device,
            interval=1.0,
            max_failures=3,
            parent=self,
        )

        self.device_monitor.state_changed.connect(
            self._on_device_state_changed
        )
        self.device_monitor.error_occurred.connect(
            self._on_device_error
        )
        self.device_monitor.manual_reconnect_changed.connect(
            self._on_manual_reconnect_changed
        )

        self.StartReconnectingButton.clicked.connect(
            self.device_monitor.start_reconnecting
        )
        self.StopReconnectingButton.clicked.connect(
            self.device_monitor.stop_reconnecting
        )

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

        self.DeviceStatusLabel.setText(
            status_text.get(state, "Неизвестное состояние")
        )
        self._update_reconnect_buttons()

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
        )

        self.StopReconnectingButton.setEnabled(
            state == DeviceState.RECONNECTING
            and self._manual_reconnect_active
        )

    def _on_device_error(self, message: str):
        logger.warning(
            "Ошибка взаимодействия с прибором %s: %s",
            self.device_module.DEVICE_ID,
            message,
        )

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return

        self._closing = True
        self.StartReconnectingButton.setEnabled(False)
        self.StopReconnectingButton.setEnabled(False)

        try:
            self.device_monitor.stop_monitoring()
        except Exception:
            logger.exception(
                "Ошибка при остановке мониторинга прибора %s",
                self.device_module.DEVICE_ID,
            )
        finally:
            self.closed.emit()
            event.accept()
