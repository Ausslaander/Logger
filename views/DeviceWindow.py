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
        print(
            "[DeviceWindow] 1. Вход в __init__",
            flush=True,
        )

        print(
            "[DeviceWindow] 2. Перед super().__init__(parent)",
            flush=True,
        )
        super().__init__(parent)
        print(
            "[DeviceWindow] 3. После super().__init__(parent)",
            flush=True,
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_DeleteOnClose,
            True,
        )

        self.device_module = device_module
        self.found_device = found_device

        self._current_device_state = None
        self._manual_reconnect_active = False
        self._closing = False

        print(
            f"[DeviceWindow] 4. DEVICE_WINDOW_UI={DEVICE_WINDOW_UI!r}",
            flush=True,
        )
        print(
            "[DeviceWindow] 5. Перед uic.loadUi()",
            flush=True,
        )

        uic.loadUi(DEVICE_WINDOW_UI, self)

        print(
            "[DeviceWindow] 6. После uic.loadUi()",
            flush=True,
        )

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

        print(
            "[DeviceWindow] 7. Подписи окна настроены",
            flush=True,
        )

        print(
            "[DeviceWindow] 8.1 StartRecordingButton:",
            repr(self.StartRecordingButton),
            flush=True,
        )
        self.StartRecordingButton.setEnabled(False)
        print("[DeviceWindow] 8.2 StartRecordingButton отключена", flush=True)

        print(
            "[DeviceWindow] 8.3 StopRecordingButton:",
            repr(self.StopRecordingButton),
            flush=True,
        )
        self.StopRecordingButton.setEnabled(False)
        print("[DeviceWindow] 8.4 StopRecordingButton отключена", flush=True)

        print(
            "[DeviceWindow] 8.5 Получение StartReconnectingButton",
            flush=True,
        )
        start_button = self.StartReconnectingButton
        print(
            "[DeviceWindow] 8.6 StartReconnectingButton получена:",
            repr(start_button),
            flush=True,
        )
        print(
            "[DeviceWindow] 8.7 Тип StartReconnectingButton:",
            type(start_button),
            flush=True,
        )

        print(
            "[DeviceWindow] 8.8 Получение StopReconnectingButton",
            flush=True,
        )
        stop_button = self.StopReconnectingButton
        print(
            "[DeviceWindow] 8.9 StopReconnectingButton получена:",
            repr(stop_button),
            flush=True,
        )
        print(
            "[DeviceWindow] 8.10 Тип StopReconnectingButton:",
            type(stop_button),
            flush=True,
        )
        print(
            "[DeviceWindow] 8.11 Перед отключением StopReconnectingButton",
            flush=True,
        )
        self.StopReconnectingButton.setEnabled(False)
        print(
            "[DeviceWindow] 8.12 После отключения StopReconnectingButton",
            flush=True,
        )

        print(
            "[DeviceWindow] 8.13 Все кнопки настроены",
            flush=True,
        )

        print(
            "[DeviceWindow] 9. Перед созданием DeviceMonitor",
            flush=True,
        )

        self.device_monitor = DeviceMonitor(
            device_module=self.device_module,
            found_device=self.found_device,
            interval=1.0,
            max_failures=3,
            parent=self,
        )

        print(
            "[DeviceWindow] 10. DeviceMonitor создан",
            flush=True,
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

        print(
            "[DeviceWindow] 11. Сигналы DeviceMonitor подключены",
            flush=True,
        )

        self.StartReconnectingButton.clicked.connect(
            self.device_monitor.start_reconnecting
        )
        self.StopReconnectingButton.clicked.connect(
            self.device_monitor.stop_reconnecting
        )

        print(
            "[DeviceWindow] 12. Обработчики кнопок подключены",
            flush=True,
        )

        print(
            "[DeviceWindow] 13. Перед start_monitoring()",
            flush=True,
        )

        self.device_monitor.start_monitoring()

        print(
            "[DeviceWindow] 14. После start_monitoring()",
            flush=True,
        )

    def _on_device_state_changed(self, state: DeviceState):
        print(
            f"[DeviceWindow] Изменение состояния: {state!r}",
            flush=True,
        )

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
        print(
            f"[DeviceWindow] Ручное переподключение: {active}",
            flush=True,
        )

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
        print(
            f"[DeviceWindow] Ошибка прибора: {message}",
            flush=True,
        )

        logger.warning(
            "Ошибка взаимодействия с прибором %s: %s",
            self.device_module.DEVICE_ID,
            message,
        )

    def closeEvent(self, event):
        print(
            "[DeviceWindow] Вызван closeEvent()",
            flush=True,
        )

        if self._closing:
            event.accept()
            return

        self._closing = True
        self.StartReconnectingButton.setEnabled(False)
        self.StopReconnectingButton.setEnabled(False)

        try:
            print(
                "[DeviceWindow] Перед stop_monitoring()",
                flush=True,
            )
            self.device_monitor.stop_monitoring()
            print(
                "[DeviceWindow] После stop_monitoring()",
                flush=True,
            )
        except Exception:
            logger.exception(
                "Ошибка при остановке мониторинга прибора %s",
                self.device_module.DEVICE_ID,
            )
        finally:
            self.closed.emit()
            event.accept()

            print(
                "[DeviceWindow] Окно закрывается",
                flush=True,
            )