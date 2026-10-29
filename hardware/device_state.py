from enum import Enum, auto


class DeviceState(Enum):
    FOUND = auto()
    CONNECTING = auto()
    ONLINE = auto()
    CHECKING = auto()
    OFFLINE = auto()
    RECONNECTING = auto()
    CONNECTION_ERROR = auto()
