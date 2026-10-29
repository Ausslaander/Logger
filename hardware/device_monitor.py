
from threading import Event, get_ident

from PyQt6.QtCore import QThread, pyqtSignal

from hardware.device_connection import DeviceConnection
from hardware.device_state import DeviceState


class DeviceMonitor(QThread):
    """Контролирует связь и управляет восстановлением подключения."""

    state_changed = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    manual_reconnect_changed = pyqtSignal(bool)

    def __init__(
        self,
        device_module,
        found_device: dict,
        interval: float = 1.0,
        max_failures: int = 3,
        parent=None,
    ):
        super().__init__(parent)

        if interval <= 0:
            raise ValueError(
                "Интервал проверки должен быть положительным."
            )

        if max_failures < 1:
            raise ValueError(
                "Количество неудачных проверок должно быть не меньше 1."
            )

        self.device_module = device_module
        self.found_device = found_device
        self.interval = interval
        self.max_failures = max_failures

        self._stop_event = Event()
        self._start_reconnect_event = Event()
        self._stop_reconnect_event = Event()
        self._polling_paused = Event()

        self._connection = None
        self._current_state = None
        self._manual_reconnect_active = False

        print(
            f"[DeviceMonitor] __init__: "
            f"port={found_device.get('port')}, "
            f"slave_id={found_device.get('slave_id')}, "
            f"interval={interval}, max_failures={max_failures}",
            flush=True,
        )

    def _set_state(self, state: DeviceState) -> None:
        if state != self._current_state:
            print(
                f"[DeviceMonitor] Состояние: "
                f"{self._current_state} -> {state}",
                flush=True,
            )
            self._current_state = state
            self.state_changed.emit(state)

    def _set_manual_reconnect(self, active: bool) -> None:
        if active != self._manual_reconnect_active:
            print(
                f"[DeviceMonitor] Ручное переподключение: {active}",
                flush=True,
            )
            self._manual_reconnect_active = active
            self.manual_reconnect_changed.emit(active)

    def _connect_and_check(self) -> bool:
        """Одна попытка: открыть порт и получить корректный ответ."""
        print(
            "[DeviceMonitor] _connect_and_check: начало",
            flush=True,
        )

        try:
            print("[DeviceMonitor] Вызов connect()", flush=True)
            self._connection.connect()
            print("[DeviceMonitor] connect() завершён", flush=True)

            print(
                "[DeviceMonitor] Вызов check_connection()",
                flush=True,
            )
            result = self._connection.check_connection()

            print(
                f"[DeviceMonitor] check_connection() завершён: {result}",
                flush=True,
            )
            return result

        except Exception as error:
            print(
                f"[DeviceMonitor] ОШИБКА подключения/проверки: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            self.error_occurred.emit(str(error))
            return False

        finally:
            print(
                "[DeviceMonitor] _connect_and_check: выход",
                flush=True,
            )

    def _wait(self) -> None:
        """Ожидание следующего шага с возможностью остановки."""
        print(
            f"[DeviceMonitor] Ожидание {self.interval} с",
            flush=True,
        )
        self._stop_event.wait(self.interval)
        print(
            "[DeviceMonitor] Ожидание завершено",
            flush=True,
        )

    def run(self) -> None:
        print(
            f"[DeviceMonitor] run(): начало, thread_id={get_ident()}",
            flush=True,
        )

        failures = 0
        ever_online = False
        manual_mode = False

        try:
            print(
                "[DeviceMonitor] Создание DeviceConnection",
                flush=True,
            )

            self._connection = DeviceConnection(
                self.device_module,
                self.found_device,
            )

            print(
                "[DeviceMonitor] DeviceConnection создан",
                flush=True,
            )

            # Первоначальная попытка подключения.
            print(
                "[DeviceMonitor] Первоначальное подключение",
                flush=True,
            )
            self._set_state(DeviceState.CONNECTING)

            if self._connect_and_check():
                ever_online = True
                self._set_state(DeviceState.ONLINE)
                print(
                    "[DeviceMonitor] Прибор доступен",
                    flush=True,
                )
            else:
                print(
                    "[DeviceMonitor] Первоначальное подключение не удалось",
                    flush=True,
                )
                self._connection.disconnect()
                self._set_state(DeviceState.OFFLINE)

            iteration = 0

            while not self._stop_event.is_set():
                iteration += 1

                print(
                    f"[DeviceMonitor] Цикл #{iteration}, "
                    f"state={self._current_state}, "
                    f"manual_mode={manual_mode}, "
                    f"failures={failures}, "
                    f"polling_paused={self._polling_paused.is_set()}",
                    flush=True,
                )

                # Во время записи не обрабатываем команды
                # переподключения и не выполняем проверки связи.
                if self._polling_paused.is_set():
                    self._stop_event.wait(0.1)
                    continue

                # Команда пользователя на запуск переподключения.
                if self._start_reconnect_event.is_set():
                    print(
                        "[DeviceMonitor] Получена команда "
                        "начала переподключения",
                        flush=True,
                    )

                    self._start_reconnect_event.clear()
                    self._stop_reconnect_event.clear()

                    if (
                        not ever_online
                        or self._current_state == DeviceState.OFFLINE
                    ):
                        manual_mode = True
                        self._set_manual_reconnect(True)
                        self._set_state(DeviceState.RECONNECTING)
                    else:
                        print(
                            "[DeviceMonitor] Ручное переподключение "
                            "не запущено: прибор уже был доступен",
                            flush=True,
                        )

                # Команда пользователя на остановку переподключения.
                if self._stop_reconnect_event.is_set():
                    print(
                        "[DeviceMonitor] Получена команда "
                        "остановки переподключения",
                        flush=True,
                    )

                    self._stop_reconnect_event.clear()

                    if manual_mode:
                        manual_mode = False
                        self._set_manual_reconnect(False)

                        print(
                            "[DeviceMonitor] Закрытие соединения "
                            "после остановки переподключения",
                            flush=True,
                        )
                        self._connection.disconnect()
                        self._set_state(DeviceState.OFFLINE)

                # Режим ручного переподключения.
                if manual_mode:
                    print(
                        "[DeviceMonitor] Режим ручного переподключения",
                        flush=True,
                    )

                    if self._connect_and_check():
                        ever_online = True
                        failures = 0
                        manual_mode = False

                        self._set_manual_reconnect(False)
                        self._set_state(DeviceState.ONLINE)

                        print(
                            "[DeviceMonitor] Переподключение успешно",
                            flush=True,
                        )
                    else:
                        print(
                            "[DeviceMonitor] Переподключение не удалось; "
                            "закрываю соединение",
                            flush=True,
                        )
                        self._connection.disconnect()

                    self._wait()
                    continue

                # Проверка работающего прибора.
                if self._current_state == DeviceState.ONLINE:
                    try:
                        print(
                            "[DeviceMonitor] Проверка работающего прибора",
                            flush=True,
                        )

                        is_alive = (
                            self._connection.check_connection()
                        )

                        print(
                            f"[DeviceMonitor] Результат проверки: "
                            f"{is_alive}",
                            flush=True,
                        )

                    except Exception as error:
                        print(
                            f"[DeviceMonitor] ОШИБКА проверки связи: "
                            f"{type(error).__name__}: {error}",
                            flush=True,
                        )
                        self.error_occurred.emit(str(error))
                        is_alive = False

                    if is_alive:
                        failures = 0
                    else:
                        failures += 1
                        print(
                            f"[DeviceMonitor] Неудачная проверка: "
                            f"{failures}/{self.max_failures}",
                            flush=True,
                        )

                    if failures >= self.max_failures:
                        print(
                            "[DeviceMonitor] Достигнут предел ошибок; "
                            "закрываю соединение",
                            flush=True,
                        )

                        self._connection.disconnect()
                        failures = 0

                        self._set_state(DeviceState.OFFLINE)

                        # Одна автоматическая попытка восстановления.
                        self._set_state(DeviceState.RECONNECTING)

                        print(
                            "[DeviceMonitor] Автоматическая попытка "
                            "восстановления",
                            flush=True,
                        )

                        if self._connect_and_check():
                            ever_online = True
                            self._set_state(DeviceState.ONLINE)

                            print(
                                "[DeviceMonitor] Автоматическое "
                                "восстановление успешно",
                                flush=True,
                            )
                        else:
                            print(
                                "[DeviceMonitor] Автоматическое "
                                "восстановление не удалось",
                                flush=True,
                            )
                            self._connection.disconnect()
                            self._set_state(DeviceState.OFFLINE)

                self._wait()

            print(
                "[DeviceMonitor] Цикл завершён: получен запрос остановки",
                flush=True,
            )

        except Exception as error:
            print(
                f"[DeviceMonitor] КРИТИЧЕСКАЯ ОШИБКА run(): "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            self.error_occurred.emit(
                f"{type(error).__name__}: {error}"
            )

        finally:
            print(
                "[DeviceMonitor] finally: начало завершения",
                flush=True,
            )

            try:
                self._set_manual_reconnect(False)
            except Exception as error:
                print(
                    f"[DeviceMonitor] Ошибка сброса ручного "
                    f"переподключения: {error}",
                    flush=True,
                )
                self.error_occurred.emit(
                    "Не удалось обновить состояние переподключения."
                )

            if self._connection is not None:
                try:
                    print(
                        "[DeviceMonitor] Закрытие соединения",
                        flush=True,
                    )
                    self._connection.disconnect()
                    print(
                        "[DeviceMonitor] Соединение закрыто",
                        flush=True,
                    )

                except Exception as error:
                    print(
                        f"[DeviceMonitor] Ошибка закрытия соединения: "
                        f"{type(error).__name__}: {error}",
                        flush=True,
                    )
                    self.error_occurred.emit(
                        f"Ошибка закрытия соединения: {error}"
                    )

                finally:
                    self._connection = None

            print(
                "[DeviceMonitor] run(): завершение",
                flush=True,
            )

    def start_monitoring(self) -> None:
        """Запускает монитор."""
        print(
            f"[DeviceMonitor] start_monitoring(): "
            f"isRunning={self.isRunning()}",
            flush=True,
        )

        if not self.isRunning():
            self._stop_event.clear()
            self._start_reconnect_event.clear()
            self._stop_reconnect_event.clear()
            self._polling_paused.clear()
            self._current_state = None
            self._manual_reconnect_active = False

            print(
                "[DeviceMonitor] Вызов start()",
                flush=True,
            )
            self.start()

    def start_reconnecting(self) -> None:
        """Запрашивает запуск цикла переподключения."""
        print(
            f"[DeviceMonitor] start_reconnecting(): "
            f"isRunning={self.isRunning()}",
            flush=True,
        )

        if self.isRunning() and not self._polling_paused.is_set():
            self._start_reconnect_event.set()

    def stop_reconnecting(self) -> None:
        """Запрашивает остановку цикла переподключения."""
        print(
            "[DeviceMonitor] stop_reconnecting(): вызван",
            flush=True,
        )

        if self.isRunning() and not self._polling_paused.is_set():
            self._stop_reconnect_event.set()

    def stop_monitoring(self) -> None:
        """Останавливает монитор и ждёт освобождения ресурсов."""
        print(
            f"[DeviceMonitor] stop_monitoring(): "
            f"isRunning={self.isRunning()}",
            flush=True,
        )

        self._stop_event.set()
        self._stop_reconnect_event.set()

        if self.isRunning():
            print(
                "[DeviceMonitor] Ожидание завершения потока",
                flush=True,
            )
            self.wait()
            print(
                "[DeviceMonitor] Поток завершён",
                flush=True,
            )

    def pause_polling(self) -> None:
        """Приостанавливает проверки связи."""
        print(
            "[DeviceMonitor] Опрос приостановлен",
            flush=True,
        )
        self._polling_paused.set()

    def resume_polling(self) -> None:
        """Возобновляет проверки связи."""
        print(
            "[DeviceMonitor] Опрос возобновлён",
            flush=True,
        )
        self._polling_paused.clear()
