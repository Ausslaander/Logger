import PyQt6
from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow

from config import DEVICE_WINDOW_UI

class DeviceWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        uic.loadUi(DEVICE_WINDOW_UI, self)

        self.DeviceStatusLabel.setText('Готов (тестовый режим)')
        self.StartRecordingButton.setEnabled(True)
        self.StopRecordingButton.setEnabled(False)