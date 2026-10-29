import serial
import logging

logger = logging.getLogger(__name__)


class DeviceConnection:
    """Управляет соединением с конкретным экземпляром прибора."""

    def __init__(self, device_module, found_device: dict):
        self.device_module = device_module
        self.found_device = found_device
        self._connection: serial.Serial | None = None

    @property
    def is_connected(self) -> bool:
        return (
            self._connection is not None
            and self._connection.is_open
        )

    def connect(self) -> None:
        """Открывает последовательный порт."""
        print("[DeviceConnection] connect(): начало", flush=True)
        if self.is_connected:
            return

        self.disconnect()

        self._connection = serial.Serial(
            port=self.found_device["port"],
            baudrate=self.device_module.BAUDRATE,
            bytesize=self.device_module.BYTESIZE,
            parity=self.device_module.PARITY,
            stopbits=self.device_module.STOPBITS,
            timeout=self.device_module.TIMEOUT,
        )
        print("[DeviceConnection] connect(): завершение", flush=True)

    def check_connection(self) -> bool:
        """Проверяет связь с прибором через интерфейс его модели."""
        print("[DeviceConnection] check_connection(): начало", flush=True)
        if not self.is_connected:
            return False

        product_code = self.device_module.probe(
            self._connection,
            self.found_device["slave_id"],
        )

        print("[DeviceConnection] check_connection(): завершение", flush=True)

        return product_code is not None

    def disconnect(self) -> None:
        """Закрывает последовательный порт."""
        print("[DeviceConnection] disconnect(): начало", flush=True)

        connection = self._connection
        self._connection = None

        if connection is None:
            return

        try:
            if connection.is_open:
                connection.close()
        except Exception:
            logger.exception(
                "Не удалось корректно закрыть последовательный порт"
            )
        print("[DeviceConnection] disconnect(): завершение", flush=True)
