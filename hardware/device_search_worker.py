
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from hardware.device_search import scan_device
from services.internal_logger import LogLevel

import traceback


class DeviceSearchWorker(QObject):
    finished = pyqtSignal(list)
    failed = pyqtSignal(str)
    log_message = pyqtSignal(str, object)

    def __init__(self, device_module):
        super().__init__()
        self.device_module = device_module

    @pyqtSlot()
    def run(self):

        try:

            devices = scan_device(
                self.device_module,
                log=lambda message, level: self.log_message.emit(
                    message, level
                ),
            )

            print(
                f"12. scan_device() завершён, найдено: {len(devices)}",
                flush=True,
            )
            self.finished.emit(devices)

        except Exception as error:
            traceback.print_exc()

            self.log_message.emit(
                f"Ошибка поиска: {type(error).__name__}: {error}",
                LogLevel.ERROR,
            )
            self.failed.emit(str(error))
