import sys

from PyQt6.QtWidgets import QApplication

from views.MainWindow import MainWindow

import faulthandler

faulthandler.enable(all_threads=True)

def main():
    """
    Точка входа в приложение.

    Создаёт экземпляр приложения Qt, инициализирует главное окно
    и запускает цикл обработки событий.
    """

    # Создание объекта приложения Qt.
    # sys.argv передаёт приложению аргументы командной строки.
    app = QApplication(sys.argv)

    # Создание главного окна приложения.
    window=MainWindow()

    # Отображение главного окна на экране.
    window.show()

    # Запуск основного цикла обработки событий Qt.
    # Цикл продолжает работу, пока приложение не будет закрыто.
    print("[main] Перед app.exec()", flush=True)

    exit_code = app.exec()

    print(
        f"[main] app.exec() завершился, exit_code={exit_code}",
        flush=True,
    )

    sys.exit(exit_code)


# Запуск приложения только в случае непосредственного выполнения main.py.
# При импорте main.py в другой модуль функция main() автоматически не вызывается.
if __name__ == "__main__":
    main()