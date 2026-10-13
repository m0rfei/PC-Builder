"""Проверки расчётной логики калькулятора мощности."""

import pytest
from PySide6.QtWidgets import QApplication

from pc_builder.power_calculator import (
    PowerCalculatorInput,
    PowerCalculatorSettings,
    calculate_power,
)
from pc_builder.database import (
    add_build_slot,
    create_build,
    create_component,
    initialize_database,
    list_build_slots,
    set_build_slot_component,
    update_build_slot_quantity,
)
from pc_builder.power_calculator_widgets import PowerCalculatorDialog
from pc_builder.specifications import create_component_spec


def test_power_formula_reserve_rounds_up_to_next_50_watts():
    result = calculate_power(
        PowerCalculatorInput(
            cpu_present=True,
            cpu_tdp=200,
            gpu_present=True,
            gpu_power_w=100,
            motherboard_present=True,
            ram_modules=2,
            ssd_count=1,
            hdd_count=1,
            case_fan_count=2,
        )
    )
    assert result.complete
    assert result.subtotal_w == 381
    assert result.recommended_w == 500


@pytest.mark.parametrize("value", [None, "125", -1, float("inf"), float("nan"), True])
def test_invalid_cpu_tdp_returns_partial_calculation(value):
    result = calculate_power(
        PowerCalculatorInput(
            cpu_present=True,
            cpu_tdp=value,
            motherboard_present=True,
            ram_modules=1,
        )
    )
    assert not result.complete
    assert result.recommended_w is None
    assert result.lines[0].total_watts is None
    assert result.missing_data


def test_missing_gpu_is_optional_but_cpu_and_motherboard_are_required():
    data = PowerCalculatorInput(
        cpu_present=True, cpu_tdp=65, motherboard_present=True, ram_modules=1,
    )
    result = calculate_power(data)
    assert result.complete
    assert result.lines[1].total_watts == 0
    assert result.recommended_w is not None

    incomplete = calculate_power(PowerCalculatorInput(ram_modules=1))
    assert not incomplete.complete
    assert incomplete.recommended_w is None
    assert any("Процессор" in message for message in incomplete.missing_data)
    assert any("Материнская плата" in message for message in incomplete.missing_data)


def test_invalid_counts_and_settings_are_rejected():
    with pytest.raises(ValueError, match="целым числом"):
        calculate_power(PowerCalculatorInput(ram_modules=-1))
    with pytest.raises(ValueError, match="не меньше нуля"):
        calculate_power(
            PowerCalculatorInput(),
            PowerCalculatorSettings(reserve_percent=-1),
        )


def test_build_calculator_reads_slot_quantities_without_mutating_build(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "power-build.db"
    initialize_database(path)
    cpu = create_component("cpu", "Audit", "Audit CPU", database_path=path)
    board = create_component("motherboard", "Audit", "Audit Board", database_path=path)
    ram = create_component("ram", "Audit", "Audit RAM", database_path=path)
    ssd = create_component("ssd", "Audit", "Audit SSD", database_path=path)
    hdd = create_component("hdd", "Audit", "Audit HDD", database_path=path)
    fan = create_component("case_fan", "Audit", "Audit Fan", database_path=path)
    create_component_spec(cpu, database_path=path, tdp_w=65)
    build_id = create_build("Audit build", database_path=path)
    add_build_slot(build_id, "case_fan", path)
    slots = list_build_slots(build_id, path)
    for category, component_id in (
        ("cpu", cpu), ("motherboard", board), ("ram", ram),
        ("storage", ssd), ("case_fan", fan),
    ):
        slot = next(row for row in slots if row["category"] == category)
        set_build_slot_component(slot["slot_id"], component_id, path)
    hdd_slot_id = add_build_slot(build_id, "storage", path)
    set_build_slot_component(hdd_slot_id, hdd, path)
    update_build_slot_quantity(next(row for row in slots if row["category"] == "ram")["slot_id"], 2, path)
    update_build_slot_quantity(next(row for row in slots if row["category"] == "storage")["slot_id"], 2, path)
    update_build_slot_quantity(next(row for row in slots if row["category"] == "case_fan")["slot_id"], 3, path)
    before = list_build_slots(build_id, path)

    dialog = PowerCalculatorDialog(path, build_id=build_id)
    data = dialog._build_input()
    result = calculate_power(data, dialog._settings_value())

    assert data.cpu_tdp == 65
    assert not data.gpu_present
    assert (data.ram_modules, data.ssd_count, data.hdd_count, data.case_fan_count) == (2, 2, 1, 3)
    assert result.complete
    assert result.subtotal_w == 154
    assert result.recommended_w == 250
    assert list_build_slots(build_id, path) == before
    dialog.close()
    app.processEvents()
