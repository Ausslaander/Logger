
import serial
from serial.tools import list_ports

from services.internal_logger import InternalLogger as Logger
from services.internal_logger import LogLevel


def scan_device(device_module, log=None) -> list[dict]:
    """
    Ищет прибор заданной модели на доступных последовательных портах.

    device_module должен содержать:
        DISPLAY_NAME, BAUDRATE, BYTESIZE, PARITY, STOPBITS,
        TIMEOUT, SLAVE_IDS и функцию probe(connection, slave_id).

    log — функция вида log(message, level).

    Возвращает список словарей:
        {"port": str, "slave_id": int, "model": str}
    """
    if log is None:
        log = Logger.log

    if device_module.BAUDRATE is None:
        log(
            f"Поиск {device_module.DISPLAY_NAME} невозможен: "
            "не задана скорость передачи.",
            LogLevel.ERROR,
        )
        return []

    ports = list(list_ports.comports())
    slave_ids = list(device_module.SLAVE_IDS)

    total_ports = len(ports)
    total_ids = len(slave_ids)
    found_devices = []

    log(
        f"Начат поиск прибора: {device_module.DISPLAY_NAME}.",
        LogLevel.INFO,
    )
    log(
        f"Обнаружено последовательных портов: {total_ports}.",
        LogLevel.INFO,
    )
    log(
        f"Будет проверено Modbus ID: {total_ids}.",
        LogLevel.INFO,
    )

    for port_info in ports:
        port_name = port_info.device

        try:
            with serial.Serial(
                port=port_name,
                baudrate=device_module.BAUDRATE,
                bytesize=device_module.BYTESIZE,
                parity=device_module.PARITY,
                stopbits=device_module.STOPBITS,
                timeout=device_module.TIMEOUT,
                write_timeout=device_module.TIMEOUT,
            ) as connection:

                for index, slave_id in enumerate(slave_ids, start=1):
                    log(
                        f"Проверка порта {port_name}: "
                        f"Modbus ID {slave_id} "
                        f"({index} из {total_ids}).",
                        LogLevel.INFO,
                    )

                    try:
                        model = device_module.probe(
                            connection,
                            slave_id,
                        )

                    except (serial.SerialException, OSError) as error:
                        log(
                            f"Ошибка обмена с портом {port_name}, "
                            f"Modbus ID {slave_id}: {error}",
                            LogLevel.WARNING,
                        )
                        break

                    if model is None:
                        continue

                    device = {
                        "port": port_name,
                        "slave_id": slave_id,
                        "model": model,
                    }
                    found_devices.append(device)

                    log(
                        f"Найден прибор: модель={model}, "
                        f"порт={port_name}, Modbus ID={slave_id}.",
                        LogLevel.INFO,
                    )
                    return found_devices

        except (serial.SerialException, OSError) as error:
            log(
                f"Не удалось открыть порт {port_name}: {error}",
                LogLevel.WARNING,
            )

    if found_devices:
        log(
            f"Поиск завершён. Найдено устройств: "
            f"{len(found_devices)}.",
            LogLevel.INFO,
        )
    else:
        log(
            f"Поиск завершён. Прибор {device_module.DISPLAY_NAME} "
            "не обнаружен.",
            LogLevel.WARNING,
        )

    return found_devices
