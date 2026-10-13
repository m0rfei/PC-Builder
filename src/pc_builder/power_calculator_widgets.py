"""Один интерфейс калькулятора для самостоятельного расчёта и сборки."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QDialog, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox,
    QLabel, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from .database import DatabaseError, get_component, list_build_slots
from .power_calculator import (
    PowerCalculatorInput, PowerCalculatorSettings, calculate_power,
)
from .specifications import get_component_spec


DEFAULTS = {
    "motherboard_w": 50.0,
    "ram_module_w": 5.0,
    "ssd_w": 5.0,
    "hdd_w": 10.0,
    "case_fan_w": 3.0,
    "reserve_percent": 30.0,
}
SETTING_LABELS = {
    "motherboard_w": "Материнская плата, Вт",
    "ram_module_w": "Один модуль RAM, Вт",
    "ssd_w": "Одно устройство SSD, Вт",
    "hdd_w": "Одно устройство HDD, Вт",
    "case_fan_w": "Один корпусный вентилятор, Вт",
    "reserve_percent": "Запас мощности, %",
}
STANDALONE_COMPONENTS = (
    ("cpu", "Процессор"),
    ("motherboard", "Материнская плата"),
    ("gpu", "Видеокарта"),
)
COUNT_FIELDS = (
    ("ram_modules", "Модули RAM"),
    ("ssd_count", "Устройства SSD"),
    ("hdd_count", "Устройства HDD"),
    ("case_fan_count", "Корпусные вентиляторы"),
)


class PowerCalculatorDialog(QDialog):
    """Ориентировочная оценка нагрузки без сохранения данных в сборке."""

    def __init__(
        self,
        database_path: Path | str | None = None,
        *,
        build_id: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.database_path = database_path
        self.build_id = build_id
        self._settings = QSettings("PC-Builder", "PC-Builder")
        self._loading_settings = True
        self._component_ids: dict[str, int | None] = {key: None for key, _ in STANDALONE_COMPONENTS}
        self._component_labels: dict[str, QLabel] = {}
        self._count_inputs: dict[str, QSpinBox] = {}
        self._setting_inputs: dict[str, QDoubleSpinBox] = {}
        self.setWindowTitle("Калькулятор мощности блока питания")
        self.resize(760, 680)
        self.setMinimumSize(620, 520)
        root = QVBoxLayout(self)

        if build_id is None:
            self._build_standalone_controls(root)
        else:
            source = QLabel("Расчёт по текущему составу сборки. Состав сборки не изменяется.")
            source.setWordWrap(True)
            root.addWidget(source)

        settings_box = QGroupBox("Настройки ориентировочного расчёта")
        settings_form = QFormLayout(settings_box)
        for key, label in SETTING_LABELS.items():
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1_000_000.0)
            spin.setDecimals(1 if key != "reserve_percent" else 0)
            spin.setSingleStep(1.0 if key != "reserve_percent" else 5.0)
            spin.setKeyboardTracking(False)
            spin.setSuffix(" %" if key == "reserve_percent" else " Вт")
            spin.setValue(self._read_setting(key))
            spin.valueChanged.connect(self._settings_changed)
            self._setting_inputs[key] = spin
            settings_form.addRow(label + ":", spin)
        root.addWidget(settings_box)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Категория", "Количество", "На устройство", "Сумма"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-weight: 600;")
        root.addWidget(self.summary_label)
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        root.addWidget(self.warning_label)

        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)
        root.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)
        self._loading_settings = False
        self._recalculate()

    def _read_setting(self, key: str) -> float:
        default = DEFAULTS[key]
        try:
            value = float(self._settings.value(f"power_calculator/{key}", default))
        except (TypeError, ValueError):
            return default
        return value if math.isfinite(value) and value >= 0 else default

    def _settings_changed(self, *_args) -> None:
        if self._loading_settings:
            return
        for key, spin in self._setting_inputs.items():
            self._settings.setValue(f"power_calculator/{key}", spin.value())
        self._settings.sync()
        self._recalculate()

    def _build_standalone_controls(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox("Конфигурация для расчёта")
        layout = QGridLayout(group)
        for row, (component_type, label_text) in enumerate(STANDALONE_COMPONENTS):
            label = QLabel("Не выбрано")
            label.setWordWrap(True)
            self._component_labels[component_type] = label
            choose = QPushButton("Выбрать" if component_type != "gpu" else "Выбрать (необязательно)")
            choose.clicked.connect(lambda _checked=False, kind=component_type: self._choose_component(kind))
            layout.addWidget(QLabel(label_text + ":"), row, 0)
            layout.addWidget(label, row, 1)
            layout.addWidget(choose, row, 2)
        for offset, (key, label_text) in enumerate(COUNT_FIELDS, len(STANDALONE_COMPONENTS)):
            spin = QSpinBox()
            spin.setRange(0, 2_000_000_000)
            spin.setKeyboardTracking(False)
            spin.setValue(1 if key == "ram_modules" else 0)
            spin.valueChanged.connect(self._recalculate)
            self._count_inputs[key] = spin
            layout.addWidget(QLabel(label_text + ":"), offset, 0)
            layout.addWidget(spin, offset, 1)
        parent_layout.addWidget(group)

    def _choose_component(self, component_type: str) -> None:
        # Локальный импорт избегает циклической зависимости с BuildsPage.
        from .builds_widgets import ComponentPickerDialog

        dialog = ComponentPickerDialog(self.database_path, self, {component_type})
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.component_id is None:
            return
        try:
            component = get_component(dialog.component_id, self.database_path)
            if component is None:
                raise DatabaseError("Выбранное комплектующее больше не найдено.")
        except DatabaseError as error:
            QMessageBox.warning(self, "Не удалось выбрать комплектующее", str(error))
            return
        self._component_ids[component_type] = int(component["id"])
        self._component_labels[component_type].setText(
            " ".join(value for value in (component.get("manufacturer"), component.get("model_name")) if value)
        )
        self._recalculate()

    def _settings_value(self) -> PowerCalculatorSettings:
        return PowerCalculatorSettings(**{
            key: spin.value() for key, spin in self._setting_inputs.items()
        })

    def _component_tdp(self, component_id: int | None, field: str, label: str, problems: list[str]):
        if component_id is None:
            return False, None
        try:
            spec = get_component_spec(component_id, self.database_path) or {}
        except DatabaseError as error:
            problems.append(f"{label}: не удалось прочитать характеристики ({error}).")
            return True, None
        return True, spec.get(field)

    def _standalone_input(self) -> PowerCalculatorInput:
        problems: list[str] = []
        cpu_present, cpu_tdp = self._component_tdp(self._component_ids["cpu"], "tdp_w", "Процессор", problems)
        gpu_present, gpu_tdp = self._component_tdp(self._component_ids["gpu"], "power_w", "Видеокарта", problems)
        return PowerCalculatorInput(
            cpu_present=cpu_present,
            cpu_tdp=cpu_tdp,
            gpu_present=gpu_present,
            gpu_power_w=gpu_tdp,
            motherboard_present=self._component_ids["motherboard"] is not None,
            ram_modules=self._count_inputs["ram_modules"].value(),
            ssd_count=self._count_inputs["ssd_count"].value(),
            hdd_count=self._count_inputs["hdd_count"].value(),
            case_fan_count=self._count_inputs["case_fan_count"].value(),
            data_problems=tuple(problems),
        )

    def _build_input(self) -> PowerCalculatorInput:
        problems: list[str] = []
        try:
            slots = list_build_slots(self.build_id, self.database_path)
        except DatabaseError as error:
            return PowerCalculatorInput(data_problems=(f"Не удалось прочитать состав сборки: {error}.",))
        cpu = next((slot for slot in slots if slot["category"] == "cpu" and slot["component_id"] is not None), None)
        gpu = next((slot for slot in slots if slot["category"] == "gpu" and slot["component_id"] is not None), None)
        motherboard_present = any(
            slot["category"] == "motherboard" and slot["component_id"] is not None for slot in slots
        )
        cpu_present, cpu_tdp = self._component_tdp(cpu["component_id"] if cpu else None, "tdp_w", "Процессор", problems)
        gpu_present, gpu_tdp = self._component_tdp(gpu["component_id"] if gpu else None, "power_w", "Видеокарта", problems)
        ram_modules = sum(int(slot["quantity"]) for slot in slots
                          if slot["category"] == "ram" and slot["component_id"] is not None)
        ssd_count = sum(int(slot["quantity"]) for slot in slots
                        if slot["category"] == "storage" and slot["component_id"] is not None
                        and slot["component_type"] == "ssd")
        hdd_count = sum(int(slot["quantity"]) for slot in slots
                        if slot["category"] == "storage" and slot["component_id"] is not None
                        and slot["component_type"] == "hdd")
        fan_count = sum(int(slot["quantity"]) for slot in slots
                        if slot["category"] == "case_fan" and slot["component_id"] is not None)
        return PowerCalculatorInput(
            cpu_present=cpu_present, cpu_tdp=cpu_tdp,
            gpu_present=gpu_present, gpu_power_w=gpu_tdp,
            motherboard_present=motherboard_present,
            ram_modules=ram_modules, ssd_count=ssd_count,
            hdd_count=hdd_count, case_fan_count=fan_count,
            data_problems=tuple(problems),
        )

    @staticmethod
    def _watts(value: float | int | None) -> str:
        return "Неизвестно" if value is None else f"{value:g} Вт"

    def _recalculate(self, *_args) -> None:
        data = self._build_input() if self.build_id is not None else self._standalone_input()
        try:
            result = calculate_power(data, self._settings_value())
        except ValueError as error:
            self.warning_label.setText(str(error))
            return
        self.table.setRowCount(len(result.lines))
        for row, line in enumerate(result.lines):
            values = [
                line.category,
                str(line.quantity),
                self._watts(line.watts_per_unit) if line.quantity else "—",
                self._watts(line.total_watts),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        title = "Суммарное расчётное потребление" if result.complete else "Частичный расчёт известных компонентов"
        self.summary_label.setText(f"{title}: {result.subtotal_w:g} Вт\nЗапас: {result.reserve_percent:g}%")
        if result.recommended_w is None:
            self.summary_label.setText(self.summary_label.text() + "\nРекомендуемая мощность БП: недоступна — расчёт неполный.")
        else:
            self.summary_label.setText(
                self.summary_label.text() + f"\nОриентировочная рекомендация по БП: {result.recommended_w} Вт"
            )
        self.warning_label.setText(
            "Расчёт неполный:\n• " + "\n• ".join(result.missing_data)
            if result.missing_data else "Ориентировочная оценка; фактическое потребление может отличаться."
        )
