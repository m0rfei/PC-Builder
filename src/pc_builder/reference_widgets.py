"""Окно управления значениями справочников."""

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from .catalog import COMPONENT_TYPE_LABELS
from .database import DatabaseError, VALID_COMPONENT_TYPES
from .references import (
    add_reference_value, delete_reference_value, get_reference_fields,
    list_reference_values, rename_reference_value, replace_reference_value,
)


class ReferenceManagerDialog(QDialog):
    """Универсальный редактор справочников категорий и характеристик."""

    def __init__(self, database_path: Path | str | None = None, parent=None):
        super().__init__(parent)
        self.database_path = database_path
        self.setWindowTitle("Справочники")
        self.resize(760, 540)

        layout = QVBoxLayout(self)
        selectors = QHBoxLayout()
        self.category_combo = QComboBox()
        self.category_combo.setObjectName("referenceCategory")
        for kind in sorted(VALID_COMPONENT_TYPES, key=lambda item: COMPONENT_TYPE_LABELS[item].casefold()):
            self.category_combo.addItem(COMPONENT_TYPE_LABELS[kind], kind)
        self.field_combo = QComboBox()
        self.field_combo.setObjectName("referenceField")
        selectors.addWidget(QLabel("Категория:"))
        selectors.addWidget(self.category_combo, 1)
        selectors.addWidget(QLabel("Поле:"))
        selectors.addWidget(self.field_combo, 1)
        layout.addLayout(selectors)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("referenceSearch")
        self.search_input.setPlaceholderText("Поиск по значениям и комплектующим")
        layout.addWidget(self.search_input)
        self.table = QTableWidget(0, 4)
        self.table.setObjectName("referenceValues")
        self.table.setHorizontalHeaderLabels(["Значение", "Источник", "Используют", "Комплектующие"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 190)
        self.table.setColumnWidth(2, 75)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Добавить")
        self.rename_button = QPushButton("Переименовать")
        self.delete_button = QPushButton("Удалить")
        self.refresh_button = QPushButton("Обновить")
        for button in (self.add_button, self.rename_button, self.delete_button, self.refresh_button):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.category_combo.currentIndexChanged.connect(self._refresh_fields)
        self.field_combo.currentIndexChanged.connect(self.refresh)
        self.search_input.textChanged.connect(self._filter_rows)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.add_button.clicked.connect(self._add)
        self.rename_button.clicked.connect(self._rename)
        self.delete_button.clicked.connect(self._delete)
        self.refresh_button.clicked.connect(self.refresh)
        self._refresh_fields()

    def _kind(self) -> str:
        return self.category_combo.currentData()

    def _field(self) -> str | None:
        return self.field_combo.currentData()

    def _refresh_fields(self, *_args) -> None:
        previous = self.field_combo.currentData()
        self.field_combo.blockSignals(True)
        self.field_combo.clear()
        try:
            fields = get_reference_fields(self._kind())
        except DatabaseError:
            fields = []
        for item in fields:
            self.field_combo.addItem(item["label"], item["field"])
        index = self.field_combo.findData(previous)
        self.field_combo.setCurrentIndex(index if index >= 0 else (0 if fields else -1))
        self.field_combo.blockSignals(False)
        self.refresh()

    def refresh(self, *_args) -> None:
        if self._field() is None:
            self.table.setRowCount(0)
            return
        try:
            values = list_reference_values(self._kind(), self._field(), self.database_path)
        except DatabaseError as error:
            self._show_error("Не удалось загрузить справочник", error)
            values = []
        self.table.setRowCount(0)
        for value in values:
            row = self.table.rowCount()
            self.table.insertRow(row)
            shown_label = value["label"] if value["label"] == value["value"] else f'{value["label"]} ({value["value"]})'
            label = QTableWidgetItem(shown_label)
            label.setData(256, value["value"])
            label.setData(257, value["usage_count"])
            self.table.setItem(row, 0, label)
            names = [f'{item["manufacturer"]} — {item["model_name"]} (№{item["id"]})' for item in value["used_by"]]
            self.table.setItem(row, 1, QTableWidgetItem(value["origin"]))
            self.table.setItem(row, 2, QTableWidgetItem(str(value["usage_count"])))
            self.table.setItem(row, 3, QTableWidgetItem("; ".join(names)))
        self._filter_rows()
        self._update_actions()

    def _filter_rows(self, *_args) -> None:
        needle = self.search_input.text().strip().casefold()
        for row in range(self.table.rowCount()):
            text = " ".join(self.table.item(row, col).text() for col in range(4)).casefold()
            self.table.setRowHidden(row, bool(needle and needle not in text))

    def _selected(self) -> tuple[str, int] | None:
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return None
        item = self.table.item(row, 0)
        return item.data(256), int(item.data(257) or 0)

    def _update_actions(self, *_args) -> None:
        selected = self._selected() is not None
        self.rename_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)

    def _add(self) -> None:
        value, accepted = QInputDialog.getText(self, "Добавить значение", "Новое значение:")
        if not accepted:
            return
        try:
            add_reference_value(self._kind(), self._field(), value, self.database_path)
        except DatabaseError as error:
            self._show_error("Не удалось добавить значение", error)
            return
        self.refresh()

    def _rename(self) -> None:
        selected = self._selected()
        if not selected:
            return
        old_value, used_count = selected
        new_value, accepted = QInputDialog.getText(
            self, "Переименовать значение", "Новое название:", QLineEdit.EchoMode.Normal, old_value
        )
        if not accepted:
            return
        if used_count and QMessageBox.question(
            self, "Переименовать значение",
            f"Значение «{old_value}» используется в {used_count} комплектующих. Переименовать его во всех записях?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            rename_reference_value(self._kind(), self._field(), old_value, new_value, self.database_path)
        except DatabaseError as error:
            self._show_error("Не удалось переименовать значение", error)
            return
        self.refresh()

    def _delete(self) -> None:
        selected = self._selected()
        if not selected:
            return
        value, count = selected
        if not count:
            if QMessageBox.question(
                self, "Удалить значение", f"Удалить значение «{value}»?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
            try:
                delete_reference_value(self._kind(), self._field(), value, self.database_path)
            except DatabaseError as error:
                self._show_error("Не удалось удалить значение", error)
                return
            self.refresh()
            return

        matches = list_reference_values(self._kind(), self._field(), self.database_path)
        details = next(item["used_by"] for item in matches if item["value"] == value)
        names = "\n".join(f'• {item["manufacturer"]} — {item["model_name"]} (№{item["id"]})' for item in details)
        message = QMessageBox(self)
        message.setWindowTitle("Значение используется")
        message.setIcon(QMessageBox.Icon.Warning)
        message.setText(f"«{value}» используется комплектующими: {count}.")
        message.setInformativeText(names + "\n\nМожно заменить его другим значением этого же справочника.")
        replace_button = message.addButton("Заменить значение", QMessageBox.ButtonRole.AcceptRole)
        message.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        if message.clickedButton() != replace_button:
            return
        choices = [item["value"] for item in matches if item["value"] != value]
        if not choices:
            self._show_error("Замена невозможна", "Сначала добавьте другое значение в этот справочник.")
            return
        target, accepted = QInputDialog.getItem(self, "Заменить значение", "Заменить на:", choices, 0, False)
        if not accepted:
            return
        if QMessageBox.question(
            self, "Подтвердить замену", f"Заменить «{value}» на «{target}» у {count} комплектующих и удалить старый пункт?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            replace_reference_value(self._kind(), self._field(), value, target, self.database_path)
        except DatabaseError as error:
            self._show_error("Не удалось заменить значение", error)
            return
        self.refresh()

    def _show_error(self, title: str, error: Exception | str) -> None:
        QMessageBox.warning(self, title, str(error))
