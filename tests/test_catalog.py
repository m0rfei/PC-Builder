"""Тесты каталога версии 4 и его основных операций."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import inspect

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pc_builder.catalog import duplicate_component, list_archived_components, list_owned_models
from pc_builder.catalog_widgets import ArchivePage, CatalogPage
from pc_builder.database import (
    archive_component, create_component, create_custom_attribute, delete_component,
    get_component, get_custom_attributes, get_custom_attribute_options, initialize_database, restore_component,
)
from pc_builder.specifications import create_component_spec, get_component_spec


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def database_path(tmp_path):
    path = tmp_path / "catalog.db"
    initialize_database(path)
    return path


def _component(path, name, *, component_type="gpu", manufacturer="Изготовитель", part_number=None):
    return create_component(
        component_type, manufacturer, name, part_number=part_number,
        database_path=path,
    )


def test_catalog_lists_individual_components_without_quantity(qapp, database_path):
    _component(database_path, "Альфа")
    _component(database_path, "Альфа")
    archived = _component(database_path, "Бета", component_type="cpu")
    archive_component(archived, database_path)
    _component(database_path, "Гамма", component_type="ram")

    page = CatalogPage(database_path)
    assert [row["model_name"] for row in list_owned_models(database_path=database_path)] == ["Альфа", "Альфа", "Гамма"]
    assert page.table.rowCount() == 3
    headers = [page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
    assert headers[:3] == ["Тип", "Производитель", "Название модели"]
    assert "Тип памяти" in headers and "Сокет" in headers
    archive = ArchivePage(database_path)
    assert archive.table.rowCount() == 1
    assert archive.table.columnCount() == 3


def test_search_filter_sort_and_literal_wildcards(database_path):
    first = _component(database_path, "Карта Альфа", manufacturer="Техно", part_number="ABC-42")
    second = _component(database_path, "Карта Бета", manufacturer="Другой", part_number="XYZ")
    literal = _component(database_path, "Карта 100%", manufacturer="Техно")
    card_1000 = _component(database_path, "Карта 1000", manufacturer="Техно")
    cpu = _component(database_path, "Процессор", component_type="cpu")

    assert [row["id"] for row in list_owned_models(search="Альфа", database_path=database_path)] == [first]
    assert {row["id"] for row in list_owned_models(search="Техно", database_path=database_path)} == {first, literal, card_1000}
    assert [row["id"] for row in list_owned_models(search="ABC-42", database_path=database_path)] == [first]
    assert [row["id"] for row in list_owned_models(search="100%", database_path=database_path)] == [literal]
    assert [row["model_name"] for row in list_owned_models(descending=True, database_path=database_path)] == [
        "Процессор", "Карта Бета", "Карта Альфа", "Карта 1000", "Карта 100%"
    ]
    assert [row["id"] for row in list_owned_models(component_type="cpu", database_path=database_path)] == [cpu]


def test_model_form_creates_individual_components_without_quantity(qapp, database_path):
    from pc_builder.catalog_widgets import ModelFormDialog

    first = ModelFormDialog(database_path)
    first.type_combo.setCurrentIndex(first.type_combo.findData("ram"))
    first.manufacturer_input.setEditText("Kingston")
    first.model_name_input.setText("DDR4 4 GB")
    first._save()
    second = ModelFormDialog(database_path)
    second.type_combo.setCurrentIndex(second.type_combo.findData("ram"))
    second.manufacturer_input.setEditText("Kingston")
    second.model_name_input.setText("DDR4 4 GB")
    second._save()
    assert first.model_id != second.model_id
    assert "quantity" not in get_component(first.model_id, database_path)
    assert not hasattr(first, "quantity_input")


def test_model_form_edits_individual_component_without_quantity(qapp, database_path):
    from pc_builder.catalog_widgets import ModelFormDialog

    component_id = _component(database_path, "Исходное название", component_type="gpu")
    dialog = ModelFormDialog(database_path, get_component(component_id, database_path))
    dialog.model_name_input.setText("Новое название")
    dialog.notes_input.setPlainText("Заметка сохранена")
    dialog._save()
    updated = get_component(component_id, database_path)
    assert updated["model_name"] == "Новое название"
    assert updated["notes"] == "Заметка сохранена"
    assert "quantity" not in updated
    assert not hasattr(dialog, "quantity_input")


def test_active_and_archived_context_menus_have_expected_actions(qapp, database_path):
    active = _component(database_path, "В наличии")
    archived = _component(database_path, "В архиве")
    archive_component(archived, database_path)
    catalog = CatalogPage(database_path)
    archived_page = ArchivePage(database_path)
    active_menu, active_actions = catalog._build_context_menu(catalog)
    archive_menu, archive_actions = archived_page._build_context_menu(archived_page)
    assert [action.text() for action in active_actions] == ["Редактировать", "Дублировать", "В архив", "Удалить навсегда"]
    assert [action.text() for action in archive_actions] == ["Открыть / редактировать", "Восстановить", "Удалить навсегда"]
    assert len(active_menu.actions()) == 5 and len(archive_menu.actions()) == 4
    catalog._archive(active)
    assert get_component(active, database_path)["status"] == "archived"
    assert [row["id"] for row in list_archived_components(database_path)] == [archived, active]
    archived_page._restore(archived)
    assert get_component(archived, database_path)["status"] == "owned"


def test_duplicate_copies_fields_specs_and_custom_attributes(database_path):
    source = _component(database_path, "Исходная модель", component_type="cpu")
    create_component_spec(source, socket="AM5", cores=8, threads=16, has_integrated_gpu=True, database_path=database_path)
    create_custom_attribute(source, "Цвет", "text", "чёрный", database_path=database_path)
    create_custom_attribute(source, "Вес", "number", 1.25, unit="кг", database_path=database_path)
    create_custom_attribute(source, "Есть подсветка", "boolean", False, database_path=database_path)
    enum_id = create_custom_attribute(
        source, "Серия", "enum", "Pro", enum_options=["Basic", "Pro", "Max"],
        database_path=database_path,
    )

    duplicate_id = duplicate_component(source, database_path)
    duplicate = get_component(duplicate_id, database_path)
    assert duplicate["model_name"] == "Исходная модель"
    assert duplicate["component_type"] == "cpu"
    assert duplicate["status"] == "owned"
    assert duplicate["archived_at"] is None
    original_spec = get_component_spec(source, database_path)
    duplicate_spec = get_component_spec(duplicate_id, database_path)
    original_spec.pop("model_id")
    duplicate_spec.pop("model_id")
    assert duplicate_spec == original_spec
    original_attrs = {row["name"]: row for row in get_custom_attributes(source, database_path)}
    copied_attrs = {row["name"]: row for row in get_custom_attributes(duplicate_id, database_path)}
    assert set(copied_attrs) == set(original_attrs)
    for name in original_attrs:
        assert {key: copied_attrs[name][key] for key in ("value_type", "value_text", "value_number", "value_boolean", "value_enum", "unit")} == {
            key: original_attrs[name][key] for key in ("value_type", "value_text", "value_number", "value_boolean", "value_enum", "unit")
        }
    assert duplicate_id != source
    copied_enum = next(row for row in get_custom_attributes(duplicate_id, database_path) if row["name"] == "Серия")
    assert get_custom_attribute_options(copied_enum["id"], database_path) == ["Basic", "Pro", "Max"]
    assert get_custom_attribute_options(enum_id, database_path) == ["Basic", "Pro", "Max"]


def test_delete_requires_confirmation_and_then_deletes(qapp, database_path, monkeypatch):
    from pc_builder import catalog_widgets

    component_id = _component(database_path, "Удаляемое")
    page = CatalogPage(database_path)
    calls = []
    monkeypatch.setattr(catalog_widgets, "confirm_delete", lambda _parent, name: calls.append(name) or False)
    page._delete(component_id)
    assert get_component(component_id, database_path) is not None
    assert calls == ["Удаляемое"]
    monkeypatch.setattr(catalog_widgets, "confirm_delete", lambda _parent, _name: True)
    page._delete(component_id)
    assert get_component(component_id, database_path) is None


def test_catalog_ui_does_not_reference_instance_apis():
    from pc_builder import catalog, catalog_widgets

    legacy_names = (
        "create_component_instance", "get_component_instance", "update_component_instance",
        "archive_component_instance", "restore_component_instance",
    )
    source = inspect.getsource(catalog) + inspect.getsource(catalog_widgets)
    assert not any(name in source for name in legacy_names)


def test_dynamic_columns_use_schema_for_all_types_and_populated_fields_for_filter(qapp, database_path):
    from pc_builder.catalog_widgets import CatalogPage

    cpu = _component(database_path, "CPU", component_type="cpu")
    ram = _component(database_path, "RAM", component_type="ram")
    gpu = _component(database_path, "GPU", component_type="gpu")
    create_component_spec(cpu, socket="AM5", cores=8, database_path=database_path)
    create_component_spec(ram, ram_type="ddr4", capacity_gb=8, database_path=database_path)
    create_component_spec(gpu, length_mm=300, database_path=database_path)

    page = CatalogPage(database_path)
    all_headers = [page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
    assert "Сокет" in all_headers and "Тип памяти" in all_headers
    assert "Физические ядра" not in all_headers and "Длина" not in all_headers

    page.type_filter.setCurrentIndex(page.type_filter.findData("cpu"))
    cpu_headers = [page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
    assert "Физические ядра" in cpu_headers
    assert "Сокет" in cpu_headers
    assert "Потоки" not in cpu_headers


def test_custom_dynamic_columns_require_shared_definition_and_populated_value(qapp, database_path):
    cpu = _component(database_path, "CPU", component_type="cpu")
    gpu = _component(database_path, "GPU", component_type="gpu")
    ram = _component(database_path, "RAM", component_type="ram")
    create_custom_attribute(cpu, "Серия", "text", "A", database_path=database_path)
    create_custom_attribute(gpu, "Серия", "text", "B", database_path=database_path)
    create_custom_attribute(ram, "Только RAM", "text", "", database_path=database_path)
    page = CatalogPage(database_path)
    headers = [page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
    assert "Серия" in headers
    assert "Только RAM" not in headers
    page.type_filter.setCurrentIndex(page.type_filter.findData("ram"))
    headers = [page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
    assert "Серия" not in headers
    assert "Только RAM" not in headers


def test_dynamic_numeric_and_text_header_sorting_preserves_search_and_filter(qapp, database_path):
    low = _component(database_path, "CPU 2", component_type="cpu", manufacturer="Zulu")
    high = _component(database_path, "CPU 10", component_type="cpu", manufacturer="Alpha")
    _component(database_path, "Other", component_type="gpu", manufacturer="Beta")
    create_component_spec(low, cores=2, database_path=database_path)
    create_component_spec(high, cores=10, database_path=database_path)
    page = CatalogPage(database_path)
    page.type_filter.setCurrentIndex(page.type_filter.findData("cpu"))
    cores_column = next(i for i, col in enumerate(page._columns) if col["key"] == "cores")
    page._sort_by_header(cores_column)
    assert [page.table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in range(2)] == [low, high]
    page._sort_by_header(cores_column)
    assert [page.table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in range(2)] == [high, low]

    manufacturer_column = next(i for i, col in enumerate(page._columns) if col["key"] == "manufacturer")
    page._sort_by_header(manufacturer_column)
    assert [page.table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in range(2)] == [high, low]
    page.search_input.setText("CPU 2")
    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).data(Qt.ItemDataRole.UserRole) == low


def test_floating_add_button_stays_in_lower_right_on_resize_and_scroll(qapp, database_path):
    for index in range(40):
        _component(database_path, f"GPU {index:02}")
    page = CatalogPage(database_path)
    page.resize(900, 600)
    page.show()
    qapp.processEvents()
    button = page.add_model_button
    area = page.table_area
    assert button.pos().x() + button.width() <= area.width() - 12
    assert button.pos().y() + button.height() <= area.height() - 8
    initial_pos = button.pos()
    page.table.verticalScrollBar().setValue(page.table.verticalScrollBar().maximum())
    qapp.processEvents()
    assert button.pos() == initial_pos
    page.resize(1100, 700)
    qapp.processEvents()
    assert button.pos().x() + button.width() <= area.width() - 12
    assert button.pos().y() + button.height() <= area.height() - 8
