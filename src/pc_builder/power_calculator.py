"""Чистая расчётная логика ориентировочной мощности системы."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True)
class PowerCalculatorSettings:
    motherboard_w: float = 50.0
    ram_module_w: float = 5.0
    ssd_w: float = 5.0
    hdd_w: float = 10.0
    case_fan_w: float = 3.0
    reserve_percent: float = 30.0


@dataclass(frozen=True)
class PowerCalculatorInput:
    cpu_present: bool = False
    cpu_tdp: Any = None
    gpu_present: bool = False
    gpu_power_w: Any = None
    motherboard_present: bool = False
    ram_modules: int = 0
    ssd_count: int = 0
    hdd_count: int = 0
    case_fan_count: int = 0
    data_problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class PowerLine:
    category: str
    quantity: int
    watts_per_unit: float | None
    total_watts: float | None


@dataclass(frozen=True)
class PowerCalculatorResult:
    lines: tuple[PowerLine, ...]
    subtotal_w: float
    reserve_percent: float
    recommended_w: int | None
    complete: bool
    missing_data: tuple[str, ...]


def _power_value(value: Any, label: str, field_label: str, missing: list[str]) -> float | None:
    if value is None:
        missing.append(f"{label}: не указана характеристика «{field_label}».")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        missing.append(f"{label}: значение «{field_label}» имеет некорректный формат.")
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        missing.append(f"{label}: «{field_label}» должно быть конечным числом не меньше нуля.")
        return None
    # Ноль разрешён существующей моделью (tdp_w >= 0), поэтому не считается
    # отсутствующим значением автоматически.
    return numeric


def calculate_power(
    data: PowerCalculatorInput,
    settings: PowerCalculatorSettings = PowerCalculatorSettings(),
) -> PowerCalculatorResult:
    """Считает известную нагрузку и рекомендацию с округлением вверх до 50 Вт."""
    for name, value in (
        ("Материнская плата", settings.motherboard_w), ("RAM", settings.ram_module_w),
        ("SSD", settings.ssd_w), ("HDD", settings.hdd_w),
        ("Корпусный вентилятор", settings.case_fan_w), ("Запас", settings.reserve_percent),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Настройка «{name}» должна быть конечным числом не меньше нуля.")
    for name, value in (
        ("RAM", data.ram_modules), ("SSD", data.ssd_count),
        ("HDD", data.hdd_count), ("Корпусные вентиляторы", data.case_fan_count),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"Количество «{name}» должно быть целым числом не меньше нуля.")
    missing = list(data.data_problems)
    lines: list[PowerLine] = []
    known_total = 0.0

    def add(category: str, quantity: int, each: float | None, *, unknown_if_absent: bool = False) -> None:
        nonlocal known_total
        total = each * quantity if each is not None and quantity > 0 else (
            None if unknown_if_absent else 0.0 if quantity == 0 else None
        )
        lines.append(PowerLine(category, quantity, each, total))
        if total is not None:
            known_total += total

    if data.cpu_present:
        cpu_tdp = _power_value(data.cpu_tdp, "Процессор", "TDP (tdp_w)", missing)
        add("CPU", 1, cpu_tdp)
    else:
        add("CPU", 0, None, unknown_if_absent=True)
        missing.append("Процессор не выбран.")

    if data.gpu_present:
        gpu_tdp = _power_value(data.gpu_power_w, "Видеокарта", "энергопотребление (power_w)", missing)
        add("GPU", 1, gpu_tdp)
    else:
        add("GPU", 0, None)

    add("Материнская плата", 1 if data.motherboard_present else 0,
        settings.motherboard_w if data.motherboard_present else None,
        unknown_if_absent=not data.motherboard_present)
    if not data.motherboard_present:
        missing.append("Материнская плата не выбрана.")
    add("RAM", data.ram_modules, settings.ram_module_w)
    if data.ram_modules <= 0:
        missing.append("Не указано количество модулей RAM.")
    add("SSD", data.ssd_count, settings.ssd_w)
    add("HDD", data.hdd_count, settings.hdd_w)
    add("Корпусные вентиляторы", data.case_fan_count, settings.case_fan_w)

    complete = not missing
    recommended = None
    if complete:
        raw = known_total * (1.0 + settings.reserve_percent / 100.0)
        recommended = int(math.ceil(raw / 50.0) * 50)
    return PowerCalculatorResult(
        tuple(lines), known_total, settings.reserve_percent, recommended,
        complete, tuple(dict.fromkeys(missing)),
    )
