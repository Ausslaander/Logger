from models.measurement import MeasurementDefinition
import serial


DEVICE_ID = "GLine_a1k0"
DISPLAY_NAME = (
    "Генератор ВЧ сигналов "
    "GLine.A-1K0.2M0/4M0.1.0 HFP"
)

# ОБЯЗАТЕЛЬНО указать скорость из настроек реального генератора.
BAUDRATE = 9600

BYTESIZE = serial.EIGHTBITS
PARITY = serial.PARITY_NONE
STOPBITS = serial.STOPBITS_ONE
TIMEOUT = 0.2

SLAVE_IDS = range(1, 248)


def crc16(data: bytes) -> int:
    """CRC-16/Modbus."""
    crc = 0xFFFF

    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1

    return crc


def append_crc(data: bytes) -> bytes:
    crc = crc16(data)
    return data + bytes((crc & 0xFF, crc >> 8))


def build_identification_request(slave_id: int) -> bytes:
    """Формирует запрос Read Slave ID (0x11)."""
    return append_crc(bytes((slave_id, 0x11)))


def probe(connection: serial.Serial, slave_id: int) -> str | None:
    """
    Проверяет Modbus ID и возвращает идентификатор изделия,
    только если ответ соответствует ожидаемому формату GLine.
    """
    connection.reset_input_buffer()
    connection.write(build_identification_request(slave_id))
    connection.flush()

    header = connection.read(3)

    if len(header) != 3:
        return None

    response_id, function_code, byte_count = header

    if response_id != slave_id:
        return None

    # Исключение Modbus: адрес, функция с установленным старшим
    # битом, код исключения, CRC.
    if function_code & 0x80:
        tail = connection.read(2)
        response = header + tail
        return None

    if function_code != 0x11:
        return None

    if byte_count not in (34, 36):
        return None

    tail = connection.read(byte_count + 2)

    if len(tail) != byte_count + 2:
        return None

    response = header + tail

    expected_crc = crc16(response[:-2])
    received_crc = response[-2] | (response[-1] << 8)

    if expected_crc != received_crc:
        return None

    # Согласно таблице руководства:
    # байт 3 — признак ВЧ, байт 4 — дополнительный,
    # байты 5–36 — 32 символа шифра изделия.
    if response[3] not in (0, 255) or response[4] != 0:
        return None

    try:
        product_code = response[5:37].decode("ascii").strip("\x00 ")
    except UnicodeDecodeError:
        return None

    if not product_code.startswith("GLine"):
        return None

    return product_code
# Предварительный пример структуры.
# Реальные величины уточним по документации прибора.
MEASUREMENT_DEFINITIONS = [
    # MeasurementDefinition(
    #     key="output_power",
    #     name="Выходная мощность",
    #     unit="W",
    #     precision=2,
    # ),
]