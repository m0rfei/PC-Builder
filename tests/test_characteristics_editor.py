"""Проверки редакторов характеристик и пользовательских операций."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QSpinBox

from pc_builder.characteristics_widgets import (
    CustomAttributeDialog,
    CustomAttributesEditor,
    SPEC_FIELDS,
    SpecificationsEditor,
)
from pc_builder.database import (
    DatabaseError,
    create_component_model,
    create_custom_attribute,
    delete_custom_attribute,
    get_custom_attributes,
    get_custom_attribute_options,
    get_component_model,
    initialize_database,
    update_custom_attribute,
)
from pc_builder.specifications import create_component_spec, get_component_spec


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def database_path(tmp_path):
    path = tmp_path / "editor.db"
    initialize_database(path)
    return path


def _model(path, component_type="cpu"):
    return create_component_model(component_type, "Изготовитель", "Модель", database_path=path)


def test_specification_editor_loads_fields_for_all_types_without_creating_rows(database_path, qapp):
    component_types = (
        "motherboard", "cpu", "ram", "gpu", "psu", "ssd", "hdd",
        "cpu_cooler", "case_fan", "case",
    )
    for component_type in component_types:
        model_id = _model(database_path, component_type)
        editor = SpecificationsEditor(model_id, component_type, database_path)
        expected = {field[0] for field in SPEC_FIELDS[component_type]}
        assert set(editor.controls) == expected
        assert get_component_spec(model_id, database_path) is None
        editor.deleteLater()


def test_dropdowns_start_with_requested_ssd_ram_and_hdd_values(database_path, qapp):
    from pc_builder.database import create_component_model

    ssd = create_component_model("ssd", "Samsung", "SSD", database_path=database_path)
    ssd_editor = SpecificationsEditor(ssd, "ssd", database_path)
    assert {ssd_editor.controls["form_factor"].itemData(i)
            for i in range(1, ssd_editor.controls["form_factor"].count())} == {"2_5_in", "m2"}
    assert {ssd_editor.controls["interface_type"].itemData(i)
            for i in range(1, ssd_editor.controls["interface_type"].count())} == {"sata", "pcie"}

    ram = create_component_model("ram", "Kingston", "RAM", database_path=database_path)
    ram_editor = SpecificationsEditor(ram, "ram", database_path)
    assert {ram_editor.controls["ram_type"].itemData(i)
            for i in range(1, ram_editor.controls["ram_type"].count())} == {"ddr", "ddr2", "ddr3", "ddr4", "ddr5"}
    assert {ram_editor.controls["form_factor"].itemData(i)
            for i in range(1, ram_editor.controls["form_factor"].count())} == {"dimm", "so_dimm"}

    hdd = create_component_model("hdd", "Seagate", "HDD", database_path=database_path)
    hdd_editor = SpecificationsEditor(hdd, "hdd", database_path)
    assert [hdd_editor.controls["interface_type"].itemData(i)
            for i in range(1, hdd_editor.controls["interface_type"].count())] == ["sata"]


def test_specification_editor_saves_and_reloads_values_and_nulls(database_path, qapp):
    model_id = _model(database_path, "gpu")
    editor = SpecificationsEditor(model_id, "gpu", database_path)
    editor.controls["slot_width"].setValue(2.5)
    editor.controls["power_w"].setValue(250)
    connectors = editor.controls["power_connectors"]
    connectors.set_values({"pcie_8pin": 2})

    editor.save()

    spec = get_component_spec(model_id, database_path)
    assert spec["slot_width"] == 2.5
    assert spec["power_w"] == 250
    assert spec["vram_gb"] is None
    assert spec["power_connectors"] == {"pcie_8pin": 2}
    reopened = SpecificationsEditor(model_id, "gpu", database_path)
    assert reopened.controls["slot_width"].value() == 2.5
    assert reopened.controls["power_connectors"].values() == {"pcie_8pin": 2}


def test_memory_units_are_explicit_and_stored_as_gb(database_path, qapp):
    ram_id = _model(database_path, "ram")
    ram_editor = SpecificationsEditor(ram_id, "ram", database_path)
    memory = ram_editor.controls["capacity_gb"]
    assert memory.unit.currentData() == "gb"
    memory.unit.setCurrentIndex(memory.unit.findData("mb"))
    memory.number.setValue(128)
    ram_editor.save()
    assert get_component_spec(ram_id, database_path)["capacity_gb"] == 0.125
    reopened = SpecificationsEditor(ram_id, "ram", database_path)
    assert reopened.controls["capacity_gb"].unit.currentData() == "mb"
    assert reopened.controls["capacity_gb"].number.value() == 128

    gpu_id = _model(database_path, "gpu")
    gpu_editor = SpecificationsEditor(gpu_id, "gpu", database_path)
    vram = gpu_editor.controls["vram_gb"]
    vram.unit.setCurrentIndex(vram.unit.findData("mb"))
    vram.number.setValue(512)
    gpu_editor.save()
    assert get_component_spec(gpu_id, database_path)["vram_gb"] == 0.5


def test_specification_controls_are_typed_and_gpu_chip_brand_is_independent(database_path, qapp):
    from pc_builder.catalog_widgets import ModelFormDialog

    gpu_id = create_component_model("gpu", "ASUS", "Board", database_path=database_path)
    editor = SpecificationsEditor(gpu_id, "gpu", database_path)
    assert isinstance(editor.controls["power_w"], QDoubleSpinBox)
    assert editor.controls["power_w"].suffix() == " Вт"
    chip_brand = editor.controls["chip_manufacturer"]
    assert isinstance(chip_brand, QComboBox) and chip_brand.isEditable()
    chip_brand.setCurrentIndex(chip_brand.findData("NVIDIA"))
    editor.save()
    assert get_component_spec(gpu_id, database_path)["chip_manufacturer"] == "NVIDIA"
    assert get_component_model(gpu_id, database_path)["manufacturer"] == "ASUS"

    cpu_editor = SpecificationsEditor(_model(database_path, "cpu"), "cpu", database_path)
    assert isinstance(cpu_editor.controls["cores"], QSpinBox)
    assert isinstance(cpu_editor.controls["socket"], QComboBox)
    assert cpu_editor.controls["socket"].isEditable()

    psu_id = _model(database_path, "psu")
    psu_editor = SpecificationsEditor(psu_id, "psu", database_path)
    assert psu_editor.controls["modularity"].isEditable()
    psu_editor.controls["modularity"].setCurrentIndex(psu_editor.controls["modularity"].findData("semi_modular"))
    psu_editor.save()
    assert get_component_spec(psu_id, database_path)["modularity"] == "semi_modular"

    cpu_dialog = ModelFormDialog(database_path)
    assert isinstance(cpu_dialog.manufacturer_input, QComboBox)
    cpu_dialog.type_combo.setCurrentIndex(cpu_dialog.type_combo.findData("cpu"))
    assert {cpu_dialog.manufacturer_input.itemText(i) for i in range(cpu_dialog.manufacturer_input.count())} >= {"Intel", "AMD"}

    from pc_builder.database import list_manufacturer_options
    hdd_dialog = ModelFormDialog(database_path)
    hdd_dialog.type_combo.setCurrentIndex(hdd_dialog.type_combo.findData("hdd"))
    hdd_dialog.manufacturer_input.setEditText("Новый HDD бренд")
    hdd_dialog.add_manufacturer_button.click()
    assert "Новый HDD бренд" in list_manufacturer_options("hdd", database_path)
    reopened = ModelFormDialog(database_path)
    reopened.type_combo.setCurrentIndex(reopened.type_combo.findData("hdd"))
    assert "Новый HDD бренд" in {
        reopened.manufacturer_input.itemText(i) for i in range(reopened.manufacturer_input.count())
    }
    hdd_dialog.remove_manufacturer_button.click()
    assert "Новый HDD бренд" not in list_manufacturer_options("hdd", database_path)


def test_legacy_custom_enum_keeps_value_without_fabricated_options(database_path, qapp):
    model_id = _model(database_path)
    attribute_id = create_custom_attribute(model_id, "Старый список", "enum", "Старое значение", database_path=database_path)
    attribute = get_custom_attributes(model_id, database_path)[0]
    dialog = CustomAttributeDialog(model_id, "cpu", database_path, attribute=attribute)
    assert dialog.enum_input.currentText() == "Старое значение"
    assert dialog.enum_options_list.count() == 0
    assert "варианты ранее не сохранялись" in dialog.enum_legacy_warning.text()


def test_cancel_restores_saved_values_and_does_not_create_empty_spec(database_path, qapp):
    model_id = _model(database_path)
    editor = SpecificationsEditor(model_id, "cpu", database_path)
    editor.controls["cores"].setValue(8)
    editor.cancel_changes()
    assert editor.controls["cores"].value() == editor.controls["cores"].minimum()
    assert get_component_spec(model_id, database_path) is None


def test_saving_one_model_does_not_change_another_models_specifications(database_path, qapp):
    first = _model(database_path)
    second = create_component_model("cpu", "Изготовитель", "Вторая модель", database_path=database_path)
    first_editor = SpecificationsEditor(first, "cpu", database_path)
    first_editor.controls["cores"].setValue(8)
    first_editor.save()
    second_editor = SpecificationsEditor(second, "cpu", database_path)
    second_editor.controls["cores"].setValue(4)
    second_editor.save()

    first_editor.controls["cores"].setValue(12)
    first_editor.save()

    assert get_component_spec(first, database_path)["cores"] == 12
    assert get_component_spec(second, database_path)["cores"] == 4


def test_invalid_spec_value_keeps_form_open_and_preserves_input(database_path, qapp):
    model_id = _model(database_path)
    editor = SpecificationsEditor(model_id, "cpu", database_path)
    assert editor.controls["tdp_w"].minimum() == -0.00001
    with pytest.raises(DatabaseError):
        create_component_spec(model_id, tdp_w=-15, database_path=database_path)
    assert get_component_spec(model_id, database_path) is None


def test_custom_attribute_dialog_supports_existing_value_types(database_path, qapp):
    model_id = _model(database_path)
    values = {"text": "важно", "number": "24.5", "boolean": None, "enum": "PCIe 5.0"}
    for value_type, value in values.items():
        dialog = CustomAttributeDialog(model_id, "cpu", database_path)
        dialog.name_input.setText(f"Поле {value_type}")
        dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(value_type))
        if value_type == "text":
            dialog.text_input.setText(value)
        elif value_type == "number":
            dialog.number_input.setValue(float(value))
        elif value_type == "boolean":
            dialog.boolean_input.setCurrentIndex(0)
        else:
            dialog.enum_input.setEditText(value)
            for option in ("PCIe 4.0", "PCIe 5.0", "PCIe 6.0"):
                dialog.enum_options_input.setText(option)
                dialog._add_enum_option()
            dialog.enum_input.setCurrentIndex(dialog.enum_input.findData(value))
        dialog._save()
        assert dialog.attribute_id is not None

    rows = {row["value_type"]: row for row in get_custom_attributes(model_id, database_path)}
    assert rows["text"]["value_text"] == "важно"
    assert rows["number"]["value_number"] == 24.5
    assert rows["boolean"]["value_boolean"] == 1
    assert rows["enum"]["value_enum"] == "PCIe 5.0"
    enum_attribute = next(row for row in get_custom_attributes(model_id, database_path) if row["value_type"] == "enum")
    reopened_enum = CustomAttributeDialog(model_id, "cpu", database_path, attribute=enum_attribute)
    assert reopened_enum.enum_input.currentText() == "PCIe 5.0"
    assert reopened_enum.enum_options_list.count() == 3
    assert [reopened_enum.enum_options_list.item(i).text() for i in range(3)] == ["PCIe 4.0", "PCIe 5.0", "PCIe 6.0"]
    reopened_enum.enum_options_list.setCurrentRow(2)
    reopened_enum._remove_enum_option()
    reopened_enum.enum_input.setCurrentIndex(reopened_enum.enum_input.findData("PCIe 5.0"))
    reopened_enum._save()
    assert get_custom_attribute_options(enum_attribute["id"], database_path) == ["PCIe 4.0", "PCIe 5.0"]


def test_custom_attribute_update_delete_and_model_isolation(database_path, qapp):
    first = _model(database_path, "cpu")
    second = create_component_model("gpu", "Изготовитель", "Другая модель", database_path=database_path)
    attribute_id = create_custom_attribute(first, "Заметка", "text", "старое", database_path=database_path)
    create_custom_attribute(second, "Заметка", "text", "не менять", database_path=database_path)

    current = get_custom_attributes(first, database_path)[0]
    dialog = CustomAttributeDialog(first, "cpu", database_path, attribute=current)
    dialog.name_input.setText("Измерение")
    dialog.text_input.setText("32.75")
    dialog.unit_input.setText("ГБ")
    dialog._save()

    updated = get_custom_attributes(first, database_path)[0]
    assert updated["id"] == attribute_id
    assert updated["name"] == "Измерение"
    assert updated["value_number"] is None
    assert updated["value_text"] == "32.75"
    assert updated["unit"] == "ГБ"
    assert get_custom_attributes(second, database_path)[0]["value_text"] == "не менять"

    editor = CustomAttributesEditor(first, "cpu", database_path)
    assert editor.table.rowCount() == 1
    delete_custom_attribute(attribute_id, database_path)
    editor.refresh()
    # Удаление значения не удаляет общее определение поля категории.
    assert editor.table.rowCount() == 1
    assert editor.table.item(0, 2).text() == "—"


def test_custom_attribute_update_uses_typed_storage_and_rejects_invalid_values(database_path):
    model_id = _model(database_path)
    attribute_id = create_custom_attribute(model_id, "Число", "number", 1.5, database_path=database_path)
    with pytest.raises(DatabaseError, match="не соответствует типу"):
        update_custom_attribute(attribute_id, "Число", "number", "ошибка", database_path=database_path)
    assert get_custom_attributes(model_id, database_path)[0]["value_number"] == 1.5
