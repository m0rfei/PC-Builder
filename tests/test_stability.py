"""Интеграционные проверки жизненного цикла и единиц объёма памяти."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sqlite3

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QTabWidget

from pc_builder.catalog import duplicate_component, list_archived_components, list_owned_models
from pc_builder.catalog_widgets import ModelCardDialog, ModelFormDialog
from pc_builder.characteristics_widgets import SPEC_FIELDS, SpecificationsEditor
from pc_builder.database import (
    DatabaseError,
    archive_component,
    create_custom_attribute,
    delete_component,
    get_component,
    get_custom_attributes,
    get_custom_attribute_options,
    initialize_database,
    restore_component,
    update_component,
)
from pc_builder.specifications import create_component_spec, get_component_spec


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def database_path(tmp_path):
    path = tmp_path / "stability.db"
    initialize_database(path)
    return path


def _make_component(database_path, qapp, *, name="Тестовый процессор"):
    dialog = ModelFormDialog(database_path)
    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData("cpu"))
    dialog.manufacturer_input.setEditText("AMD")
    dialog.model_name_input.setText(name)
    dialog._save()
    assert dialog.model_id is not None
    return dialog.model_id


def test_full_component_lifecycle_and_card_reopen(database_path, qapp):
    component_id = _make_component(database_path, qapp)
    assert "quantity" not in get_component(component_id, database_path)

    card = ModelCardDialog(component_id, database_path)
    assert not card.findChildren(QTabWidget)
    assert card.scroll.widget() is not None
    spec_editor = SpecificationsEditor(component_id, "cpu", database_path)
    spec_editor.controls["socket"].setEditText("AM5")
    spec_editor.controls["cores"].setValue(6)
    spec_editor.controls["threads"].setValue(12)
    spec_editor.controls["base_clock_mhz"].setValue(3500.5)
    spec_editor.save()
    assert "сохранены" in spec_editor.status.text()

    attribute_id = create_custom_attribute(
        component_id, "Поколение", "enum", "Zen 3",
        enum_options=["Zen 2", "Zen 3", "Zen 4"], database_path=database_path,
    )
    card.close()

    reopened = ModelCardDialog(component_id, database_path)
    assert reopened.name_input.text() == "Тестовый процессор"
    assert reopened.spec_editor.controls["socket"].currentData() == "AM5"
    assert reopened.spec_editor.controls["cores"].value() == 6
    assert reopened.custom_editor.table.rowCount() == 1
    assert reopened.custom_editor.table.item(0, 0).text() == "Поколение"
    assert reopened.custom_editor.table.item(0, 2).text() == "Zen 3"
    assert get_component_spec(component_id, database_path)["socket"] == "AM5"
    assert get_component_spec(component_id, database_path)["base_clock_mhz"] == 3500.5
    attrs = get_custom_attributes(component_id, database_path)
    assert attrs[0]["value_enum"] == "Zen 3"
    assert get_custom_attribute_options(attribute_id, database_path) == ["Zen 2", "Zen 3", "Zen 4"]

    update_component(component_id, notes="Физическая единица №1", database_path=database_path)
    assert get_component(component_id, database_path)["notes"] == "Физическая единица №1"
    duplicate_id = duplicate_component(component_id, database_path)
    duplicate = get_component(duplicate_id, database_path)
    assert "quantity" not in duplicate
    assert duplicate["status"] == "owned"
    assert duplicate["archived_at"] is None
    assert get_component_spec(duplicate_id, database_path)["cores"] == 6
    copied_attribute = get_custom_attributes(duplicate_id, database_path)[0]
    assert copied_attribute["value_enum"] == "Zen 3"
    assert get_custom_attribute_options(copied_attribute["id"], database_path) == ["Zen 2", "Zen 3", "Zen 4"]

    archive_component(component_id, database_path)
    assert component_id not in {row["id"] for row in list_owned_models(database_path=database_path)}
    assert component_id in {row["id"] for row in list_archived_components(database_path)}
    restore_component(component_id, database_path)
    assert component_id in {row["id"] for row in list_owned_models(database_path=database_path)}

    # Как при подтверждённом удалении: удалить тестовую исходную запись через штатный API.
    delete_component(component_id, database_path)
    assert get_component(component_id, database_path) is None
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        for table in (
            "cpu_specs", "custom_attributes", "custom_attribute_options",
        ):
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            key = "model_id" if "model_id" in columns else None
            if key:
                assert connection.execute(f"SELECT COUNT(*) FROM {table} WHERE model_id=?", (component_id,)).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM custom_attribute_options WHERE attribute_id=?", (attribute_id,)
        ).fetchone()[0] == 0


@pytest.mark.parametrize(
    ("component_type", "field", "mb_value", "expected_gb"),
    [
        ("ram", "capacity_gb", 128, 0.125),
        ("ram", "capacity_gb", 256, 0.25),
        ("ram", "capacity_gb", 512, 0.5),
        ("ram", "capacity_gb", None, None),
        ("gpu", "vram_gb", 512, 0.5),
        ("gpu", "vram_gb", None, None),
    ],
)
def test_memory_editor_exact_mb_gb_round_trip(database_path, qapp, component_type, field, mb_value, expected_gb):
    from pc_builder.database import create_component

    component_id = create_component(component_type, "Проверка", "Память", database_path=database_path)
    editor = SpecificationsEditor(component_id, component_type, database_path)
    control = editor.controls[field]
    if mb_value is None:
        assert control.value_gb() is None
    elif mb_value == 512:
        control.unit.setCurrentIndex(control.unit.findData("mb"))
        control.number.setValue(mb_value)
        assert control.value_gb() == expected_gb
    else:
        control.set_gb(expected_gb)
        assert control.unit.currentData() == "mb"
        assert control.number.value() == mb_value
    editor.save()
    saved = get_component_spec(component_id, database_path)[field]
    assert saved == expected_gb

    reopened = SpecificationsEditor(component_id, component_type, database_path)
    reopened.save()
    assert get_component_spec(component_id, database_path)[field] == expected_gb


@pytest.mark.parametrize("gb_value", [1, 8, 12, 0.333333])
def test_memory_editor_gb_values_and_fractional_precision_are_stable(database_path, qapp, gb_value):
    from pc_builder.database import create_component

    component_id = create_component("gpu", "Проверка", "VRAM", database_path=database_path)
    editor = SpecificationsEditor(component_id, "gpu", database_path)
    memory = editor.controls["vram_gb"]
    memory.set_gb(gb_value)
    editor.save()
    assert get_component_spec(component_id, database_path)["vram_gb"] == gb_value
    reopened = SpecificationsEditor(component_id, "gpu", database_path)
    reopened.save()
    assert get_component_spec(component_id, database_path)["vram_gb"] == gb_value


def test_storage_capacity_and_max_ram_stay_in_gb_and_optional_values_stay_null(database_path, qapp):
    from pc_builder.database import create_component
    from pc_builder.specifications import create_component_spec

    ssd_id = create_component("ssd", "Проверка", "SSD", database_path=database_path)
    ssd = SpecificationsEditor(ssd_id, "ssd", database_path)
    ssd.controls["capacity_gb"].setValue(1024)
    ssd.save()
    assert get_component_spec(ssd_id, database_path)["capacity_gb"] == 1024

    board_id = create_component("motherboard", "Проверка", "Плата", database_path=database_path)
    create_component_spec(board_id, max_ram_gb=128, database_path=database_path)
    reopened = SpecificationsEditor(board_id, "motherboard", database_path)
    assert reopened.controls["max_ram_gb"].value() == 128
    reopened.save()
    assert get_component_spec(board_id, database_path)["max_ram_gb"] == 128
    assert get_component_spec(board_id, database_path)["socket"] is None


def test_all_component_types_can_open_their_existing_specification_fields(database_path, qapp):
    from pc_builder.database import create_component

    for component_type, fields in SPEC_FIELDS.items():
        component_id = create_component(component_type, "Проверка", component_type, database_path=database_path)
        card = ModelCardDialog(component_id, database_path)
        assert not card.findChildren(QTabWidget)
        assert card.scroll.widget() is not None
        assert card.spec_editor.component_type == component_type
        assert set(card.spec_editor.controls) == {item[0] for item in fields}
        card.close()


def test_gpu_card_shows_filled_groups_and_hides_empty_groups(database_path, qapp):
    from pc_builder.database import create_component

    component_id = create_component(
        "gpu", "ASUS", "RTX 4070", part_number="RTX-4070-01",
        description="Описание видеокарты", notes="Проверено",
        database_path=database_path,
    )
    create_component_spec(
        component_id,
        chip_manufacturer="NVIDIA", vram_gb=12, vram_type="gddr6x",
        length_mm=300, thickness_mm=50, slot_width=2.5, power_w=200,
        recommended_psu_w=650, power_connectors={"pcie_8pin": 2},
        database_path=database_path,
    )
    card = ModelCardDialog(component_id, database_path)
    controls = card.spec_editor.controls
    assert controls["chip_manufacturer"].currentData() == "NVIDIA"
    assert controls["vram_gb"].value_gb() == 12
    assert controls["length_mm"].value() == 300
    assert controls["slot_width"].value() == 2.5
    assert controls["power_connectors"].values() == {"pcie_8pin": 2}
    assert card.component_type == "gpu"
    assert card.notes_input.toPlainText() == "Проверено"


def test_empty_specification_groups_and_empty_custom_values_are_hidden(database_path, qapp):
    from pc_builder.database import create_component

    component_id = create_component("cpu", "AMD", "Ryzen", database_path=database_path)
    create_custom_attribute(component_id, "Пока не заполнено", "text", "", database_path=database_path)
    card = ModelCardDialog(component_id, database_path)
    assert card.spec_editor.component_type == "cpu"
    assert card.spec_editor.controls["cores"].value() == card.spec_editor.controls["cores"].minimum()
    assert card.custom_editor.table.rowCount() == 1
    assert card.custom_editor.table.item(0, 0).text() == "Пока не заполнено"


def test_quantity_api_is_removed_and_duplicate_enum_options_are_rejected_without_data_loss(database_path):
    from pc_builder.database import create_component

    component_id = create_component("cpu", "AMD", "Тест", database_path=database_path)
    with pytest.raises(TypeError):
        create_component("cpu", "AMD", "Другая", quantity=0, database_path=database_path)
    with pytest.raises(DatabaseError):
        update_component(component_id, quantity=0, database_path=database_path)
    assert "quantity" not in get_component(component_id, database_path)
    with pytest.raises(DatabaseError, match="не должны повторяться"):
        create_custom_attribute(
            component_id, "Список", "enum", "A", enum_options=["A", "A"],
            database_path=database_path,
        )
    assert get_custom_attributes(component_id, database_path) == []
