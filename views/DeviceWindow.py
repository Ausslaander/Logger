import PyQt6
from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow

from config import DEVICE_WINDOW_UI

from enum import Enum, auto

class DeviceWindow(QMainWindow):
    def __init__(self, device_module, found_device, parent=None):

        super().__init__(parent)

        self.device_module = device_module
        self.found_device = found_device

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