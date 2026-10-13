"""Проверки каталожных таблиц и функций доступа к данным."""

import sqlite3

import pytest

from pc_builder.database import (
    SCHEMA_VERSION,
    DatabaseError,
    archive_component_instance,
    create_component_image,
    create_component_instance,
    create_component_model,
    create_custom_attribute,
    get_component_images,
    get_component_instance,
    get_component_model,
    get_connection,
    get_custom_attributes,
    initialize_database,
    restore_component_instance,
)


@pytest.fixture
def database_path(tmp_path):
    path = tmp_path / "pc_builder.db"
    initialize_database(path)
    return path


def _model(path):
    return create_component_model("gpu", "Пример", "Модель X", database_path=path)


def test_model_can_be_saved_and_read(database_path):
    model_id = create_component_model(
        "gpu", "Пример", "Модель X", part_number="ABC-1", notes="Мои заметки",
        database_path=database_path,
    )

    model = get_component_model(model_id, database_path)
    assert model["manufacturer"] == "Пример"
    assert model["model_name"] == "Модель X"
    assert model["part_number"] == "ABC-1"
    assert model["notes"] == "Мои заметки"
    assert model["created_at"]
    assert model["updated_at"]


def test_one_model_can_have_multiple_physical_instances(database_path):
    model_id = _model(database_path)
    first = create_component_instance(model_id, serial_number="S-1", database_path=database_path)
    second = create_component_instance(model_id, serial_number="S-2", database_path=database_path)

    assert first != second
    assert get_component_instance(first, database_path)["model_id"] == model_id
    assert get_component_instance(second, database_path)["serial_number"] == "S-2"


def test_instance_can_be_archived_and_restored(database_path):
    instance_id = create_component_instance(_model(database_path), database_path=database_path)

    archive_component_instance(instance_id, database_path)
    archived = get_component_instance(instance_id, database_path)
    assert archived["ownership_status"] == "archived"
    assert archived["archived_at"]

    restore_component_instance(instance_id, database_path)
    restored = get_component_instance(instance_id, database_path)
    assert restored["ownership_status"] == "owned"
    assert restored["archived_at"] is None


def test_database_rejects_invalid_status_and_status_date_pair(database_path):
    model_id = _model(database_path)
    with pytest.raises(DatabaseError):
        with get_connection(database_path) as connection:
            connection.execute(
                "INSERT INTO component_instances (model_id, ownership_status) VALUES (?, ?)",
                (model_id, "missing"),
            )
    with pytest.raises(DatabaseError):
        with get_connection(database_path) as connection:
            connection.execute(
                "INSERT INTO component_instances (model_id, ownership_status) VALUES (?, ?)",
                (model_id, "archived"),
            )


def test_custom_attributes_store_supported_types(database_path):
    model_id = _model(database_path)
    create_custom_attribute(model_id, "Память", "text", "GDDR6", database_path=database_path)
    create_custom_attribute(model_id, "Частота", "number", 2500.5, unit="МГц", database_path=database_path)
    create_custom_attribute(model_id, "Подсветка", "boolean", True, database_path=database_path)
    create_custom_attribute(model_id, "Цвет", "enum", "чёрный", database_path=database_path)

    values = {item["name"]: item for item in get_custom_attributes(model_id, database_path)}
    assert values["Память"]["value_text"] == "GDDR6"
    assert values["Частота"]["value_number"] == 2500.5
    assert values["Частота"]["unit"] == "МГц"
    assert values["Подсветка"]["value_boolean"] == 1
    assert values["Цвет"]["value_enum"] == "чёрный"


def test_custom_attribute_rejects_wrong_value_type(database_path):
    model_id = _model(database_path)
    with pytest.raises(DatabaseError, match="не соответствует типу"):
        create_custom_attribute(model_id, "Частота", "number", "быстро", database_path=database_path)

    with pytest.raises(DatabaseError):
        with get_connection(database_path) as connection:
            connection.execute(
                """INSERT INTO custom_attributes (model_id, name, value_type, value_text)
                   VALUES (?, ?, ?, ?)""",
                (model_id, "Неправильное", "number", "текст"),
            )


def test_images_are_related_to_model_and_require_relative_path(database_path):
    model_id = _model(database_path)
    image_id = create_component_image(
        model_id, "images/gpu/front.png", caption="Вид спереди", sort_order=2,
        database_path=database_path,
    )

    image = get_component_images(model_id, database_path)[0]
    assert image["id"] == image_id
    assert image["relative_path"] == "images/gpu/front.png"
    assert image["caption"] == "Вид спереди"
    with pytest.raises(DatabaseError, match="относительным"):
        create_component_image(model_id, "../outside.png", database_path=database_path)


def test_foreign_keys_are_enabled_for_each_connection(database_path):
    with get_connection(database_path) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    with pytest.raises(DatabaseError):
        create_component_instance(99999, database_path=database_path)


def test_migration_preserves_existing_data_and_is_idempotent(tmp_path):
    path = tmp_path / "existing.db"
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE component_models (
            id INTEGER PRIMARY KEY, component_type TEXT NOT NULL, manufacturer TEXT NOT NULL,
            model_name TEXT NOT NULL, part_number TEXT, description TEXT, notes TEXT,
            created_at TEXT NOT NULL DEFAULT 'old-created', updated_at TEXT NOT NULL DEFAULT 'old-updated'
        )""")
        connection.execute("""CREATE TABLE component_instances (
            id INTEGER PRIMARY KEY, model_id INTEGER NOT NULL REFERENCES component_models(id),
            serial_number TEXT, notes TEXT, ownership_status TEXT NOT NULL DEFAULT 'owned',
            created_at TEXT NOT NULL DEFAULT 'old-created', archived_at TEXT
        )""")
        connection.execute("""CREATE TABLE custom_attributes (
            id INTEGER PRIMARY KEY, model_id INTEGER NOT NULL REFERENCES component_models(id),
            name TEXT NOT NULL, value_type TEXT NOT NULL, value_text TEXT, value_number REAL,
            value_boolean INTEGER, value_enum TEXT, unit TEXT
        )""")
        connection.execute("""CREATE TABLE component_images (
            id INTEGER PRIMARY KEY, model_id INTEGER NOT NULL REFERENCES component_models(id),
            relative_path TEXT NOT NULL, caption TEXT, sort_order INTEGER NOT NULL DEFAULT 0
        )""")
        connection.execute(
            "INSERT INTO component_models (id, component_type, manufacturer, model_name) VALUES (7, 'gpu', 'M', 'G')"
        )
        connection.execute("INSERT INTO component_instances (id, model_id, serial_number) VALUES (8, 7, 'SN')")
        connection.execute(
            "INSERT INTO custom_attributes (id, model_id, name, value_type, value_text) VALUES (9, 7, 'цвет', 'text', 'чёрный')"
        )
        connection.execute(
            "INSERT INTO component_images (id, model_id, relative_path) VALUES (10, 7, 'images/gpu.png')"
        )
        connection.execute("PRAGMA user_version = 2")

    initialize_database(path)
    initialize_database(path)

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("SELECT serial_number FROM component_instances WHERE id = 8").fetchone()[0] == "SN"
        assert connection.execute("SELECT value_text FROM custom_attributes WHERE id = 9").fetchone()[0] == "чёрный"
        assert connection.execute("SELECT relative_path FROM component_images WHERE id = 10").fetchone()[0] == "images/gpu.png"
        names = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    assert {"component_models", "component_instances", "custom_attributes", "component_images"} <= names
