from collections import OrderedDict
from contextlib import contextmanager
from threading import Condition

from PyQt6.QtCore import QThread, pyqtSignal

from accessors.measurement_journal import MeasurementJournal


class MeasurementWriter(QThread):
    """Очередь несохранённых измерений с повторной записью при сбое диска."""

    write_delayed = pyqtSignal(object, str)
    write_resumed = pyqtSignal(object)

    def __init__(self, experiment_path, parent=None):
        super().__init__(parent)
        self._journal = MeasurementJournal(experiment_path)
        self._pending = OrderedDict((row.id, row) for row in self._journal.pending_rows())
        self._unwritten = OrderedDict()
        self._condition = Condition()
        self._paused = 0
        self._writing = False
        self._stopping = False

    @property
    def path(self):
        return self._journal.path

    def exists(self):
        with self._condition:
            return bool(self._pending) or self._journal.exists()

    def append(self, rows):
        for row in rows:
            MeasurementJournal.validate_row(row)
        if self.path is None:
            raise ValueError("Сначала сохраните испытание.")
        with self._condition:
            if self._stopping:
                raise RuntimeError("Запись журнала уже завершена.")
            for row in rows:
                self._pending[row.id] = row
                self._unwritten[row.id] = row
            if not self.isRunning():
                self.start()
            self._condition.notify_all()

    def pending_rows(self):
        with self._condition:
            return list(self._pending.values())

    def has_unwritten(self):
        with self._condition:
            return bool(self._unwritten)

    def rows(self, connection):
        return self._journal.rows(connection, self.pending_rows())

    def apply(self, connection):
        self._journal.apply(connection, self.pending_rows())

    @contextmanager
    def suspend_writes(self):
        with self._condition:
            self._paused += 1
            self._condition.wait_for(lambda: not self._writing)
        try:
            yield
        finally:
            with self._condition:
                self._paused -= 1
                self._condition.notify_all()

    def clear(self):
        # Вызывается при сохранении или явном отказе от несохранённых данных.
        with self.suspend_writes():
            self._journal.clear()
            with self._condition:
                self._pending.clear()
                self._unwritten.clear()

    def mark_saved(self, experiment_path):
        # Вызывается при приостановленном потоке после успешной записи SQLite.
        cleanup_error = None
        try:
            self._journal.clear()
        except OSError as error:
            cleanup_error = str(error)
        with self._condition:
            self._pending.clear()
            self._unwritten.clear()
        self._journal = MeasurementJournal(experiment_path)
        return cleanup_error

    def stop(self):
        with self._condition:
            self._stopping = True
            self._condition.notify_all()
        self.wait()

    def run(self):
        last_error = None
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._stopping or (self._unwritten and not self._paused)
                )
                if self._stopping:
                    return
                batch = list(self._unwritten.values())[:256]
                journal = self._journal
                self._writing = True
            error_message = None
            try:
                journal.append(batch, timeout=0.1)
            except Exception as error:
                error_message = str(error)
            else:
                with self._condition:
                    for row in batch:
                        if self._unwritten.get(row.id) == row:
                            del self._unwritten[row.id]
            finally:
                with self._condition:
                    self._writing = False
                    self._condition.notify_all()

            if error_message is not None:
                if error_message != last_error:
                    self.write_delayed.emit(journal.path, error_message)
                with self._condition:
                    if not self._stopping and not self._paused:
                        self._condition.wait(timeout=0.2)
            elif last_error is not None:
                self.write_resumed.emit(journal.path)
            last_error = error_message
