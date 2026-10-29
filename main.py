
import sys
import faulthandler

from PyQt6.QtWidgets import QApplication

from views.MainWindow import MainWindow


faulthandler.enable(all_threads=True)


def main():
    """Запускает приложение."""
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
