from hardware.devices import GLine_a1k0


DEVICE_MODULES = {
    GLine_a1k0.DEVICE_ID: GLine_a1k0,
}


def get_available_devices() -> list[tuple[str, str]]:
    """Возвращает список (идентификатор, название прибора)."""

    return [
        (device_id, module.DISPLAY_NAME)
        for device_id, module in DEVICE_MODULES.items()
    ]


def get_device_module(device_id: str):
    """Возвращает модуль по идентификатору прибора."""

    return DEVICE_MODULES.get(device_id)
