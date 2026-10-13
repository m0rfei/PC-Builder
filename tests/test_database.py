"""Проверки создания и повторной инициализации базы."""

import sqlite3

import pytest

from pc_builder import database
from pc_builder.database import DatabaseError, SCHEMA_VERSION, initialize_database


def test_creates_database_and_initializes_schema(tmp_path):
    database_path = tmp_path / "nested" / "pc_builder.db"

    result = initialize_database(database_path)

    assert result == database_path
    assert database_path.is_file()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = ?", ("table",)
        ).fetchall()
        assert {row[0] for row in tables} == {
            "component_models",
            "component_instances",
            "custom_attributes",
            "component_images",
            "specification_options",
            "custom_attribute_options",
            "manufacturer_options",
            "cpu_specs", "motherboard_specs", "ram_specs", "gpu_specs", "psu_specs",
            "ssd_specs", "hdd_specs", "cpu_cooler_specs", "case_fan_specs", "case_specs",
            "gpu_power_connectors", "cpu_cooler_supported_sockets",
            "case_supported_form_factors", "case_radiator_support",
            "builds", "build_components",
                "component_model_images",
                "custom_attribute_definitions",
                "custom_attribute_definition_options",
                "motherboard_supported_ram_types",
        }


def test_reinitialization_does_not_duplicate_objects(tmp_path):
    database_path = tmp_path / "pc_builder.db"
    initialize_database(database_path)
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        objects = connection.execute(
            "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
    assert {row for row in objects if row[0] == "table"} == {
        ("table", "component_models"),
        ("table", "component_instances"),
        ("table", "custom_attributes"),
        ("table", "component_images"),
        ("table", "specification_options"),
        ("table", "custom_attribute_options"),
        ("table", "manufacturer_options"),
        ("table", "cpu_specs"),
        ("table", "motherboard_specs"),
        ("table", "ram_specs"),
        ("table", "gpu_specs"),
        ("table", "psu_specs"),
        ("table", "ssd_specs"),
        ("table", "hdd_specs"),
        ("table", "cpu_cooler_specs"),
        ("table", "case_fan_specs"),
        ("table", "case_specs"),
        ("table", "gpu_power_connectors"),
        ("table", "cpu_cooler_supported_sockets"),
        ("table", "case_supported_form_factors"),
        ("table", "case_radiator_support"),
        ("table", "builds"),
        ("table", "build_components"),
        ("table", "component_model_images"),
        ("table", "custom_attribute_definitions"),
        ("table", "custom_attribute_definition_options"),
        ("table", "motherboard_supported_ram_types"),
    }


def test_unavailable_path_has_clear_error(tmp_path):
    parent_file = tmp_path / "not_a_directory"
    parent_file.write_text("test", encoding="utf-8")

    with pytest.raises(DatabaseError, match="Не удалось открыть базу данных"):
        initialize_database(parent_file / "pc_builder.db")


def test_packaged_database_path_uses_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setattr(database.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    assert database.get_default_database_path() == tmp_path / "LocalAppData" / "PC-Builder" / "pc_builder.db"


def test_development_database_path_stays_in_project(monkeypatch):
    monkeypatch.setattr(database.sys, "frozen", False, raising=False)
    assert database.get_default_database_path() == database.PROJECT_ROOT / "data" / "pc_builder.db"
