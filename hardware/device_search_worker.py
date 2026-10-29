
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
            print("10. DeviceSearchWorker.run() начат", flush=True)

            devices = scan_device(
                self.device_module,
                log=lambda message, level: self.log_message.emit(
                    message, level
                ),
            )

            print(
                f"11. Поиск завершён, найдено: {len(devices)}",
                flush=True,
            )

            print("12. Перед finished.emit()", flush=True)
            self.finished.emit(devices)
            print("13. После finished.emit()", flush=True)

        except Exception as error:
            traceback.print_exc()

            self.log_message.emit(
                f"Ошибка поиска: {type(error).__name__}: {error}",
                LogLevel.ERROR,
            )
            self.failed.emit(str(error))

        finally:
            print("14. Выход из DeviceSearchWorker.run()", flush=True)

