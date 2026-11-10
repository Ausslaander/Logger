from importlib import import_module
from pkgutil import iter_modules

from hardware import devices


DEVICE_MODULES = {}
for entry in iter_modules(devices.__path__):
    if not entry.ispkg and not entry.name.startswith("_"):
        module = import_module(f"{devices.__name__}.{entry.name}")
        if hasattr(module, "DEVICE_ID"):
            DEVICE_MODULES[module.DEVICE_ID] = module


def get_available_devices() -> list[tuple[str, str]]:
    """Возвращает список (идентификатор, название прибора)."""

    return [
        (device_id, module.DISPLAY_NAME)
        for device_id, module in DEVICE_MODULES.items()
    ]


def get_device_module(device_id: str):
    """Возвращает модуль по идентификатору прибора."""

    return DEVICE_MODULES.get(device_id)
