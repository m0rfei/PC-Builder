"""Редакторы стандартных и дополнительных характеристик модели."""

import math
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QListWidgetItem,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

from .catalog import COMPONENT_TYPE_LABELS
from .database import (
    DatabaseError,
    create_custom_attribute,
    get_custom_attribute_options,
    update_custom_attribute,
    list_custom_attribute_definitions,
    create_custom_attribute_definition,
    update_custom_attribute_definition,
    delete_custom_attribute_definition,
    get_custom_attribute_definition_options,
    get_custom_attribute_definition_usage,
    list_component_custom_values,
    save_custom_attribute_value,
    delete_custom_attribute_value,
)
from .specifications import (
    SPEC_FIELDS as API_SPEC_FIELDS,
    create_component_spec,
    get_component_spec,
    update_component_spec,
    list_specification_options,
)
from .reference_data import INITIAL_SPEC_OPTIONS


FORM_FACTORS = {
    "atx": "ATX", "micro_atx": "Micro-ATX", "mini_itx": "Mini-ITX",
    "extended_atx": "Extended ATX", "mini_dtx": "Mini-DTX", "dtx": "DTX", "ssi_eeb": "SSI-EEB",
}
RAM_TYPES = {key: key.upper() for key in ("ddr", "ddr2", "ddr3", "ddr4", "ddr5")}
PCIE_VERSIONS = {f"{version}.0": f"PCIe {version}.0" for version in range(1, 7)}
VRAM_TYPES = {key: key.upper() for key in (
    "gddr3", "gddr5", "gddr5x", "gddr6", "gddr6x", "gddr7",
    "hbm", "hbm2", "hbm2e", "hbm3", "hbm3e",
)}
PSU_FORM_FACTORS = {
    "atx": "ATX", "sfx": "SFX", "sfx_l": "SFX-L", "tfx": "TFX",
    "flex_atx": "Flex ATX", "1u": "1U", "2u": "2U", "proprietary": "Проприетарный",
}
SSD_FORM_FACTORS = {"2_5_in": "2,5″", "m2": "M.2"}
HDD_FORM_FACTORS = {"2_5_in": "2,5 дюйма", "3_5_in": "3,5 дюйма"}
EFFICIENCY = {
    "80_plus": "80 PLUS", "80_plus_bronze": "80 PLUS Bronze", "80_plus_silver": "80 PLUS Silver",
    "80_plus_gold": "80 PLUS Gold", "80_plus_platinum": "80 PLUS Platinum",
    "80_plus_titanium": "80 PLUS Titanium",
}
GPU_CONNECTORS = {
    "pcie_6pin": "PCIe 6 pin", "pcie_8pin": "PCIe 8 pin",
    "12vhpwr": "12VHPWR", "12v_2x6": "12V-2x6",
}
FAN_CONNECTORS = {
    "3_pin": "3 pin", "4_pin_pwm": "4 pin PWM", "molex_4pin": "Molex 4 pin",
    "sata_power": "Питание SATA", "proprietary": "Проприетарный", "other": "Другой",
}

# Поля задаются в том же составе и с теми же ключами, что и в схеме v3.
SPEC_FIELDS = {
    "cpu": [
        ("socket", "Сокет", "text", ""), ("ram_type", "Тип поддерживаемой памяти", "enum", RAM_TYPES),
        ("pcie_version", "Версия PCIe", "enum", PCIE_VERSIONS), ("cores", "Физические ядра", "int", "шт."),
        ("threads", "Потоки", "int", "шт."), ("base_clock_mhz", "Базовая частота", "number", "МГц"),
        ("boost_clock_mhz", "Максимальная частота", "number", "МГц"), ("tdp_w", "TDP", "number", "Вт"),
        ("has_integrated_gpu", "Интегрированная графика", "bool", ""),
    ],
    "motherboard": [
        ("socket", "Сокет", "text", ""), ("chipset", "Чипсет", "text", ""),
        ("form_factor", "Форм-фактор", "enum", FORM_FACTORS),
        ("supported_ram_types", "Поддерживаемые типы памяти", "ram_types", RAM_TYPES),
        ("ram_slots", "Слоты памяти", "int", "шт."), ("max_ram_gb", "Максимальный объём памяти", "number", "ГБ"),
        ("max_ram_clock_mhz", "Максимальная частота памяти", "number", "МГц"),
        ("m2_slots", "Слоты M.2", "int", "шт."), ("sata_ports", "Порты SATA", "int", "шт."),
        ("pcie_version", "Версия PCIe", "enum", PCIE_VERSIONS),
    ],
    "ram": [
        ("ram_type", "Тип памяти", "enum", RAM_TYPES), ("capacity_gb", "Объём модуля", "memory", "ГБ"),
        ("frequency_mhz", "Частота", "number", "МГц"),
        ("form_factor", "Форм-фактор", "enum", {"dimm": "DIMM", "so_dimm": "SO-DIMM"}),
        ("ecc", "Поддержка ECC", "bool", ""),
    ],
    "gpu": [
        ("chip_manufacturer", "Производитель графического чипа", "choice_text", INITIAL_SPEC_OPTIONS["gpu"]["chip_manufacturer"]),
        ("vram_gb", "Объём видеопамяти", "memory", "ГБ"), ("vram_type", "Тип видеопамяти", "enum", VRAM_TYPES),
        ("length_mm", "Длина", "number", "мм"), ("thickness_mm", "Толщина", "number", "мм"),
        ("slot_width", "Ширина в слотах", "number", "слота"), ("power_w", "Энергопотребление", "number", "Вт"),
        ("recommended_psu_w", "Рекомендуемая мощность БП", "number", "Вт"),
        ("cooling_type", "Тип охлаждения", "enum", {"air": "Воздушное", "passive": "Пассивное"}),
        ("power_connectors", "Разъёмы питания", "connectors", GPU_CONNECTORS),
    ],
    "psu": [
        ("rated_power_w", "Номинальная мощность", "number", "Вт"),
        ("modularity", "Модульность кабелей", "enum", INITIAL_SPEC_OPTIONS["psu"]["modularity"]),
        ("form_factor", "Форм-фактор", "enum", PSU_FORM_FACTORS),
        ("efficiency_rating", "Сертификация эффективности", "enum", EFFICIENCY),
        ("pcie_6_2pin_count", "Разъёмы PCIe 6+2 pin", "int", "шт."),
        ("eps_4_4pin_count", "Разъёмы EPS 4+4 pin", "int", "шт."),
        ("native_12vhpwr", "Нативный 12VHPWR", "bool", ""),
        ("native_12v2x6", "Нативный 12V-2x6", "bool", ""),
        ("sata_power_count", "Разъёмы питания SATA", "int", "шт."),
    ],
    "ssd": [
        ("capacity_gb", "Ёмкость", "number", "ГБ"), ("form_factor", "Форм-фактор", "enum", SSD_FORM_FACTORS),
        ("interface_type", "Интерфейс", "enum", {"sata": "SATA", "pcie": "PCIe"}),
        ("protocol", "Протокол", "enum", {"nvme": "NVMe"}),
        ("pcie_version", "Версия PCIe", "enum", PCIE_VERSIONS), ("power_w", "Энергопотребление", "number", "Вт"),
    ],
    "hdd": [
        ("capacity_gb", "Ёмкость", "number", "ГБ"), ("form_factor", "Форм-фактор", "enum", HDD_FORM_FACTORS),
        ("interface_type", "Интерфейс", "enum", {"sata": "SATA"}),
        ("power_w", "Энергопотребление", "number", "Вт"),
    ],
    "cpu_cooler": [
        ("supported_sockets", "Поддерживаемые сокеты", "strings", None),
        ("height_mm", "Высота", "number", "мм"), ("power_w", "Энергопотребление", "number", "Вт"),
    ],
    "case_fan": [
        ("size_mm", "Размер", "number", "мм"), ("thickness_mm", "Толщина", "number", "мм"),
        ("connector_type", "Тип подключения", "enum", FAN_CONNECTORS),
        ("lighting", "Подсветка", "bool", ""),
        ("power_w", "Энергопотребление", "number", "Вт"), ("max_rpm", "Максимальная скорость", "int", "об/мин"),
    ],
    "case": [
        ("form_factors_supported", "Поддерживаемые форм-факторы плат", "form_factors", FORM_FACTORS),
        ("max_gpu_length_mm", "Максимальная длина видеокарты", "number", "мм"),
        ("max_cpu_cooler_height_mm", "Максимальная высота кулера", "number", "мм"),
        ("max_psu_length_mm", "Максимальная длина БП", "number", "мм"),
        ("drive_2_5_bays", "Места для накопителей 2,5 дюйма", "int", "шт."),
        ("drive_3_5_bays", "Места для накопителей 3,5 дюйма", "int", "шт."),
        ("radiator_support", "Поддерживаемые радиаторы", "radiators", None),
    ],
}

STANDARD_FIELD_LABELS = {
    key: label for fields in SPEC_FIELDS.values() for key, label, _kind, _extra in fields
}


def _show_message(parent, icon: QMessageBox.Icon, title: str, text: str, button_text: str = "Закрыть") -> None:
    dialog = QMessageBox(icon, title, text, QMessageBox.StandardButton.NoButton, parent)
    dialog.addButton(button_text, QMessageBox.ButtonRole.AcceptRole)
    dialog.exec()


class MemorySizeEditor(QWidget):
    """Вводит объём в MB или GB, сохраняя внутри схемы значение в GB."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.number = QDoubleSpinBox()
        self.number.setRange(0, 1_000_000_000)
        self.number.setDecimals(6)
        self.number.setSpecialValueText("Не указано")
        self.number.setKeyboardTracking(False)
        self.unit = QComboBox()
        self.unit.addItem("МБ", "mb")
        self.unit.addItem("ГБ", "gb")
        self.unit.setCurrentIndex(1)
        self._last_unit = "gb"
        layout.addWidget(self.number, 1)
        layout.addWidget(self.unit)
        self.unit.currentIndexChanged.connect(self._unit_changed)
        self._set_suffix()

    def _set_suffix(self) -> None:
        self.number.setSuffix("")

    def _unit_changed(self, *_args) -> None:
        if self.unit.currentData() != getattr(self, "_last_unit", "gb"):
            value = self.number.value()
            if value:
                if self._last_unit == "gb":
                    value *= 1024
                else:
                    value /= 1024
                self.number.setValue(value)
            self._last_unit = self.unit.currentData()
        self._set_suffix()

    def set_gb(self, value: float | None) -> None:
        desired_unit = "mb" if value is not None and 0 < value < 1 else "gb"
        self.unit.setCurrentIndex(self.unit.findData(desired_unit))
        self._last_unit = desired_unit
        self.number.setValue(0 if value is None else value * 1024 if desired_unit == "mb" else value)
        self._set_suffix()

    def value_gb(self) -> float | None:
        value = self.number.value()
        if value == 0:
            return None
        return value / 1024 if self.unit.currentData() == "mb" else value


class MultiValueEditor(QWidget):
    """Небольшой список для сокетов, форм-факторов или размеров радиаторов."""

    valuesChanged = Signal()

    def __init__(self, kind: str, choices: dict[str, str] | None = None, parent=None):
        super().__init__(parent)
        self.kind = kind
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.items = QListWidget()
        layout.addWidget(self.items)
        controls = QHBoxLayout()
        self.text_input: QComboBox | None = None
        self.choice_input: QComboBox | None = None
        self.number_input: QSpinBox | None = None
        if kind == "strings":
            self.text_input = QComboBox()
            self.text_input.setEditable(True)
            self.text_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            for key, label in (choices or {}).items():
                self.text_input.addItem(label, key)
            self.text_input.setCurrentIndex(-1)
            self.text_input.setPlaceholderText("Введите или выберите значение")
            controls.addWidget(self.text_input, 1)
        elif kind in {"form_factors", "ram_types"}:
            self.choice_input = QComboBox()
            self.choice_input.setEditable(kind != "ram_types")
            self.choice_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            for key, label in (choices or {}).items():
                self.choice_input.addItem(label, key)
            self.choice_input.setCurrentIndex(
                0 if kind == "form_factors" and self.choice_input.count() else -1
            )
            controls.addWidget(self.choice_input, 1)
        else:
            self.number_input = QSpinBox()
            self.number_input.setRange(1, 10000)
            self.number_input.setSuffix(" мм")
            controls.addWidget(self.number_input, 1)
        add_button = QPushButton("Добавить")
        remove_button = QPushButton("Удалить выбранное")
        add_button.clicked.connect(self.add_current)
        remove_button.clicked.connect(self.remove_selected)
        controls.addWidget(add_button)
        controls.addWidget(remove_button)
        layout.addLayout(controls)

    def values(self) -> list[Any]:
        return [self.items.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self.items.count())]

    def set_values(self, values: list[Any]) -> None:
        self.items.clear()
        for value in values:
            self._append(value)

    def _append(self, value: Any) -> None:
        display = None
        if self.kind in {"ram_types", "form_factors"} and self.choice_input is not None:
            index = self.choice_input.findData(value)
            if index >= 0:
                display = self.choice_input.itemText(index)
        item = QListWidgetItem(display or str(value))
        item.setData(Qt.ItemDataRole.UserRole, value)
        self.items.addItem(item)

    def add_current(self) -> None:
        if self.kind == "strings":
            value = self.text_input.currentData()
            if value is None:
                value = self.text_input.currentText()
            value = value.strip()
            if not value:
                return
            self.text_input.setCurrentIndex(-1)
            self.text_input.setEditText("")
        elif self.kind in {"form_factors", "ram_types"}:
            value = self.choice_input.currentData()
            if value is None:
                value = self.choice_input.currentText().strip()
            if not value:
                return
        else:
            value = self.number_input.value()
        if value not in self.values():
            self._append(value)
            self.valuesChanged.emit()

    def remove_selected(self) -> None:
        row = self.items.currentRow()
        if row >= 0:
            self.items.takeItem(row)
            self.valuesChanged.emit()


class ConnectorEditor(QWidget):
    """Структурированный ввод типа и количества разъёмов видеокарты."""

    valuesChanged = Signal()

    def __init__(self, choices: dict[str, str] | None = None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Тип разъёма", "Число разъёмов"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(100)
        self.choices = choices or GPU_CONNECTORS
        layout.addWidget(self.table)
        controls = QHBoxLayout()
        add_button = QPushButton("Добавить разъём")
        remove_button = QPushButton("Удалить выбранное")
        add_button.clicked.connect(self.add_row)
        remove_button.clicked.connect(self.remove_row)
        controls.addWidget(add_button)
        controls.addWidget(remove_button)
        controls.addStretch()
        layout.addLayout(controls)

    def set_values(self, values: dict[str, int]) -> None:
        self.table.setRowCount(0)
        for connector, count in values.items():
            self._insert(connector, count)

    def _insert(self, connector: str, count: int) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for key, label in self.choices.items():
            combo.addItem(label, key)
        index = combo.findData(connector)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setEditText(connector)
        self.table.setCellWidget(row, 0, combo)
        quantity = QSpinBox()
        quantity.setRange(1, 100)
        quantity.setValue(count)
        self.table.setCellWidget(row, 1, quantity)
        combo.activated.connect(self.valuesChanged.emit)
        combo.lineEdit().editingFinished.connect(self.valuesChanged.emit)
        quantity.editingFinished.connect(self.valuesChanged.emit)

    def add_row(self) -> None:
        self._insert("pcie_8pin", 1)
        self.valuesChanged.emit()

    def remove_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self.valuesChanged.emit()

    def values(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 0)
            quantity = self.table.cellWidget(row, 1)
            connector = combo.currentData()
            if connector in result:
                raise ValueError("Один тип разъёма добавлен несколько раз. Объедините его в одну строку.")
            if connector is None:
                connector = combo.currentText().strip()
            if not connector:
                raise ValueError("Выберите или введите тип разъёма.")
            result[connector] = quantity.value()
        return result


class SpecificationsEditor(QWidget):
    """Форма типизированных характеристик для одного типа модели."""

    def __init__(self, model_id: int | None, component_type: str, database_path: Path | str | None = None, parent=None, *, auto_save: bool = False):
        super().__init__(parent)
        self.model_id = model_id
        self.component_type = component_type
        self.database_path = database_path
        self.auto_save = auto_save
        self._loading = False
        self.controls: dict[str, QWidget] = {}
        self.setMinimumWidth(600)

        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QWidget()
        self.form = QFormLayout(form_widget)
        self._build_form()
        if auto_save:
            root.addWidget(form_widget, 1)
        else:
            scroll.setWidget(form_widget)
            root.addWidget(scroll, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        footer = QHBoxLayout()
        cancel_button = QPushButton("Отмена")
        save_button = QPushButton("Сохранить спецификации")
        cancel_button.clicked.connect(self.cancel_changes)
        save_button.clicked.connect(self.save)
        footer.addWidget(self.status, 1)
        footer.addWidget(cancel_button)
        footer.addWidget(save_button)
        if not auto_save:
            footer.addWidget(self.status, 1)
            root.addLayout(footer)
        else:
            root.addWidget(self.status)
            cancel_button.hide()
            save_button.hide()
        self.load()

    def _build_form(self) -> None:
        for key, label, kind, extra in SPEC_FIELDS[self.component_type]:
            if kind == "text" and key in {"socket", "chipset"}:
                control = self._choice_combo(key, editable=True)
            elif kind in {"text", "choice_text"}:
                if kind == "choice_text":
                    control = self._choice_combo(key, extra, editable=True)
                else:
                    control = QLineEdit()
            elif kind in {"int", "number"}:
                if kind == "int":
                    control = QSpinBox()
                    control.setRange(0 if key in {"cores", "threads"} else -1, 2_000_000_000)
                    control.setSpecialValueText("Не указано")
                else:
                    control = QDoubleSpinBox()
                    control.setDecimals(5)
                    sentinel = 0.0 if key in {
                        "capacity_gb", "frequency_mhz", "base_clock_mhz", "boost_clock_mhz",
                        "max_ram_gb", "max_ram_clock_mhz", "vram_gb", "size_mm",
                    } else -0.00001
                    control.setRange(sentinel, 1_000_000_000.0)
                    control.setSpecialValueText("Не указано")
                control.setKeyboardTracking(False)
                if extra:
                    control.setSuffix(" " + extra)
            elif kind == "memory":
                control = MemorySizeEditor()
            elif kind == "bool":
                control = QComboBox()
                control.addItem("Не указано", None)
                control.addItem("Да", True)
                control.addItem("Нет", False)
            elif kind == "enum":
                control = self._choice_combo(key, extra, editable=True)
            elif kind in {"strings", "form_factors", "radiators", "ram_types"}:
                choices = extra
                option_field = "socket" if key == "supported_sockets" else key
                if kind in {"strings", "form_factors"}:
                    choices = self._option_map(option_field, extra)
                elif kind == "ram_types":
                    choices = self._option_map("ram_type", extra)
                control = MultiValueEditor(kind, choices)
            elif kind == "connectors":
                control = ConnectorEditor(self._option_map(key, extra))
            else:
                raise ValueError(f"Неизвестный тип редактора поля: {kind}")
            self.controls[key] = control
            self.form.addRow(label + ":", control)
            if self.auto_save:
                self._connect_autosave(key, kind, control)
            elif isinstance(control, QLineEdit):
                control.textEdited.connect(self._clear_status)
            elif isinstance(control, QComboBox):
                control.currentIndexChanged.connect(self._clear_status)
                control.currentTextChanged.connect(self._clear_status)
            elif isinstance(control, QSpinBox):
                control.valueChanged.connect(self._clear_status)
            elif isinstance(control, QDoubleSpinBox):
                control.valueChanged.connect(self._clear_status)
            elif isinstance(control, MemorySizeEditor):
                control.number.valueChanged.connect(self._clear_status)

    def _connect_autosave(self, key: str, kind: str, control: QWidget) -> None:
        if isinstance(control, MultiValueEditor):
            control.valuesChanged.connect(lambda key=key: self._save_field(key))
        elif isinstance(control, ConnectorEditor):
            control.valuesChanged.connect(lambda key=key: self._save_field(key))
        elif isinstance(control, MemorySizeEditor):
            control.number.editingFinished.connect(lambda key=key: self._save_field(key))
            control.unit.currentIndexChanged.connect(lambda _index, key=key: self._save_field(key))
        elif isinstance(control, QComboBox):
            control.activated.connect(lambda _index, key=key: self._save_field(key))
            if control.isEditable() and control.lineEdit():
                control.lineEdit().editingFinished.connect(lambda key=key: self._save_field(key))
            elif kind == "bool":
                control.currentIndexChanged.connect(lambda _index, key=key: self._save_field(key))
        elif isinstance(control, QLineEdit):
            control.editingFinished.connect(lambda key=key: self._save_field(key))
        elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
            control.editingFinished.connect(lambda key=key: self._save_field(key))

    def _option_map(self, field: str, initial: dict[str, str] | None = None) -> dict[str, str]:
        result = dict(initial or {})
        for item in list_specification_options(self.component_type, field, self.database_path):
            result[item["value"]] = item["display_value"]
        return result

    def _choice_combo(self, field: str, initial: dict[str, str] | None = None, *, editable: bool = True) -> QComboBox:
        combo = QComboBox()
        combo.addItem("Не указано", None)
        combo.setEditable(editable)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        options = self._option_map(field, initial)
        narrowed = {
            ("ram", "ram_type"): RAM_TYPES,
            ("motherboard", "ram_type"): RAM_TYPES,
            ("cpu", "ram_type"): RAM_TYPES,
            ("ram", "form_factor"): {"dimm": "DIMM", "so_dimm": "SO-DIMM"},
            ("ssd", "form_factor"): SSD_FORM_FACTORS,
            ("ssd", "interface_type"): {"sata": "SATA", "pcie": "PCIe"},
            ("hdd", "interface_type"): {"sata": "SATA"},
        }
        base = narrowed.get((self.component_type, field))
        if base is not None:
            selected = (get_component_spec(self.model_id, self.database_path) or {}).get(field) if self.model_id is not None else None
            options = dict(base)
            if selected is not None and selected not in options:
                saved = next((item["display_value"] for item in list_specification_options(
                    self.component_type, field, self.database_path
                ) if item["value"] == selected), str(selected))
                options[selected] = saved
        for value, display in options.items():
            combo.addItem(display, value)
        combo.setCurrentIndex(0)
        return combo

    def load(self) -> None:
        if self.model_id is None:
            self._loading = True
            for key, _label, kind, _extra in SPEC_FIELDS[self.component_type]:
                control = self.controls[key]
                if kind in {"int", "number"}:
                    control.setValue(control.minimum())
                elif kind == "memory":
                    control.set_gb(None)
                elif kind in {"text", "choice_text", "enum", "bool"} and isinstance(control, QComboBox):
                    control.setCurrentIndex(0)
                    if control.isEditable():
                        control.setEditText("")
                elif kind in {"strings", "form_factors", "radiators", "ram_types"}:
                    control.set_values([])
                elif kind == "connectors":
                    control.set_values({})
            self._loading = False
            return
        self._loading = True
        try:
            spec = get_component_spec(self.model_id, self.database_path) or {}
        except DatabaseError as error:
            self.status.setText(f"Не удалось загрузить спецификации: {error}")
            self._loading = False
            return
        for key, _label_text, kind, _extra in SPEC_FIELDS[self.component_type]:
            control = self.controls[key]
            value = spec.get(key)
            if kind == "text" and isinstance(control, QLineEdit):
                control.setText(value or "")
            elif kind in {"text", "choice_text", "enum"} and isinstance(control, QComboBox):
                if value is None:
                    control.setCurrentIndex(0)
                    if control.isEditable():
                        control.setEditText("")
                else:
                    index = control.findData(value)
                    if index >= 0:
                        control.setCurrentIndex(index)
                    else:
                        control.setEditText(str(value))
            elif kind in {"int", "number"}:
                control.setValue(control.minimum() if value is None else value)
            elif kind == "memory":
                control.set_gb(value)
            elif kind in {"bool", "enum"}:
                index = control.findData(value)
                control.setCurrentIndex(index if index >= 0 else 0)
            elif kind in {"strings", "form_factors", "radiators", "ram_types"}:
                control.set_values(value or [])
            elif kind == "connectors":
                control.set_values(value or {})
        self._loading = False

    def _values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, _label_text, kind, _extra in SPEC_FIELDS[self.component_type]:
            control = self.controls[key]
            if kind == "text" and isinstance(control, QLineEdit):
                result[key] = control.text().strip() or None
            elif kind in {"text", "choice_text", "enum"} and isinstance(control, QComboBox):
                value = control.currentData()
                if value is None:
                    text = control.currentText().strip()
                    value = text if text and text != "Не указано" else None
                result[key] = value
            elif kind in {"int", "number"}:
                if control.value() == control.minimum():
                    result[key] = None
                else:
                    result[key] = int(control.value()) if kind == "int" else float(control.value())
            elif kind == "memory":
                result[key] = control.value_gb()
            elif kind in {"bool", "enum"}:
                result[key] = control.currentData()
            elif kind in {"strings", "form_factors", "radiators", "ram_types"}:
                result[key] = control.values()
            elif kind == "connectors":
                result[key] = control.values()
        return result

    def save(self) -> None:
        try:
            values = self._values()
            if get_component_spec(self.model_id, self.database_path) is None:
                create_component_spec(self.model_id, database_path=self.database_path, **values)
            else:
                update_component_spec(self.model_id, database_path=self.database_path, **values)
        except (DatabaseError, ValueError) as error:
            self.status.setText(f"Не удалось сохранить спецификации: {error}")
            return
        self.status.setText("Спецификации сохранены.")

    def bind_model(self, model_id: int) -> None:
        """Привязывает черновую форму к уже созданному комплектующему, не перезагружая ввод."""
        self.model_id = model_id

    def _save_field(self, key: str) -> bool:
        if self._loading or not self.auto_save or self.model_id is None:
            return False
        control = self.controls[key]
        try:
            value = self._field_value(key)
            if get_component_spec(self.model_id, self.database_path) is None:
                create_component_spec(self.model_id, database_path=self.database_path, **{key: value})
            else:
                update_component_spec(self.model_id, database_path=self.database_path, **{key: value})
        except (DatabaseError, ValueError, TypeError) as error:
            control.setStyleSheet("border: 1px solid #d9534f;")
            control.setToolTip(str(error))
            label = next(item[1] for item in SPEC_FIELDS[self.component_type] if item[0] == key)
            self.status.setText(f"{label}: {error}")
            return False
        control.setStyleSheet("")
        control.setToolTip("")
        self.status.setText("Изменение сохранено.")
        return True

    def _field_value(self, key: str) -> Any:
        kind = next(field[2] for field in SPEC_FIELDS[self.component_type] if field[0] == key)
        control = self.controls[key]
        if kind == "text" and isinstance(control, QLineEdit):
            return control.text().strip() or None
        if kind in {"text", "choice_text", "enum"} and isinstance(control, QComboBox):
            value = control.currentData()
            if value is None:
                text = control.currentText().strip()
                value = text if text and text != "Не указано" else None
            return value
        if kind in {"int", "number"}:
            if control.value() == control.minimum():
                return None
            return int(control.value()) if kind == "int" else float(control.value())
        if kind == "memory":
            return control.value_gb()
        if kind == "bool":
            return control.currentData()
        if kind in {"strings", "form_factors", "radiators", "ram_types"}:
            return control.values()
        if kind == "connectors":
            return control.values()
        raise ValueError(f"Неизвестный тип поля {kind!r}.")

    def save_pending(self) -> bool:
        """Сохраняет каждое поле отдельно, чтобы ошибка одного не блокировала остальные."""
        results = [self._save_field(key) for key, *_ in SPEC_FIELDS[self.component_type]]
        return all(results)

    def cancel_changes(self) -> None:
        self.status.clear()
        self.load()
        if not self.status.text():
            self.status.setText("Несохранённые изменения отменены.")

    def _clear_status(self, *_args) -> None:
        self.status.clear()


class CustomAttributeDialog(QDialog):
    """Форма одной пользовательской характеристики."""

    TYPE_LABELS = {"text": "Текст", "number": "Число", "boolean": "Да / нет", "enum": "Список"}

    def __init__(
        self,
        model_id: int,
        component_type: str,
        database_path: Path | str | None = None,
        attribute: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.model_id = model_id
        self.component_type = component_type
        self.database_path = database_path
        self.attribute = attribute
        self.attribute_id: int | None = attribute["id"] if attribute else None
        self.setWindowTitle("Изменить характеристику" if attribute else "Добавить характеристику")
        self.resize(520, 500)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit()
        self.type_combo = QComboBox()
        for value_type, label in self.TYPE_LABELS.items():
            self.type_combo.addItem(label, value_type)
        self.value_stack = QStackedWidget()
        self.text_input = QLineEdit()
        self.number_input = QDoubleSpinBox()
        self.number_input.setRange(-1e12, 1e12)
        self.number_input.setDecimals(8)
        self.number_input.setKeyboardTracking(False)
        self.boolean_input = QComboBox()
        self.boolean_input.addItem("Да", True)
        self.boolean_input.addItem("Нет", False)
        enum_widget = QWidget()
        enum_layout = QVBoxLayout(enum_widget)
        enum_layout.setContentsMargins(0, 0, 0, 0)
        self.enum_input = QComboBox()
        self.enum_input.setEditable(True)
        self.enum_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.enum_input.setPlaceholderText("Выберите или введите значение")
        self.enum_options_input = QLineEdit()
        self.enum_options_input.setPlaceholderText("Новый вариант")
        self.enum_options_list = QListWidget()
        self.enum_options_list.setMaximumHeight(110)
        option_controls = QHBoxLayout()
        add_option = QPushButton("Добавить вариант")
        remove_option = QPushButton("Удалить выбранный")
        add_option.clicked.connect(self._add_enum_option)
        remove_option.clicked.connect(self._remove_enum_option)
        option_controls.addWidget(self.enum_options_input, 1)
        option_controls.addWidget(add_option)
        option_controls.addWidget(remove_option)
        self.enum_legacy_warning = QLabel()
        self.enum_legacy_warning.setWordWrap(True)
        enum_layout.addWidget(self.enum_input)
        enum_layout.addWidget(QLabel("Допустимые варианты:"))
        enum_layout.addWidget(self.enum_options_list)
        enum_layout.addLayout(option_controls)
        enum_layout.addWidget(self.enum_legacy_warning)
        for widget in (self.text_input, self.number_input, self.boolean_input, enum_widget):
            self.value_stack.addWidget(widget)
        self.unit_input = QLineEdit()
        form.addRow("Название:", self.name_input)
        form.addRow("Тип значения:", self.type_combo)
        form.addRow("Значение:", self.value_stack)
        form.addRow("Единица измерения:", self.unit_input)
        layout.addLayout(form)

        self.duplicate_warning = QLabel()
        self.duplicate_warning.setWordWrap(True)
        layout.addWidget(self.duplicate_warning)
        self.type_combo.currentIndexChanged.connect(self._type_changed)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if attribute:
            self.name_input.setText(attribute["name"])
            index = self.type_combo.findData(attribute["value_type"])
            self.type_combo.setCurrentIndex(max(index, 0))
            self.unit_input.setText(attribute["unit"] or "")
            self._load_value(attribute)
        self._type_changed()

    def _load_value(self, attribute: dict) -> None:
        value_type = attribute["value_type"]
        value_column = {"text": "value_text", "number": "value_number", "boolean": "value_boolean", "enum": "value_enum"}[value_type]
        value = attribute[value_column]
        if value_type == "text":
            self.text_input.setText(value or "")
        elif value_type == "number":
            self.number_input.setValue(0 if value is None else value)
        elif value_type == "boolean":
            self.boolean_input.setCurrentIndex(0 if value else 1)
        else:
            options = get_custom_attribute_options(attribute["id"], self.database_path)
            self.enum_input.clear()
            self.enum_options_list.clear()
            for option in options:
                self.enum_input.addItem(option, option)
                self.enum_options_list.addItem(option)
            if value:
                index = self.enum_input.findData(value)
                if index >= 0:
                    self.enum_input.setCurrentIndex(index)
                else:
                    self.enum_input.setEditText(value)
            self.enum_legacy_warning.setText(
                "Для этой старой характеристики варианты ранее не сохранялись. Старое значение сохранено; добавьте варианты при необходимости."
                if not options else ""
            )

    def _add_enum_option(self) -> None:
        value = self.enum_options_input.text().strip()
        if not value:
            return
        if any(self.enum_options_list.item(index).text() == value for index in range(self.enum_options_list.count())):
            return
        self.enum_options_list.addItem(value)
        self.enum_input.addItem(value, value)
        self.enum_input.setCurrentIndex(self.enum_input.count() - 1)
        self.enum_options_input.clear()

    def _remove_enum_option(self) -> None:
        row = self.enum_options_list.currentRow()
        if row < 0:
            return
        value = self.enum_options_list.item(row).text()
        self.enum_options_list.takeItem(row)
        index = self.enum_input.findData(value)
        if index >= 0:
            self.enum_input.removeItem(index)

    def _type_changed(self, *_args) -> None:
        self.value_stack.setCurrentIndex(self.type_combo.currentIndex())
        if self.type_combo.currentData() == "enum":
            self.enum_legacy_warning.show()
        else:
            self.enum_legacy_warning.hide()

    def _value(self) -> str | float | bool:
        value_type = self.type_combo.currentData()
        if value_type == "text":
            return self.text_input.text()
        if value_type == "number":
            value = self.number_input.value()
            if not math.isfinite(value):
                raise ValueError("Введите конечное число.")
            return value
        if value_type == "boolean":
            return self.boolean_input.currentData()
        value = self.enum_input.currentData()
        if value is None:
            value = self.enum_input.currentText().strip()
        if not value:
            raise ValueError("Укажите сохраняемое значение перечисления.")
        return value

    def _save(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            self.duplicate_warning.setText("Укажите название характеристики.")
            return
        standard_names = {
            STANDARD_FIELD_LABELS[key].casefold() for key in API_SPEC_FIELDS[self.component_type]
            if key in STANDARD_FIELD_LABELS
        }
        standard_keys = {key.casefold() for key in API_SPEC_FIELDS[self.component_type]}
        if name.casefold() in standard_names | standard_keys:
            self.duplicate_warning.setText(
                "Это название совпадает со стандартной характеристикой типа "
                f"«{COMPONENT_TYPE_LABELS[self.component_type]}». Выберите другое название."
            )
            return
        try:
            value = self._value()
            value_type = self.type_combo.currentData()
            unit = self.unit_input.text().strip() or None
            enum_options = [self.enum_options_list.item(index).text() for index in range(self.enum_options_list.count())]
            if value_type == "enum":
                if enum_options and value not in enum_options:
                    raise ValueError("Выбранное значение должно быть одним из вариантов списка.")
                if not self.attribute and not enum_options:
                    raise ValueError("Добавьте хотя бы один вариант для нового списка.")
            else:
                enum_options = []
            if self.attribute:
                update_custom_attribute(
                    self.attribute_id, name, value_type, value,
                    unit=unit, enum_options=enum_options, database_path=self.database_path,
                )
            else:
                self.attribute_id = create_custom_attribute(
                    self.model_id, name, value_type, value,
                    unit=unit, enum_options=enum_options, database_path=self.database_path,
                )
        except (DatabaseError, ValueError) as error:
            self.duplicate_warning.setText(f"Не удалось сохранить характеристику: {error}")
            return
        self.accept()


class CustomAttributesEditor(QWidget):
    """Показывает определения категории и редактирует только значения модели."""

    def __init__(self, model_id: int, component_type: str, database_path: Path | str | None = None, parent=None):
        super().__init__(parent)
        self.model_id = model_id
        self.component_type = component_type
        self.database_path = database_path
        layout = QVBoxLayout(self)
        note = QLabel("Определения редактируются в разделе «Пользовательские характеристики».")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Характеристика", "Тип", "Значение", "Единица"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda _row, _column: self.edit_selected())
        layout.addWidget(self.table, 1)
        controls = QHBoxLayout()
        self.edit_button = QPushButton("Изменить значение")
        self.edit_button.clicked.connect(self.edit_selected)
        controls.addWidget(self.edit_button)
        controls.addStretch()
        layout.addLayout(controls)
        self.refresh()

    def refresh(self) -> None:
        try:
            attributes = list_component_custom_values(self.model_id, self.component_type, self.database_path)
        except DatabaseError as error:
            _show_message(self, QMessageBox.Icon.Critical, "Ошибка характеристик", str(error))
            return
        self.attributes = attributes
        self.table.setRowCount(len(attributes))
        labels = CustomAttributeDialog.TYPE_LABELS
        for row, attribute in enumerate(attributes):
            value_column = {"text": "value_text", "number": "value_number", "boolean": "value_boolean", "enum": "value_enum"}[attribute["value_type"]]
            value = attribute[value_column]
            if attribute["value_type"] == "boolean":
                value = "" if value is None else ("Да" if value else "Нет")
            values = [attribute["name"], labels.get(attribute["value_type"], attribute["value_type"]), "—" if attribute["attribute_id"] is None else str(value), attribute["unit"] or ""]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def _selected_definition(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.attributes[self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)]

    def edit_selected(self) -> None:
        definition = self._selected_definition()
        if definition is None:
            _show_message(self, QMessageBox.Icon.Information, "Характеристика не выбрана", "Выберите строку для изменения значения.")
            return
        dialog = CustomAttributeValueDialog(self.model_id, definition, self.database_path, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()


class CustomAttributeValueDialog(QDialog):
    """Редактор значения одного заранее определённого поля."""

    def __init__(self, model_id: int, definition: dict, database_path=None, parent=None):
        super().__init__(parent)
        self.model_id = model_id
        self.definition = definition
        self.database_path = database_path
        self.setWindowTitle("Значение: " + definition["name"])
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.value_input = None
        existing = next((item for item in list_component_custom_values(
            model_id, definition["component_type"], database_path
        ) if item["definition_id"] == definition["definition_id"]), None)
        self.existing = existing
        kind = definition["value_type"]
        if kind == "text":
            self.value_input = QLineEdit()
            if existing and existing["value_text"] is not None:
                self.value_input.setText(existing["value_text"])
        elif kind == "number":
            self.value_input = QLineEdit()
            validator = QDoubleValidator(-1e12, 1e12, 8, self.value_input)
            validator.setNotation(QDoubleValidator.Notation.StandardNotation)
            self.value_input.setValidator(validator)
            if existing and existing["value_number"] is not None:
                self.value_input.setText(str(existing["value_number"]))
        elif kind == "boolean":
            self.value_input = QComboBox()
            self.value_input.addItem("Не задано", None)
            self.value_input.addItem("Да", True)
            self.value_input.addItem("Нет", False)
            if existing and existing["value_boolean"] is not None:
                self.value_input.setCurrentIndex(1 if existing["value_boolean"] else 2)
        else:
            self.value_input = QComboBox()
            self.value_input.addItem("Не задано", None)
            options = get_custom_attribute_definition_options(definition["definition_id"], database_path)
            current = existing["value_enum"] if existing else None
            if current and current not in options:
                options.append(current)
            for option in options:
                self.value_input.addItem(option, option)
            if current:
                self.value_input.setCurrentIndex(self.value_input.findData(current))
        form.addRow(definition["name"] + (f" ({definition['unit']})" if definition["unit"] else ""), self.value_input)
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        kind = self.definition["value_type"]
        control = self.value_input
        raw = control.text().strip() if kind in {"text", "number"} else control.currentData()
        try:
            if kind == "text":
                if not raw:
                    delete_custom_attribute_value(self.model_id, self.definition["definition_id"], self.database_path)
                else:
                    save_custom_attribute_value(self.model_id, self.definition["definition_id"], raw, self.database_path)
            elif kind == "number":
                if not raw:
                    delete_custom_attribute_value(self.model_id, self.definition["definition_id"], self.database_path)
                else:
                    number = float(raw.replace(",", "."))
                    save_custom_attribute_value(self.model_id, self.definition["definition_id"], number, self.database_path)
            elif raw is None:
                delete_custom_attribute_value(self.model_id, self.definition["definition_id"], self.database_path)
            else:
                save_custom_attribute_value(self.model_id, self.definition["definition_id"], raw, self.database_path)
        except (DatabaseError, ValueError) as error:
            self.error.setText(f"Не удалось сохранить значение: {error}")
            return
        self.accept()


class CustomAttributeDefinitionDialog(QDialog):
    """Создание и изменение общего определения характеристики категории."""

    def __init__(self, component_type: str, database_path=None, definition: dict | None = None, parent=None):
        super().__init__(parent)
        self.component_type = component_type
        self.database_path = database_path
        self.definition = definition
        self.setWindowTitle("Изменить характеристику" if definition else "Новая характеристика")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(definition["name"] if definition else "")
        self.kind = QComboBox()
        for key, label in CustomAttributeDialog.TYPE_LABELS.items():
            self.kind.addItem(label, key)
        if definition:
            self.kind.setCurrentIndex(max(0, self.kind.findData(definition["value_type"])))
        self.unit = QLineEdit(definition["unit"] or "" if definition else "")
        self.options = QTextEdit()
        self.options.setPlaceholderText("Один вариант на строку")
        self.options.setMaximumHeight(140)
        form.addRow("Категория:", QLabel(COMPONENT_TYPE_LABELS[component_type]))
        form.addRow("Название:", self.name)
        form.addRow("Тип значения:", self.kind)
        form.addRow("Единица измерения:", self.unit)
        form.addRow("Варианты списка:", self.options)
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        self.kind.currentIndexChanged.connect(self._update_options_visibility)
        if definition and definition["value_type"] == "enum":
            self.options.setPlainText("\n".join(get_custom_attribute_definition_options(definition["id"], database_path)))
        self._update_options_visibility()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_options_visibility(self, *_args) -> None:
        visible = self.kind.currentData() == "enum"
        self.options.setVisible(visible)

    def _save(self) -> None:
        name = self.name.text().strip()
        kind = self.kind.currentData()
        options = [line.strip() for line in self.options.toPlainText().splitlines() if line.strip()]
        try:
            if self.definition:
                update_custom_attribute_definition(
                    self.definition["id"], name=name, value_type=kind,
                    unit=self.unit.text(), enum_options=options, database_path=self.database_path,
                )
            else:
                create_custom_attribute_definition(
                    self.component_type, name, kind, unit=self.unit.text(),
                    enum_options=options, database_path=self.database_path,
                )
        except DatabaseError as error:
            self.error.setText(str(error))
            return
        self.accept()


class CustomAttributeManagerDialog(QDialog):
    """Единый экран управления пользовательскими определениями по категориям."""

    def __init__(self, database_path=None, parent=None):
        super().__init__(parent)
        self.database_path = database_path
        self.setWindowTitle("Пользовательские характеристики")
        self.resize(850, 580)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.category = QComboBox()
        self.category.addItem("Все категории", None)
        for kind, label in sorted(COMPONENT_TYPE_LABELS.items(), key=lambda item: item[1]):
            self.category.addItem(label, kind)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию характеристики")
        controls.addWidget(self.category)
        controls.addWidget(self.search, 1)
        layout.addLayout(controls)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Категория", "Название", "Тип", "Единица", "Заполнено у"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda *_args: self.edit_selected())
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        self.add_button = QPushButton("Добавить")
        self.edit_button = QPushButton("Изменить")
        self.delete_button = QPushButton("Удалить")
        self.add_button.clicked.connect(self.add_definition)
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        for button in (self.add_button, self.edit_button, self.delete_button):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.category.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.refresh()

    def refresh(self, *_args) -> None:
        try:
            definitions = list_custom_attribute_definitions(self.category.currentData(), self.database_path)
        except DatabaseError as error:
            _show_message(self, QMessageBox.Icon.Critical, "Ошибка справочника характеристик", str(error))
            return
        query = self.search.text().strip().casefold()
        if query:
            definitions = [item for item in definitions if query in item["name"].casefold()]
        self.definitions = definitions
        self.table.setRowCount(len(definitions))
        labels = CustomAttributeDialog.TYPE_LABELS
        for row, definition in enumerate(definitions):
            values = [COMPONENT_TYPE_LABELS.get(definition["component_type"], definition["component_type"]),
                      definition["name"], labels.get(definition["value_type"], definition["value_type"]),
                      definition["unit"] or "", str(definition["value_count"])]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, definition["id"])
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.add_button.setEnabled(self.category.currentData() is not None)

    def _selected(self) -> dict | None:
        row = self.table.currentRow()
        return self.definitions[row] if 0 <= row < len(self.definitions) else None

    def add_definition(self) -> None:
        kind = self.category.currentData()
        if kind is None:
            return
        if CustomAttributeDefinitionDialog(kind, self.database_path, parent=self).exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def edit_selected(self) -> None:
        definition = self._selected()
        if definition and CustomAttributeDefinitionDialog(
            definition["component_type"], self.database_path, definition=definition, parent=self
        ).exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def delete_selected(self) -> None:
        definition = self._selected()
        if not definition:
            return
        try:
            usage = get_custom_attribute_definition_usage(definition["id"], self.database_path)
        except DatabaseError as error:
            _show_message(self, QMessageBox.Icon.Warning, "Ошибка проверки данных", str(error))
            return
        names = [f"{item['manufacturer']} {item['model_name']}".strip() for item in usage]
        details = "\n".join(names[:8])
        if len(names) > 8:
            details += f"\n… и ещё {len(names) - 8}"
        warning = f"Удалить характеристику «{definition['name']}»?"
        if names:
            warning += f"\n\nБудут удалены сохранённые значения у {len(names)} комплектующих:\n{details}"
        warning += "\n\nДействие нельзя отменить."
        answer = QMessageBox.warning(
            self, "Удалить пользовательскую характеристику?", warning,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_custom_attribute_definition(definition["id"], self.database_path)
        except DatabaseError as error:
            _show_message(self, QMessageBox.Icon.Warning, "Не удалось удалить характеристику", str(error))
            return
        self.refresh()
