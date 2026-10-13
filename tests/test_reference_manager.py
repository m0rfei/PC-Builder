"""Тесты операций и универсального окна справочников."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sqlite3

import pytest
from PySide6.QtWidgets import QApplication

from pc_builder.database import DatabaseError, create_component, initialize_database
from pc_builder.references import (
    add_reference_value, delete_reference_value, get_reference_fields,
    list_reference_values, rename_reference_value, replace_reference_value,
)
from pc_builder.reference_widgets import ReferenceManagerDialog
from pc_builder.specifications import create_component_spec, get_component_spec


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "references-manager.db"
    initialize_database(path)
    return path


def _usage(path, value):
    return [row for row in list_reference_values("gpu", "chip_manufacturer", path) if row["value"] == value][0]


def test_manager_opens_with_category_fields_and_search(qapp, db):
    dialog = ReferenceManagerDialog(db)
    assert dialog.windowTitle() == "Справочники"
    assert dialog.category_combo.count() == 10
    assert "manufacturer" in {item["field"] for item in get_reference_fields("cpu")}
    dialog.category_combo.setCurrentIndex(dialog.category_combo.findData("hdd"))
    assert dialog.field_combo.findData("manufacturer") >= 0
    assert "AMD" not in {item["value"] for item in list_reference_values("hdd", "manufacturer", db)}
    dialog.search_input.setText("western")
    visible = [dialog.table.item(row, 0).text() for row in range(dialog.table.rowCount())
               if not dialog.table.isRowHidden(row)]
    assert visible == ["Western Digital"]
    dialog.close()


def test_add_rejects_case_and_whitespace_duplicates_and_persists(qapp, db):
    value = add_reference_value("hdd", "manufacturer", "  Test   Brand ", db)
    assert value == "Test Brand"
    with pytest.raises(DatabaseError, match="уже есть"):
        add_reference_value("hdd", "manufacturer", " test brand ", db)
    reopened = ReferenceManagerDialog(db)
    assert value in {row["value"] for row in list_reference_values("hdd", "manufacturer", db)}
    reopened.close()


def test_manager_add_button_writes_to_selected_category(qapp, db, monkeypatch):
    monkeypatch.setattr(
        "pc_builder.reference_widgets.QInputDialog.getText",
        lambda *args, **kwargs: ("Новый бренд SSD", True),
    )
    dialog = ReferenceManagerDialog(db)
    dialog.category_combo.setCurrentIndex(dialog.category_combo.findData("ssd"))
    dialog.field_combo.setCurrentIndex(dialog.field_combo.findData("manufacturer"))
    dialog.add_button.click()
    assert "Новый бренд SSD" in {
        item["value"] for item in list_reference_values("ssd", "manufacturer", db)
    }
    assert "Новый бренд SSD" not in {
        item["value"] for item in list_reference_values("hdd", "manufacturer", db)
    }
    dialog.close()


def test_rename_updates_using_components_and_delete_unused(qapp, db):
    first = create_component("gpu", "Старый бренд", "Карта 1", database_path=db)
    second = create_component("gpu", "Старый бренд", "Карта 2", database_path=db)
    create_component_spec(first, chip_manufacturer="NVIDIA", cooling_type="air", database_path=db)
    create_component_spec(second, chip_manufacturer="NVIDIA", database_path=db)
    rename_reference_value("gpu", "manufacturer", "Старый бренд", "Новый бренд", db)
    assert _usage(db, "NVIDIA")["usage_count"] == 2
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM component_models WHERE manufacturer='Новый бренд'").fetchone()[0] == 2
    add_reference_value("gpu", "manufacturer", "Не используется", db)
    delete_reference_value("gpu", "manufacturer", "Не используется", db)
    assert "Не используется" not in {row["value"] for row in list_reference_values("gpu", "manufacturer", db)}
    with pytest.raises(DatabaseError, match="Сначала замените"):
        delete_reference_value("gpu", "manufacturer", "Новый бренд", db)


def test_replace_used_scalar_and_list_values_is_transactional(db):
    component_id = create_component("gpu", "ASUS", "Карта", database_path=db)
    create_component_spec(
        component_id, chip_manufacturer="NVIDIA", cooling_type="air",
        power_connectors={"pcie_8pin": 2}, database_path=db,
    )
    replace_reference_value("gpu", "chip_manufacturer", "NVIDIA", "AMD", db)
    replace_reference_value("gpu", "cooling_type", "air", "passive", db)
    replace_reference_value("gpu", "power_connectors", "pcie_8pin", "pcie_6pin", db)
    saved = get_component_spec(component_id, db)
    assert saved["chip_manufacturer"] == "AMD"
    assert saved["cooling_type"] == "passive"
    assert saved["power_connectors"] == {"pcie_6pin": 2}
    with pytest.raises(DatabaseError, match="одном выбранном справочнике"):
        replace_reference_value("hdd", "manufacturer", "Seagate", "Samsung", db)
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_cooler_socket_reference_replacement_preserves_multiple_values(db):
    cooler = create_component("cpu_cooler", "Noctua", "Охладитель", database_path=db)
    create_component_spec(cooler, supported_sockets=["AM4", "AM5"], database_path=db)
    add_reference_value("cpu_cooler", "socket", "AM5-new", db)
    replace_reference_value("cpu_cooler", "socket", "AM5", "AM5-new", db)
    assert get_component_spec(cooler, db)["supported_sockets"] == ["AM4", "AM5-new"]
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
