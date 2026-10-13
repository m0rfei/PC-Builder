"""Проверки расширяемых справочников и новых типизированных полей."""

import sqlite3

import pytest

from pc_builder.database import (
    DatabaseError, add_manufacturer_option, create_component_model,
    create_custom_attribute, delete_manufacturer_option, get_custom_attributes,
    get_custom_attribute_options,
    initialize_database, list_manufacturer_options,
)
from pc_builder.reference_data import INITIAL_MANUFACTURERS, SOCKET_OPTIONS
from pc_builder.specifications import create_component_spec, get_component_spec, list_specification_options


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "reference.db"
    initialize_database(path)
    return path


def test_category_manufacturer_lists_are_separate_and_seeded(db):
    for kind, expected in INITIAL_MANUFACTURERS.items():
        assert set(expected) <= set(list_manufacturer_options(kind, db))
    assert "AMD" not in list_manufacturer_options("hdd", db)
    assert "Intel" not in list_manufacturer_options("hdd", db)
    assert "AMD" not in list_manufacturer_options("ssd", db)
    assert "Intel" in list_manufacturer_options("ssd", db)
    assert not ({"NVIDIA", "AMD", "Intel"} & set(INITIAL_MANUFACTURERS["gpu"]))


def test_add_remove_manufacturer_and_used_value_is_protected(db):
    add_manufacturer_option("hdd", "Новый бренд", db)
    initialize_database(db)
    assert "Новый бренд" in list_manufacturer_options("hdd", db)
    delete_manufacturer_option("hdd", "Новый бренд", db)
    assert "Новый бренд" not in list_manufacturer_options("hdd", db)

    model_id = create_component_model("hdd", "Старый бренд", "Диск", database_path=db)
    assert "Старый бренд" in list_manufacturer_options("hdd", db)
    with pytest.raises(DatabaseError, match="используется комплектующими"):
        delete_manufacturer_option("hdd", "Старый бренд", db)
    assert "Старый бренд" in list_manufacturer_options("hdd", db)
    with pytest.raises(DatabaseError, match="уже есть"):
        add_manufacturer_option("hdd", "seagate", db)


def test_new_fields_and_multi_socket_values_persist(db):
    cpu = create_component_model("cpu", "AMD", "CPU", database_path=db)
    create_component_spec(cpu, ram_type="ddr5", pcie_version="5.0", database_path=db)
    assert get_component_spec(cpu, db)["ram_type"] == "ddr5"
    assert get_component_spec(cpu, db)["pcie_version"] == "5.0"

    ram = create_component_model("ram", "Kingston", "DIMM", database_path=db)
    create_component_spec(ram, ram_type="ddr", form_factor="dimm", ecc=True, database_path=db)
    assert get_component_spec(ram, db)["ecc"] is True

    gpu = create_component_model("gpu", "ASUS", "GPU", database_path=db)
    create_component_spec(gpu, cooling_type="passive", database_path=db)
    assert get_component_spec(gpu, db)["cooling_type"] == "passive"

    ssd = create_component_model("ssd", "Samsung", "SSD", database_path=db)
    create_component_spec(ssd, form_factor="m2", interface_type="pcie", protocol="nvme", database_path=db)
    assert get_component_spec(ssd, db)["protocol"] == "nvme"

    cooler = create_component_model("cpu_cooler", "Noctua", "Cooler", database_path=db)
    create_component_spec(cooler, supported_sockets=["AM4", "LGA1700", "Custom Socket"], database_path=db)
    assert get_component_spec(cooler, db)["supported_sockets"] == ["AM4", "Custom Socket", "LGA1700"]
    assert {item["value"] for item in list_specification_options("cpu_cooler", "socket", db)} >= set(SOCKET_OPTIONS)


def test_migration_v6_to_v7_preserves_existing_characteristics(db):
    model_id = create_component_model("gpu", "Legacy GPU maker", "Legacy card", database_path=db)
    create_component_spec(model_id, vram_gb=12, chip_manufacturer="NVIDIA", database_path=db)
    create_custom_attribute(
        model_id, "Цвет", "enum", "чёрный", enum_options=["чёрный", "серый"], database_path=db
    )
    with sqlite3.connect(db) as connection:
        connection.execute("DROP TABLE manufacturer_options")
        for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'spec_option_v7_%'").fetchall():
            connection.execute(f'DROP TRIGGER "{name}"')
        for table, column in (("cpu_specs", "ram_type"), ("cpu_specs", "pcie_version"),
                              ("ram_specs", "ecc"), ("gpu_specs", "cooling_type"),
                              ("ssd_specs", "protocol"), ("case_fan_specs", "lighting")):
            connection.execute(f'ALTER TABLE "{table}" DROP COLUMN "{column}"')
        connection.execute("PRAGMA user_version=6")

    initialize_database(db)
    initialize_database(db)
    assert get_component_spec(model_id, db)["vram_gb"] == 12
    assert get_component_spec(model_id, db)["chip_manufacturer"] == "NVIDIA"
    attribute = get_custom_attributes(model_id, db)[0]
    assert attribute["value_enum"] == "чёрный"
    assert get_custom_attribute_options(attribute["id"], db) == ["чёрный", "серый"]
    assert "Legacy GPU maker" in list_manufacturer_options("gpu", db)

