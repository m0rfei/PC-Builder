"""Интерфейс списка сборок и отдельного конструктора ПК."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from .catalog import COMPONENT_TYPE_LABELS
from .catalog_widgets import ModelCardDialog
from .compatibility import CompatibilityStatus, check_build_compatibility
from .database import (
    BUILD_SLOT_COMPONENT_TYPES, DatabaseError, VALID_COMPONENT_TYPES,
    add_build_slot, create_build, delete_build, delete_build_slot,
    get_build, get_build_components, list_build_slots, list_builds,
    list_components, set_build_slot_component, update_build,
    update_build_slot_quantity,
)


EDITOR_CATEGORIES = (
    ("cpu", "Процессор", False, False),
    ("motherboard", "Материнская плата", False, False),
    ("psu", "Блок питания", False, False),
    ("case", "Корпус", False, False),
    ("gpu", "Видеокарта (рекомендуется, но необязательно)", False, False),
    ("cpu_cooler", "Охлаждение процессора", False, False),
    ("ram", "Оперативная память", True, False),
    ("storage", "Накопители", True, False),
    ("case_fan", "Корпусные вентиляторы (необязательно)", True, False),
    ("optical_drive", "Приводы (необязательно)", True, True),
    ("controller_hub", "Контроллеры и хабы (необязательно)", True, True),
    ("network_card", "Сетевые карты (необязательно)", True, True),
)
REQUIRED_CATEGORIES = ("cpu", "motherboard", "cpu_cooler", "ram", "storage", "psu", "case")


def build_is_ready(slots: list[dict]) -> bool:
    """Готовность вычисляется по текущему составу, а не хранится в БД."""
    filled = {slot["category"] for slot in slots if slot.get("component_id") is not None}
    return all(category in filled for category in REQUIRED_CATEGORIES)


def _error(parent, title: str, error: Exception | str) -> None:
    QMessageBox.warning(parent, title, str(error))


class BuildFormDialog(QDialog):
    """Начальный шаг создания сборки: имя и необязательное описание."""

    def __init__(self, build: dict | None = None, parent=None):
        super().__init__(parent)
        self.build = build
        self.setWindowTitle("Редактирование сборки" if build else "Новая сборка")
        self.resize(420, 300)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Например, Игровой ПК")
        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(130)
        form.addRow("Название:", self.name_input)
        form.addRow("Описание:", self.description_input)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Продолжить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if build:
            self.name_input.setText(build["name"])
            self.description_input.setPlainText(build["description"] or "")

    def values(self) -> tuple[str, str | None]:
        return self.name_input.text().strip(), self.description_input.toPlainText().strip() or None

    def _save(self) -> None:
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Не указано название", "Введите название сборки.")
            self.name_input.setFocus()
            return
        self.accept()


class ComponentPickerDialog(QDialog):
    """Выбор активной карточки из каталога, ограниченный нужной категорией."""

    def __init__(
        self, database_path: Path | str | None = None, parent=None,
        component_types: set[str] | frozenset[str] | None = None,
    ):
        super().__init__(parent)
        self.database_path = database_path
        self.component_types = frozenset(component_types or VALID_COMPONENT_TYPES)
        self.component_id: int | None = None
        self.setWindowTitle("Выбрать комплектующее из каталога")
        self.resize(700, 470)
        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск по названию, производителю или артикулу")
        self.type_filter = QComboBox()
        self.type_filter.addItem("Все подходящие категории", None)
        for kind in sorted(self.component_types, key=lambda item: COMPONENT_TYPE_LABELS[item].casefold()):
            self.type_filter.addItem(COMPONENT_TYPE_LABELS[kind], kind)
        filters.addWidget(self.search_input, 2)
        filters.addWidget(self.type_filter, 1)
        layout.addLayout(filters)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Категория", "Производитель", "Модель"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Выбрать")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        self.add_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.add_button.setEnabled(False)
        layout.addWidget(buttons)
        self.search_input.textChanged.connect(self.refresh)
        self.type_filter.currentIndexChanged.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(lambda *_: self._accept_selection())
        self.refresh()

    def refresh(self, *_args) -> None:
        try:
            components = list_components(
                status="owned", component_type=self.type_filter.currentData(),
                search=self.search_input.text().strip(), database_path=self.database_path,
            )
            components = [component for component in components if component["component_type"] in self.component_types]
        except DatabaseError as error:
            _error(self, "Не удалось загрузить каталог", error)
            components = []
        self.table.setRowCount(len(components))
        for row, component in enumerate(components):
            values = [COMPONENT_TYPE_LABELS[component["component_type"]], component["manufacturer"], component["model_name"]]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, component["id"])
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self._selection_changed()

    def _selection_changed(self, *_args) -> None:
        self.add_button.setEnabled(self.table.currentRow() >= 0)

    def _accept_selection(self) -> None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is None:
            return
        self.component_id = int(item.data(Qt.ItemDataRole.UserRole))
        self.accept()


class BuildEditorDialog(QDialog):
    """Отдельное окно-конструктор; изменения слотов сохраняются сразу."""

    composition_changed = Signal()

    def __init__(
        self, build_id: int, database_path: Path | str | None = None,
        status_message=None, parent=None,
    ):
        super().__init__(parent)
        self.build_id = build_id
        self.database_path = database_path
        self.status_message = status_message or (lambda _message: None)
        self._last_ready: bool | None = None
        build = get_build(build_id, database_path)
        if build is None:
            raise DatabaseError(f"Сборка {build_id} не найдена.")
        self.setWindowTitle(f"Конструктор сборки — {build['name']}")
        self.resize(900, 760)
        self.setMinimumSize(680, 500)
        root = QVBoxLayout(self)

        details = QGroupBox("Сведения о сборке")
        details_layout = QFormLayout(details)
        self.name_input = QLineEdit(build["name"])
        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(74)
        self.description_input.setPlainText(build["description"] or "")
        details_layout.addRow("Название:", self.name_input)
        details_layout.addRow("Описание:", self.description_input)
        details_buttons = QHBoxLayout()
        self.save_details_button = QPushButton("Сохранить сведения")
        self.power_calculator_button = QPushButton("Калькулятор БП")
        details_buttons.addStretch(1)
        details_buttons.addWidget(self.power_calculator_button)
        details_buttons.addWidget(self.save_details_button)
        details_layout.addRow(details_buttons)
        root.addWidget(details)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.slots_host = QWidget()
        self.slots_layout = QVBoxLayout(self.slots_host)
        self.slots_layout.setContentsMargins(4, 4, 4, 4)
        self.slots_layout.setSpacing(8)
        self.scroll_area.setWidget(self.slots_host)
        root.addWidget(self.scroll_area, 1)

        footer = QHBoxLayout()
        self.readiness_label = QLabel()
        self.readiness_label.setWordWrap(True)
        self.readiness_label.setStyleSheet("font-weight: 600;")
        footer.addWidget(self.readiness_label, 1)
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        root.addLayout(footer)

        compatibility_group = QGroupBox("Совместимость")
        compatibility_layout = QVBoxLayout(compatibility_group)
        self.compatibility_label = QLabel()
        self.compatibility_label.setWordWrap(True)
        compatibility_layout.addWidget(self.compatibility_label)
        root.addWidget(compatibility_group)

        self.save_details_button.clicked.connect(self._save_details)
        self.power_calculator_button.clicked.connect(self._open_power_calculator)
        self.refresh()

    def _open_power_calculator(self) -> None:
        from .power_calculator_widgets import PowerCalculatorDialog

        PowerCalculatorDialog(
            self.database_path, build_id=self.build_id, parent=self,
        ).exec()

    def _save_details(self) -> None:
        try:
            update_build(
                self.build_id, name=self.name_input.text(),
                description=self.description_input.toPlainText(), database_path=self.database_path,
            )
        except DatabaseError as error:
            _error(self, "Не удалось сохранить сведения о сборке", error)
            return
        self.setWindowTitle(f"Конструктор сборки — {self.name_input.text().strip()}")
        self.status_message("Сведения о сборке сохранены.")
        self.composition_changed.emit()

    def refresh(self) -> None:
        while self.slots_layout.count():
            item = self.slots_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        try:
            slots = list_build_slots(self.build_id, self.database_path)
        except DatabaseError as error:
            _error(self, "Не удалось загрузить состав сборки", error)
            slots = []
        for category, title, dynamic, unavailable in EDITOR_CATEGORIES:
            box = QGroupBox(title)
            box_layout = QVBoxLayout(box)
            rows = [slot for slot in slots if slot["category"] == category]
            if unavailable:
                message = QLabel("В текущем каталоге нет соответствующего типа комплектующего; поле появится после добавления такой категории в отдельном этапе.")
                message.setWordWrap(True)
                message.setEnabled(False)
                box_layout.addWidget(message)
            elif rows:
                for position, slot in enumerate(rows, 1):
                    box_layout.addWidget(self._slot_row(category, slot, position, dynamic))
            else:
                empty = QLabel("Слотов пока нет.")
                empty.setEnabled(False)
                box_layout.addWidget(empty)
            if dynamic and not unavailable:
                add_row = QHBoxLayout()
                add_row.addStretch(1)
                add_button = QPushButton("Добавить слот")
                if category == "ram" and len(rows) >= 6:
                    add_button.setEnabled(False)
                    add_button.setToolTip("Можно добавить не более шести модулей памяти.")
                if category == "case_fan" and len(rows) >= 8:
                    add_button.setEnabled(False)
                    add_button.setToolTip("Можно добавить не более восьми корпусных вентиляторов.")
                add_button.clicked.connect(lambda _checked=False, kind=category: self._add_slot(kind))
                add_row.addWidget(add_button)
                box_layout.addLayout(add_row)
            self.slots_layout.addWidget(box)
        self.slots_layout.addStretch(1)
        ready = build_is_ready(slots)
        if ready:
            self.readiness_label.setText("Сборка готова")
            self.readiness_label.setStyleSheet("font-weight: 600; color: #70c590;")
        else:
            missing = [EDITOR_CATEGORY_NAMES[kind] for kind in REQUIRED_CATEGORIES if not any(
                slot["category"] == kind and slot["component_id"] is not None for slot in slots
            )]
            self.readiness_label.setText("Сборка не готова. Не заполнено: " + ", ".join(missing))
            self.readiness_label.setStyleSheet("font-weight: 600;")
        if self._last_ready is False and ready:
            self.status_message("Сборка готова")
        self._last_ready = ready
        self._refresh_compatibility()

    def _refresh_compatibility(self) -> None:
        try:
            results = check_build_compatibility(self.build_id, database_path=self.database_path)
        except DatabaseError as error:
            self.compatibility_label.setText(f"Не удалось загрузить данные для проверки: {error}")
            return
        if not results:
            self.compatibility_label.setText("Для текущего состава нет применимых правил.")
            return
        status_labels = {
            CompatibilityStatus.COMPATIBLE: "Совместимо",
            CompatibilityStatus.INCOMPATIBLE: "Несовместимо",
            CompatibilityStatus.UNKNOWN: "Недостаточно данных",
        }
        lines = []
        try:
            all_slots = list_build_slots(self.build_id, self.database_path)
            slots_by_id = {int(slot["slot_id"]): slot for slot in all_slots}
            ram_slot_numbers = {
                int(slot["slot_id"]): number
                for number, slot in enumerate((item for item in all_slots if item["category"] == "ram"), 1)
            }
        except DatabaseError as error:
            slots_by_id = {}
            lines.append(f"Не удалось получить сведения о слотах: {error}")
        for result in results:
            if result.rule_id == "ram.motherboard.ddr":
                slot_id = result.details.get("ram_slot_id") if result.details else None
                try:
                    stable_slot_id = int(slot_id) if slot_id is not None else None
                except (TypeError, ValueError):
                    stable_slot_id = None
                slot = slots_by_id.get(stable_slot_id) if stable_slot_id is not None else None
                slot_number = ram_slot_numbers.get(stable_slot_id) if stable_slot_id is not None else None
                if slot is not None and slot_number is not None and slot["category"] == "ram":
                    module_name = " ".join(part for part in (slot.get("manufacturer"), slot.get("model_name")) if part)
                    if not module_name:
                        module_name = "Неизвестный модуль"
                    line = f"RAM {slot_number} — {module_name}: {status_labels[result.status]} — {result.message}"
                else:
                    line = f"Оперативная память: {status_labels[result.status]} — {result.message}"
                if result.reason:
                    line += f" {result.reason}"
            else:
                line = f"{status_labels[result.status]} — {result.message}"
                if result.reason:
                    line += f" Причина: {result.reason}"
            lines.append(line)
        self.compatibility_label.setText("\n".join(lines))

    def _slot_row(self, category: str, slot: dict, position: int, dynamic: bool) -> QWidget:
        row = QWidget()
        layout = QGridLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        slot_title = {
            "ram": f"Модуль ОЗУ {position}",
            "storage": f"Накопитель {position}",
            "case_fan": f"Вентилятор {position}",
        }.get(category, dict((key, value) for key, value, *_ in EDITOR_CATEGORIES).get(category, category))
        title = QLabel(slot_title + ":")
        component_id = slot["component_id"]
        if component_id is None:
            value_text = "Не выбрано"
        else:
            value_text = " ".join(part for part in (slot["manufacturer"], slot["model_name"]) if part)
            if slot["status"] == "archived":
                value_text = "[В архиве] " + value_text
        value = QLabel(value_text)
        value.setWordWrap(True)
        value.setMinimumWidth(120)
        layout.addWidget(title, 0, 0)
        layout.addWidget(value, 0, 1)

        quantity_label = QLabel("Кол-во:")
        quantity = QLineEdit(str(slot["quantity"]))
        quantity.setMaximumWidth(88)
        quantity.setToolTip("Количество физических компонентов в этой позиции сборки.")
        if dynamic and component_id is not None:
            quantity.setValidator(QRegularExpressionValidator(QRegularExpression("[0-9]*"), quantity))
            quantity.editingFinished.connect(
                lambda sid=slot["slot_id"], field=quantity, kind=category: self._save_slot_quantity(sid, kind, field)
            )
        else:
            quantity.setReadOnly(True)
            quantity.setToolTip("Для этой категории количество фиксировано моделью слотов.")
        layout.addWidget(quantity_label, 0, 2)
        layout.addWidget(quantity, 0, 3)

        types = BUILD_SLOT_COMPONENT_TYPES.get(category, frozenset())
        select_button = QPushButton("Заменить" if component_id is not None else "Добавить")
        select_button.clicked.connect(lambda _checked=False, sid=slot["slot_id"], kinds=types: self._choose_component(sid, kinds))
        layout.addWidget(select_button, 0, 4)
        if component_id is not None:
            open_button = QPushButton("Карточка")
            open_button.clicked.connect(lambda _checked=False, cid=component_id: self._open_component(cid))
            layout.addWidget(open_button, 0, 5)
            clear_button = QPushButton("Очистить")
            clear_button.clicked.connect(lambda _checked=False, sid=slot["slot_id"]: self._clear_slot(sid))
            layout.addWidget(clear_button, 0, 6)
        if dynamic:
            remove_button = QPushButton("Удалить слот")
            remove_button.clicked.connect(lambda _checked=False, sid=slot["slot_id"]: self._delete_slot(sid))
            layout.addWidget(remove_button, 0, 7)
        layout.setColumnStretch(1, 1)
        return row

    def _save_slot_quantity(self, slot_id: int, category: str, editor: QLineEdit) -> None:
        if category not in {"ram", "storage", "case_fan"}:
            return
        text = editor.text().strip()
        try:
            if not text or not text.isascii() or not text.isdigit():
                raise DatabaseError("Введите целое положительное количество.")
            quantity = int(text)
            if quantity < 1 or quantity > 9_223_372_036_854_775_807:
                raise DatabaseError("Количество должно быть от 1 до 9223372036854775807.")
            update_build_slot_quantity(slot_id, quantity, self.database_path)
        except (DatabaseError, ValueError, OverflowError) as error:
            editor.setStyleSheet("border: 1px solid #d9534f;")
            editor.setToolTip(str(error))
            _error(self, "Не удалось сохранить количество", error)
            return
        self.refresh()
        self.composition_changed.emit()

    def _choose_component(self, slot_id: int, component_types: frozenset[str]) -> None:
        if not component_types:
            _error(self, "Категория недоступна", "Для этой категории пока нет соответствующего типа в каталоге.")
            return
        dialog = ComponentPickerDialog(self.database_path, self, component_types)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.component_id is None:
            return
        try:
            set_build_slot_component(slot_id, dialog.component_id, self.database_path)
        except DatabaseError as error:
            _error(self, "Не удалось назначить комплектующее", error)
            return
        self.refresh()
        self.composition_changed.emit()

    def _clear_slot(self, slot_id: int) -> None:
        try:
            set_build_slot_component(slot_id, None, self.database_path)
        except DatabaseError as error:
            _error(self, "Не удалось очистить слот", error)
            return
        self.refresh()
        self.composition_changed.emit()

    def _add_slot(self, category: str) -> None:
        try:
            add_build_slot(self.build_id, category, self.database_path)
        except DatabaseError as error:
            _error(self, "Не удалось добавить слот", error)
            return
        self.refresh()
        self.composition_changed.emit()

    def _delete_slot(self, slot_id: int) -> None:
        try:
            delete_build_slot(slot_id, self.database_path)
        except DatabaseError as error:
            _error(self, "Не удалось удалить слот", error)
            return
        self.refresh()
        self.composition_changed.emit()

    def _open_component(self, component_id: int) -> None:
        ModelCardDialog(component_id, self.database_path, self).exec()
        self.refresh()


EDITOR_CATEGORY_NAMES = {key: label.split(" (")[0] for key, label, *_ in EDITOR_CATEGORIES}


class BuildsPage(QWidget):
    """Список сборок; состав редактируется в отдельном окне-конструкторе."""

    def __init__(self, database_path: Path | str | None = None, status_message=None):
        super().__init__()
        self.database_path = database_path
        self.status_message = status_message or (lambda _message: None)
        layout = QVBoxLayout(self)
        heading = QLabel("Сборки ПК")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(heading)
        toolbar = QHBoxLayout()
        self.new_build_button = QPushButton("Новая сборка")
        self.open_build_button = QPushButton("Открыть конструктор")
        self.edit_build_button = QPushButton("Изменить название и описание")
        self.delete_build_button = QPushButton("Удалить")
        for button in (self.new_build_button, self.open_build_button, self.edit_build_button, self.delete_build_button):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.build_table = QTableWidget(0, 2)
        self.build_table.setMaximumHeight(190)
        self.build_table.setHorizontalHeaderLabels(["Название", "Описание"])
        self.build_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.build_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.build_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.build_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.build_table)
        self.description_label = QLabel("Выберите сборку.")
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)
        self.items_table = QTableWidget(0, 5)
        self.items_table.setHorizontalHeaderLabels(["Категория", "Производитель", "Модель", "Количество", "Состояние"])
        self.items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.items_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.items_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.items_table, 1)

        self.new_build_button.clicked.connect(self._create_build)
        self.open_build_button.clicked.connect(self._edit_build)
        self.edit_build_button.clicked.connect(self._edit_build_details)
        self.delete_build_button.clicked.connect(self._delete_build)
        self.build_table.itemSelectionChanged.connect(self._selection_changed)
        self.build_table.cellDoubleClicked.connect(lambda *_: self._edit_build())
        self.refresh()

    def _selected_build_id(self) -> int | None:
        row = self.build_table.currentRow()
        item = self.build_table.item(row, 0) if row >= 0 else None
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def refresh(self, *_args) -> None:
        selected = self._selected_build_id()
        try:
            builds = list_builds(self.database_path)
        except DatabaseError as error:
            _error(self, "Не удалось загрузить сборки", error)
            builds = []
        self.build_table.setRowCount(len(builds))
        selected_row = -1
        for row, build in enumerate(builds):
            for col, value in enumerate((build["name"], build["description"] or "")):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, build["id"])
                self.build_table.setItem(row, col, item)
            if build["id"] == selected:
                selected_row = row
        if selected_row < 0 and builds:
            selected_row = 0
        if selected_row >= 0:
            self.build_table.selectRow(selected_row)
        else:
            self.items_table.setRowCount(0)
            self.description_label.setText("Создайте сборку или выберите её из списка.")
        self.build_table.resizeColumnsToContents()
        self._selection_changed()
        self.status_message(f"Сохранённых сборок: {len(builds)}")

    def _selection_changed(self, *_args) -> None:
        build_id = self._selected_build_id()
        enabled = build_id is not None
        for button in (self.open_build_button, self.edit_build_button, self.delete_build_button):
            button.setEnabled(enabled)
        if not enabled:
            self.items_table.setRowCount(0)
            self.description_label.setText("Создайте сборку или выберите её из списка.")
            return
        build = get_build(build_id, self.database_path)
        self.description_label.setText(build["description"] or "Описание не указано.")
        self._refresh_items()

    def _refresh_items(self) -> None:
        build_id = self._selected_build_id()
        items = get_build_components(build_id, self.database_path) if build_id is not None else []
        self.items_table.setRowCount(len(items))
        for row, part in enumerate(items):
            values = [
                COMPONENT_TYPE_LABELS.get(part["component_type"], "Комплектующее"),
                part["manufacturer"], part["model_name"], str(part["quantity"]),
                "В архиве" if part["status"] == "archived" else "В наличии",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, part["item_id"])
                self.items_table.setItem(row, column, cell)
        self.items_table.resizeColumnsToContents()

    def _open_editor(self, build_id: int) -> None:
        dialog = BuildEditorDialog(build_id, self.database_path, self.status_message, self)
        dialog.composition_changed.connect(self.refresh)
        dialog.exec()
        self.refresh()

    def _create_build(self) -> None:
        dialog = BuildFormDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, description = dialog.values()
        try:
            build_id = create_build(name, description=description, database_path=self.database_path)
        except DatabaseError as error:
            _error(self, "Не удалось создать сборку", error)
            return
        self.refresh()
        self._open_editor(build_id)

    def _edit_build_details(self) -> None:
        build_id = self._selected_build_id()
        if build_id is None:
            return
        dialog = BuildFormDialog(get_build(build_id, self.database_path), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, description = dialog.values()
        try:
            update_build(build_id, name=name, description=description, database_path=self.database_path)
        except DatabaseError as error:
            _error(self, "Не удалось сохранить сборку", error)
            return
        self.refresh()

    def _edit_build(self) -> None:
        build_id = self._selected_build_id()
        if build_id is not None:
            self._open_editor(build_id)

    def _delete_build(self) -> None:
        build_id = self._selected_build_id()
        build = get_build(build_id, self.database_path) if build_id is not None else None
        if build is None:
            return
        if QMessageBox.question(
            self, "Удалить сборку", f"Удалить сборку «{build['name']}» и её состав? Комплектующие в каталоге останутся.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_build(build_id, self.database_path)
        except DatabaseError as error:
            _error(self, "Не удалось удалить сборку", error)
            return
        self.refresh()
