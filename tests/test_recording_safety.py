import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from accessors.database_accessor import DatabaseAccessor
from accessors.measurement_journal import MeasurementJournal, MeasurementRow
from hardware.devices import GLine_a1k0
from services.internal_logger import InternalLogger
from views.MainWindow import MainWindow


class TestConnection:
    count = 0

    def __init__(self, *args):
        self.is_connected = False

    def connect(self):
        self.is_connected = True

    def disconnect(self):
        self.is_connected = False

    def check_connection(self):
        return True

    def read_measurements(self):
        type(self).count += 1
        return (self.count,) * len(GLine_a1k0.MEASUREMENT_COLUMNS)


class RecordingSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "experiment.sqlite")
        self.main = MainWindow()
        self.main.create_exp()
        self.main._save_sqlite(self.path, self.main.get_exp_data_from_ui())

    def tearDown(self):
        if self.main._device1_window is not None:
            self.main._device1_window.stop_recording()
            self.main._device1_window.close()
        if self.main._measurement_writer is not None:
            self.main._measurement_writer.stop()
        self.main.database_accessor.close()
        self.main.hide()
        self.app.processEvents()
        self.directory.cleanup()

    def until(self, check, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if check():
                return
            time.sleep(0.005)
        self.assertTrue(check(), "Истекло время ожидания")

    def test_second_process_cannot_overwrite_open_experiment(self):
        program = """
import sys
from accessors.database_accessor import DatabaseAccessor
database = DatabaseAccessor()
try:
    database.open_database(sys.argv[1])
except RuntimeError:
    sys.exit(23)
database.close()
"""
        result = subprocess.run([sys.executable, "-B", "-c", program, self.path], timeout=10)
        self.assertEqual(result.returncode, 23)
        self.main.database_accessor.close()
        result = subprocess.run([sys.executable, "-B", "-c", program, self.path], timeout=10)
        self.assertEqual(result.returncode, 0)

    def test_file_lock_recovers_after_process_crash(self):
        self.main.database_accessor.close()
        program = """
import os, sys
from accessors.database_accessor import DatabaseAccessor
database = DatabaseAccessor()
database.open_database(sys.argv[1])
print('locked', flush=True)
sys.stdin.readline()
os._exit(31)
"""
        child = subprocess.Popen(
            [sys.executable, "-B", "-c", program, self.path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual(child.stdout.readline().strip(), "locked")
            other = DatabaseAccessor()
            with self.assertRaises(RuntimeError):
                other.open_database(self.path)
            child.communicate("exit\n", timeout=10)
            self.assertEqual(child.returncode, 31)
            self.main.database_accessor.open_database(self.path)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate()

    def test_locked_journal_retries_without_losing_accepted_measurements(self):
        TestConnection.count = 0
        with patch("hardware.device_monitor.DeviceConnection", TestConnection):
            self.main.Device1ComboBox.setCurrentIndex(1)
            self.main._found_device = {"port": "TEST", "slave_id": 2}
            self.main.device1_window()
            window = self.main._device1_window
            window.device_monitor.interval = 0.02
            self.until(window.StartRecordingButton.isEnabled)
            window.StartRecordingButton.click()
            journal = self.main.measurement_journal()
            disk = MeasurementJournal(self.path)
            self.until(lambda: disk.exists() and len(disk.pending_rows()) >= 2)
            with closing(sqlite3.connect(journal.path)) as locker:
                locker.execute("BEGIN EXCLUSIVE")
                before = TestConnection.count
                self.until(lambda: self.main._journal_notice is not None)
                self.until(lambda: TestConnection.count >= before + 10)
                self.assertTrue(window.is_recording)
                self.assertFalse(self.main._journal_notice.isModal())
                self.assertGreaterEqual(len(journal.pending_rows()), 11)
                window.StopRecordingButton.click()
                expected_ids = [row.id for row in journal.pending_rows()]
                locker.rollback()
            self.until(lambda: len(disk.pending_rows()) == len(expected_ids))
            self.assertEqual([row.id for row in disk.pending_rows()], expected_ids)
            self.assertTrue(self.main.save_exp())
            self.assertFalse(journal.exists())
            self.assertEqual([row.id for row in self.main.measurement_rows()], expected_ids)

    def test_invalid_timestamp_is_rejected_before_experiment_switch(self):
        bad_path = str(Path(self.directory.name) / "bad.sqlite")
        other = DatabaseAccessor()
        other.create_database()
        with other.connection:
            MeasurementJournal._ensure_table(other.connection)
            MeasurementJournal._write(other.connection, MeasurementRow(
                "bad-time", "GLine", "invalid", ("Power",), (12,), "",
            ))
        # Создаём структурно корректную SQLite с неверными данными измерения.
        with closing(sqlite3.connect(bad_path)) as target:
            other.connection.backup(target)
        other.close()
        original = self.main.database_accessor.connection
        with patch.object(self.main.file_accessor, "select_open_file", return_value=bad_path):
            with patch.object(QMessageBox, "warning") as warning:
                self.main.OpenExp.click()
                warning.assert_called_once()
        self.assertIs(self.main.database_accessor.connection, original)
        self.assertEqual(self.main.current_file_path, self.path)
        self.assertFalse(Path(bad_path + ".logger-lock").exists())

    def test_save_as_keeps_queue_on_failure_and_transfers_it_on_retry(self):
        target = str(Path(self.directory.name) / "copy.sqlite")
        journal = self.main.measurement_journal()
        row = MeasurementRow("pending", "TEST", "2026-11-18T12:00:00+03:00", ("Power",), (12,), "")
        journal.append([row])
        with patch("accessors.database_accessor.os.replace", side_effect=PermissionError("test")):
            with self.assertRaises(PermissionError):
                self.main._save_sqlite(target, self.main.get_exp_data_from_ui())
        self.assertEqual(self.main.current_file_path, self.path)
        self.assertEqual(journal.pending_rows(), [row])
        self.main._save_sqlite(target, self.main.get_exp_data_from_ui())
        self.assertEqual(self.main.current_file_path, target)
        self.assertEqual(self.main.measurement_rows(), [row])
        self.assertFalse(MeasurementJournal(self.path).exists())
        self.assertFalse(journal.exists())
        original = DatabaseAccessor()
        original.open_database(self.path)
        self.assertEqual(MeasurementJournal(self.path).rows(original.connection), [])
        original.close()

    def test_log_retains_only_last_thousand_lines(self):
        for index in range(1100):
            InternalLogger.log(f"sample-{index}")
        output = self.main.InternalLoggerWindow
        self.assertEqual(output.document().blockCount(), 1000)
        self.assertNotIn("sample-0\n", output.toPlainText())
        self.assertIn("sample-1099", output.toPlainText())

    def test_disk_error_keeps_queue_available_for_save_as(self):
        journal = self.main.measurement_journal()
        row = MeasurementRow("buffered", "TEST", "2026-11-18T12:00:00+03:00", ("Power",), (42,), "")
        target = str(Path(self.directory.name) / "rescued.sqlite")
        with patch.object(MeasurementJournal, "append", side_effect=OSError("disk full")):
            journal.append([row])
            self.until(lambda: self.main._journal_notice is not None)
            self.assertEqual(journal.pending_rows(), [row])
            self.main._save_sqlite(target, self.main.get_exp_data_from_ui())
        self.assertEqual(self.main.current_file_path, target)
        self.assertEqual(self.main.measurement_rows(), [row])
        self.assertFalse(journal.exists())
        self.app.processEvents()
        self.assertFalse(self.main._journal_notice.isVisible())

    def test_cleanup_failure_does_not_leave_save_as_on_old_path(self):
        journal = self.main.measurement_journal()
        row = MeasurementRow("cleanup", "TEST", "2026-11-18T12:00:00+03:00", ("Power",), (42,), "")
        journal.append([row])
        disk = MeasurementJournal(self.path)
        self.until(lambda: disk.exists() and len(disk.pending_rows()) == 1)
        target = str(Path(self.directory.name) / "saved.sqlite")
        with patch.object(MeasurementJournal, "clear", side_effect=PermissionError("locked journal")):
            self.main._save_sqlite(target, self.main.get_exp_data_from_ui())
        self.assertEqual(self.main.current_file_path, target)
        self.assertEqual(self.main.measurement_rows(), [row])
        self.assertIn("прежний временный журнал не удалён", self.main.InternalLoggerWindow.toPlainText())
        second = DatabaseAccessor()
        second.open_database(self.path)
        second.close()
        with self.assertRaises(RuntimeError):
            second.open_database(target)

    def test_recover_journal_after_crash_then_save_without_duplicates(self):
        self.main.database_accessor.close()
        program = """
import os, sys
from accessors.database_accessor import DatabaseAccessor
from accessors.measurement_journal import MeasurementJournal, MeasurementRow
database = DatabaseAccessor()
database.open_database(sys.argv[1])
MeasurementJournal(sys.argv[1]).append([
    MeasurementRow('crashed', 'TEST', '2026-11-18T12:00:00+03:00', ('Power',), (42,), '')
])
os._exit(31)
"""
        result = subprocess.run([sys.executable, "-B", "-c", program, self.path], timeout=10)
        self.assertEqual(result.returncode, 31)
        self.main = MainWindow()
        with patch.object(self.main.file_accessor, "select_open_file", return_value=self.path):
            with patch.object(self.main, "_ask_measurement_recovery", return_value=True) as prompt:
                self.main.OpenExp.click()
                prompt.assert_called_once()
        self.assertEqual([row.id for row in self.main.measurement_rows()], ["crashed"])
        self.assertTrue(self.main.save_exp())
        self.assertFalse(MeasurementJournal(self.path).exists())
        self.assertTrue(self.main.save_exp())
        self.assertEqual([row.id for row in self.main.measurement_rows()], ["crashed"])


if __name__ == "__main__":
    unittest.main()
