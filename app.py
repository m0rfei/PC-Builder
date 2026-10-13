"""Точка входа приложения PC-Builder."""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


def main() -> int:
    """Запускает приложение и возвращает код завершения."""
    application = QApplication(sys.argv)
    try:
        from pc_builder.ui_settings import ensure_ui_settings
        from pc_builder.database import initialize_database
        from pc_builder.main_window import MainWindow

        ensure_ui_settings(application)
        initialize_database()
        window = MainWindow()
    except Exception as error:
        QMessageBox.critical(
            None,
            "Не удалось запустить PC-Builder",
            "Приложение не смогло открыть базу данных или подготовить главное окно.\n\n"
            f"Подробности: {error}",
        )
        return 1
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
