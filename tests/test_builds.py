"""Тесты миграции, API и интерфейса сборок ПК."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sqlite3

import pytest
from PySide6.QtWidgets import QApplication

from pc_builder.builds_widgets import BuildEditorDialog, BuildFormDialog, BuildsPage, ComponentPickerDialog
from pc_builder.catalog import list_owned_models
from pc_builder.database import (
    SCHEMA_VERSION, DatabaseError, add_build_component, archive_component,
    create_build, create_component, delete_build, delete_component, get_build,
    get_build_components, initialize_database, list_builds, remove_build_component,
    list_build_slots, restore_component, update_build, update_build_component_quantity,
)
from pc_builder.main_window import MainWindow
from pc_builder.specifications import create_component_spec, get_component_spec


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "builds.db"
    initialize_database(path)
    return path


def test_migration_from_v7_and_repeat_preserve_existing_data(db):
    component = create_component("cpu", "AMD", "Ryzen sample", database_path=db)
    create_component_spec(component, cores=6, socket="AM4", database_path=db)
    with sqlite3.connect(db) as connection:
        connection.execute("DROP TABLE build_components")
        connection.execute("DROP TABLE builds")
        connection.execute("PRAGMA user_version=7")
    initialize_database(db)
    initialize_database(db)
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"builds", "build_components"} <= tables
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert get_component_spec(component, db)["cores"] == 6


def test_build_create_read_update_and_delete_does_not_delete_components(db):
    component = create_component("gpu", "ASUS", "GPU", database_path=db)
    build_id = create_build("Игровой ПК", description="Тестовое описание", database_path=db)
    item_id = add_build_component(build_id, component, quantity=2, database_path=db)
    assert item_id > 0
    assert get_build(build_id, db)["name"] == "Игровой ПК"
    assert list_builds(db)[0]["description"] == "Тестовое описание"
    update_build(build_id, name="Новый ПК", description="", database_path=db)
    assert get_build(build_id, db)["name"] == "Новый ПК"
    delete_build(build_id, db)
    assert get_build(build_id, db) is None
    assert get_build_components(build_id, db) == []
    assert len(list_owned_models(database_path=db)) == 1


def test_build_item_quantity_validation_duplicates_and_catalog_is_unchanged(db):
    component = create_component("ram", "Kingston", "DDR5 module", database_path=db)
    build_id = create_build("Memory build", database_path=db)
    add_build_component(build_id, component, quantity=3, database_path=db)
    for invalid in (0, -1, 1.5, True):
        with pytest.raises(DatabaseError, match="целым числом не меньше 1"):
            update_build_component_quantity(get_build_components(build_id, db)[0]["item_id"], invalid, db)
        with pytest.raises(DatabaseError, match="целым числом не меньше 1"):
            add_build_component(build_id, component + 1000, invalid, db)
    with pytest.raises(DatabaseError, match="уже есть"):
        add_build_component(build_id, component, database_path=db)
    update_build_component_quantity(get_build_components(build_id, db)[0]["item_id"], 4, db)
    assert get_build_components(build_id, db)[0]["quantity"] == 4
    initialize_database(db)
    assert get_build_components(build_id, db)[0]["quantity"] == 4
    assert len(list_owned_models(database_path=db)) == 1
    remove_build_component(build_id, component, db)
    assert get_build_components(build_id, db) == []
    assert len(list_owned_models(database_path=db)) == 1


def test_archived_component_remains_in_existing_build_but_not_new_picker(qapp, db):
    component = create_component("ssd", "Samsung", "SSD", database_path=db)
    build_id = create_build("Storage build", database_path=db)
    add_build_component(build_id, component, database_path=db)
    archive_component(component, db)
    saved_item = get_build_components(build_id, db)[0]
    assert saved_item["status"] == "archived"
    assert saved_item["quantity"] == 1
    with pytest.raises(DatabaseError, match="только комплектующее из каталога"):
        add_build_component(build_id, component, database_path=db)
    picker = ComponentPickerDialog(db)
    assert picker.table.rowCount() == 0
    restore_component(component, db)
    picker.refresh()
    assert picker.table.rowCount() == 1
    picker.close()


def test_deleting_component_clears_link_but_retains_named_build_slot(db):
    component = create_component("hdd", "Seagate", "Disk", database_path=db)
    build_id = create_build("Disk build", database_path=db)
    add_build_component(build_id, component, database_path=db)
    delete_component(component, db)
    assert get_build_components(build_id, db) == []
    assert get_build(build_id, db) is not None
    retained = list_build_slots(build_id, db)
    assert any(row["category"] == "storage" and row["component_id"] is None for row in retained)
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_builds_ui_and_navigation_are_available(qapp, db):
    component = create_component("cpu", "AMD", "CPU", database_path=db)
    build_id = create_build("Для интерфейса", database_path=db)
    add_build_component(build_id, component, quantity=2, database_path=db)
    page = BuildsPage(db)
    assert page.build_table.rowCount() == 1
    assert page.items_table.rowCount() == 1
    assert page.items_table.item(0, 3).text() == "2"
    editor = BuildEditorDialog(build_id, db)
    assert editor.readiness_label.text().startswith("Сборка не готова")
    assert any(slot["component_id"] == component for slot in list_build_slots(build_id, db))
    assert len(editor.compatibility_label.text()) > 0
    dialog = BuildFormDialog()
    assert dialog.windowTitle() == "Новая сборка"
    window = MainWindow(db)
    assert window.navigation.count() == 3
    assert window.navigation.item(2).text() == "Сборки ПК"
    assert window.references_button.text() == "Справочники"
    assert SCHEMA_VERSION == 12
    editor.close()
    page.close()
    window.close()
