"""Переход от агрегированного количества к одной записи на комплектующее."""

import sqlite3

import pytest

from pc_builder.database import (
    SCHEMA_VERSION,
    DatabaseError,
    _create_schema_v2,
    archive_component,
    create_component_image,
    create_component,
    create_custom_attribute,
    delete_component,
    get_component,
    get_custom_attributes,
    get_connection,
    initialize_database,
    list_components,
    restore_component,
    update_component,
)
from pc_builder.schema_v3 import COMPONENT_SPEC_TABLES, create_schema_v3
from pc_builder.schema_v4 import migrate_schema_v4
from pc_builder.schema_v5 import migrate_schema_v5
from pc_builder.specifications import create_component_spec, get_component_spec


def _make_v3_database(path):
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        _create_schema_v2(connection)
        create_schema_v3(connection)
        connection.execute("PRAGMA user_version=3")


def _seed_v3(path):
    _make_v3_database(path)
    with sqlite3.connect(path) as connection:
        # Active single, active pair, no instances, fully archived pair, and mixed statuses.
        rows = [
            (1, "cpu", "Maker", "Single"),
            (2, "gpu", "Maker", "Pair"),
            (3, "ram", "Maker", "No units"),
            (4, "ssd", "Maker", "Archived"),
            (5, "psu", "Maker", "Mixed"),
        ]
        connection.executemany(
            "INSERT INTO component_models (id, component_type, manufacturer, model_name) VALUES (?, ?, ?, ?)", rows
        )
        connection.executemany(
            "INSERT INTO component_instances (id, model_id, ownership_status, archived_at) VALUES (?, ?, ?, ?)",
            [(11, 1, "owned", None), (21, 2, "owned", None), (22, 2, "owned", None),
             (41, 4, "archived", "2024-01-01T00:00:00Z"),
             (42, 4, "archived", "2024-03-01T00:00:00Z"),
             (51, 5, "owned", None), (52, 5, "archived", "2024-02-01T00:00:00Z")]
        )
        connection.execute("INSERT INTO cpu_specs (model_id, socket, cores) VALUES (1, 'AM4', 6)")
        connection.execute(
            "INSERT INTO custom_attributes (model_id, name, value_type, value_text) VALUES (1, 'Цвет', 'text', 'чёрный')"
        )
        connection.execute(
            "INSERT INTO component_images (model_id, relative_path) VALUES (1, 'images/cpu.png')"
        )


def test_v3_migration_preserves_data_and_derives_model_state(tmp_path):
    path = tmp_path / "before.db"
    _seed_v3(path)
    initialize_database(path)
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM component_instances").fetchone()[0] == 7
        assert "quantity" not in {row[1] for row in connection.execute("PRAGMA table_info(component_models)")}
        states = connection.execute(
            "SELECT model_name, status, archived_at, COUNT(*) FROM component_models GROUP BY model_name,status,archived_at"
        ).fetchall()
        counts = {(name, status, archived_at): count for name, status, archived_at, count in states}
        assert counts[("Single", "owned", None)] == 1
        assert counts[("Pair", "owned", None)] == 2
        assert counts[("No units", "owned", None)] == 1
        assert counts[("Archived", "archived", "2024-03-01T00:00:00Z")] == 2
        assert counts[("Mixed", "owned", None)] == 2
        assert connection.execute("SELECT COUNT(*) FROM component_models").fetchone()[0] == 8
        assert connection.execute("SELECT socket, cores FROM cpu_specs WHERE model_id=1").fetchone() == ("AM4", 6)
        assert connection.execute("SELECT value_text FROM custom_attributes WHERE model_id=1").fetchone()[0] == "чёрный"
        assert connection.execute("SELECT relative_path FROM component_images WHERE model_id=1").fetchone()[0] == "images/cpu.png"
        assert {table for (table,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_specs'"
        )} >= set(COMPONENT_SPEC_TABLES.values())


def test_individual_component_crud_archive_restore_and_delete(tmp_path):
    path = tmp_path / "crud.db"
    initialize_database(path)
    one = create_component("cpu", "Maker", "One", database_path=path)
    many = create_component("ram", "Maker", "Four", database_path=path)
    assert "quantity" not in get_component(one, path)
    assert "quantity" not in get_component(many, path)
    assert len(list_components(status="owned", database_path=path)) == 2
    with pytest.raises(TypeError):
        create_component("cpu", "Maker", "Invalid", quantity=4, database_path=path)
    with pytest.raises(DatabaseError):
        update_component(one, quantity=0, database_path=path)
    update_component(many, notes="Обновлено", database_path=path)
    assert get_component(many, path)["notes"] == "Обновлено"
    archive_component(many, path)
    assert get_component(many, path)["status"] == "archived"
    assert get_component(many, path)["archived_at"]
    restore_component(many, path)
    assert (get_component(many, path)["status"], get_component(many, path)["archived_at"]) == ("owned", None)

    create_component_spec(one, socket="AM4", cores=6, database_path=path)
    attribute_id = create_custom_attribute(one, "Тест", "text", "значение", database_path=path)
    delete_component(one, path)
    assert get_component(one, path) is None
    with pytest.raises(DatabaseError):
        get_component_spec(one, path)
    assert get_custom_attributes(one, path) == []
    with get_connection(path) as connection:
        assert connection.execute("SELECT 1 FROM custom_attributes WHERE id=?", (attribute_id,)).fetchone() is None
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_v5_migration_splits_owned_and_archived_rows_with_all_characteristics(tmp_path):
    path = tmp_path / "filled-v5.db"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        _create_schema_v2(connection)
        create_schema_v3(connection)
        connection.execute("PRAGMA user_version=3")
        connection.execute(
            "INSERT INTO component_models(id,component_type,manufacturer,model_name,description,notes) VALUES (1,'cpu','AMD','Ryzen','CPU description','CPU note')"
        )
        connection.execute(
            "INSERT INTO component_models(id,component_type,manufacturer,model_name,description,notes) VALUES (2,'gpu','ASUS','RTX','GPU description','GPU note')"
        )
        connection.executemany(
            "INSERT INTO component_instances(model_id,serial_number) VALUES (1,?)",
            [("CPU-1",), ("CPU-2",), ("CPU-3",)],
        )
        connection.executemany(
            "INSERT INTO component_instances(model_id,serial_number,ownership_status,archived_at) VALUES (2,?,'archived','2025-04-03T10:00:00Z')",
            [("GPU-1",), ("GPU-2",)],
        )
        connection.commit()

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        migrate_schema_v4(connection)
        migrate_schema_v5(connection)

    create_component_spec(1, socket="AM5", cores=8, threads=16, base_clock_mhz=4200.5, database_path=path)
    create_component_spec(2, vram_gb=12, vram_type="gddr6x", power_w=285,
                          power_connectors={"pcie_8pin": 2}, database_path=path)
    # Заполняем именно legacy-схему v5 напрямую. Современный API атрибутов
    # требует определения v10 и поэтому не подходит для подготовки старой БД.
    with get_connection(path) as connection:
        cursor = connection.execute(
            """INSERT INTO custom_attributes
               (model_id,name,value_type,value_enum) VALUES (1,'Серия','enum','Zen 4')"""
        )
        connection.executemany(
            "INSERT INTO custom_attribute_options(attribute_id,value,sort_order) VALUES (?,?,?)",
            [(cursor.lastrowid, value, order) for order, value in enumerate(("Zen 2", "Zen 3", "Zen 4"))],
        )
        connection.execute(
            """INSERT INTO custom_attributes
               (model_id,name,value_type,value_text) VALUES (2,'Цвет','text','чёрный')"""
        )
    image_id = create_component_image(2, "images/gpu.png", database_path=path)

    assert initialize_database(path) == path
    initialize_database(path)
    with get_connection(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert "quantity" not in {row[1] for row in connection.execute("PRAGMA table_info(component_models)")}
        cpu_rows = connection.execute("SELECT id,status,archived_at FROM component_models WHERE model_name='Ryzen' ORDER BY id").fetchall()
        gpu_rows = connection.execute("SELECT id,status,archived_at FROM component_models WHERE model_name='RTX' ORDER BY id").fetchall()
        assert len(cpu_rows) == 3 and all(tuple(row[1:]) == ("owned", None) for row in cpu_rows)
        assert len(gpu_rows) == 2 and all(tuple(row[1:]) == ("archived", "2025-04-03T10:00:00Z") for row in gpu_rows)
        cpu_ids = [row[0] for row in cpu_rows]
        gpu_ids = [row[0] for row in gpu_rows]
        for model_id in cpu_ids:
            spec = connection.execute("SELECT socket,cores,threads,base_clock_mhz FROM cpu_specs WHERE model_id=?", (model_id,)).fetchone()
            assert tuple(spec) == ("AM5", 8, 16, 4200.5)
            attribute = connection.execute("SELECT id,value_enum FROM custom_attributes WHERE model_id=?", (model_id,)).fetchone()
            assert attribute[1] == "Zen 4"
            assert [row[0] for row in connection.execute("SELECT value FROM custom_attribute_options WHERE attribute_id=? ORDER BY sort_order", (attribute[0],)).fetchall()] == ["Zen 2", "Zen 3", "Zen 4"]
        for model_id in gpu_ids:
            spec = connection.execute("SELECT vram_gb,vram_type,power_w FROM gpu_specs WHERE model_id=?", (model_id,)).fetchone()
            assert tuple(spec) == (12, "gddr6x", 285)
            assert [tuple(row) for row in connection.execute("SELECT connector_type,quantity FROM gpu_power_connectors WHERE model_id=?", (model_id,)).fetchall()] == [("pcie_8pin", 2)]
            assert connection.execute("SELECT value_text FROM custom_attributes WHERE model_id=?", (model_id,)).fetchone()[0] == "чёрный"
        assert [tuple(row) for row in connection.execute("SELECT id,model_id FROM component_images").fetchall()] == [(image_id, 2)]
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
