"""Главное окно PC-Builder с каталогом и архивом."""

from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .catalog_widgets import ArchivePage, CatalogPage
from .builds_widgets import BuildsPage
from .reference_widgets import ReferenceManagerDialog
from .characteristics_widgets import CustomAttributeManagerDialog
from .ui_settings import UiSettingsDialog, ensure_ui_settings


class MainWindow(QMainWindow):
    """Главное окно и навигация между разделами приложения."""

    def __init__(self, database_path: Path | str | None = None) -> None:
        super().__init__()
        self.ui_settings = ensure_ui_settings()
        self.database_path = database_path
        self.setWindowTitle("PC-Builder")
        self.resize(1080, 700)
        self.setMinimumSize(760, 520)

        root = QWidget(self)
        layout = QVBoxLayout(root)
        title = QLabel("PC-Builder")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        content = QHBoxLayout()
        navigation_panel = QWidget()
        navigation_layout = QVBoxLayout(navigation_panel)
        navigation_layout.setContentsMargins(0, 0, 0, 0)
        self.navigation = QListWidget()
        self.navigation.addItems(["Моё железо", "Архив", "Сборки ПК"])
        self.navigation.setFixedWidth(230)
        self.navigation.setCurrentRow(0)
        self.pages = QStackedWidget()
        self.catalog_page = CatalogPage(database_path, self.statusBar().showMessage)
        self.archive_page = ArchivePage(database_path, self.statusBar().showMessage)
        self.builds_page = BuildsPage(database_path, self.statusBar().showMessage)
        self.pages.addWidget(self.catalog_page)
        self.pages.addWidget(self.archive_page)
        self.pages.addWidget(self.builds_page)
        self.navigation.currentRowChanged.connect(self._change_page)
        navigation_layout.addWidget(self.navigation, 1)
        self.power_calculator_button = QPushButton("Калькулятор БП")
        self.power_calculator_button.clicked.connect(self._open_power_calculator)
        navigation_layout.addWidget(self.power_calculator_button)
        self.references_button = QPushButton("Справочники")
        self.references_button.clicked.connect(self._open_reference_manager)
        navigation_layout.addWidget(self.references_button)
        self.custom_attributes_button = QPushButton("Пользовательские\nхарактеристики")
        self.custom_attributes_button.setMinimumHeight(44)
        self.custom_attributes_button.clicked.connect(self._open_custom_attribute_manager)
        navigation_layout.addWidget(self.custom_attributes_button)
        self.settings_button = QPushButton("Настройки интерфейса")
        self.settings_button.clicked.connect(self._open_ui_settings)
        navigation_layout.addWidget(self.settings_button)
        navigation_panel.setFixedWidth(230)
        content.addWidget(navigation_panel)
        content.addWidget(self.pages, 1)
        layout.addLayout(content, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Приложение запущено. База данных доступна.")

    def _change_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        if index == 1:
            self.archive_page.refresh()
        elif index == 0:
            self.catalog_page.refresh()
        elif index == 2:
            self.builds_page.refresh()

    def _open_reference_manager(self) -> None:
        dialog = ReferenceManagerDialog(self.database_path, self)
        dialog.exec()

    def _open_custom_attribute_manager(self) -> None:
        dialog = CustomAttributeManagerDialog(self.database_path, self)
        dialog.exec()

    def _open_ui_settings(self) -> None:
        UiSettingsDialog(self.ui_settings, self).exec()

    def _open_power_calculator(self) -> None:
        from .power_calculator_widgets import PowerCalculatorDialog

        PowerCalculatorDialog(self.database_path, parent=self).exec()
