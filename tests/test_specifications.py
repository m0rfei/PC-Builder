"""Проверки типизированных спецификаций компонентов."""

import sqlite3

import pytest

from pc_builder.database import SCHEMA_VERSION, DatabaseError, create_component_model, get_connection, initialize_database
from pc_builder.schema_v3 import COMPONENT_SPEC_TABLES
from pc_builder.specifications import (
    create_component_spec,
    get_component_spec,
    update_component_spec,
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "specifications.db"
    initialize_database(path)
    return path


def _model(path, component_type):
    return create_component_model(component_type, "Maker", "Model", database_path=path)


def test_all_ten_component_types_have_specification_tables(db):
    expected_types = {
        "motherboard", "cpu", "ram", "gpu", "psu", "ssd", "hdd",
        "cpu_cooler", "case_fan", "case",
    }
    assert set(COMPONENT_SPEC_TABLES) == expected_types

    for component_type in expected_types:
        model_id = _model(db, component_type)
        create_component_spec(model_id, database_path=db)
        assert get_component_spec(model_id, db)["model_id"] == model_id


def test_saves_and_reads_numeric_boolean_and_null_values(db):
    model_id = _model(db, "cpu")
    create_component_spec(
        model_id,
        socket="AM5",
        cores=8,
        threads=16,
        base_clock_mhz=4200.0,
        has_integrated_gpu=False,
        database_path=db,
    )

    spec = get_component_spec(model_id, db)
    assert spec["cores"] == 8
    assert spec["threads"] == 16
    assert spec["base_clock_mhz"] == 4200.0
    assert spec["has_integrated_gpu"] is False
    assert spec["boost_clock_mhz"] is None
    assert spec["tdp_w"] is None

    update_component_spec(model_id, tdp_w=65.0, database_path=db)
    assert get_component_spec(model_id, db)["tdp_w"] == 65.0


def test_lists_store_multiple_sockets_connectors_and_case_support(db):
    cooler_id = _model(db, "cpu_cooler")
    create_component_spec(cooler_id, supported_sockets=["AM5", "LGA1700"], database_path=db)
    assert get_component_spec(cooler_id, db)["supported_sockets"] == ["AM5", "LGA1700"]

    gpu_id = _model(db, "gpu")
    create_component_spec(
        gpu_id,
        power_connectors={"pcie_8pin": 2, "12v_2x6": 1},
        database_path=db,
    )
    assert get_component_spec(gpu_id, db)["power_connectors"] == {"12v_2x6": 1, "pcie_8pin": 2}

    case_id = _model(db, "case")
    create_component_spec(
        case_id,
        form_factors_supported=["atx", "mini_itx"],
        radiator_support=[240, 360],
        database_path=db,
    )
    spec = get_component_spec(case_id, db)
    assert spec["form_factors_supported"] == ["atx", "mini_itx"]
    assert spec["radiator_support"] == [240, 360]


@pytest.mark.parametrize(
    ("component_type", "values"),
    [
        ("cpu", {"cores": -1}),
        ("cpu", {"base_clock_mhz": float("nan")}),
        ("cpu", {"has_integrated_gpu": 1}),
        ("gpu", {"slot_width": -2.0}),
        ("psu", {"pcie_6_2pin_count": -1}),
        ("cpu_cooler", {"supported_sockets": ["AM5", "AM5"]}),
        ("case", {"radiator_support": [0]}),
    ],
)
def test_rejects_invalid_specification_values(db, component_type, values):
    model_id = _model(db, component_type)
    with pytest.raises(DatabaseError):
        create_component_spec(model_id, database_path=db, **values)


def test_specification_fields_must_match_model_type_in_api_and_sqlite(db):
    cpu_id = _model(db, "cpu")
    with pytest.raises(DatabaseError, match="неизвестные поля"):
        create_component_spec(cpu_id, vram_gb=8, database_path=db)

    with pytest.raises(DatabaseError):
        with get_connection(db) as connection:
            connection.execute("INSERT INTO gpu_specs (model_id) VALUES (?)", (cpu_id,))

    with pytest.raises(DatabaseError, match="Неизвестный тип"):
        _model(db, "optical_drive")


def test_v2_migration_preserves_existing_rows_and_can_be_reapplied(tmp_path):
    path = tmp_path / "version2.db"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE component_models (
                id INTEGER PRIMARY KEY, component_type TEXT NOT NULL, manufacturer TEXT NOT NULL,
                model_name TEXT NOT NULL, part_number TEXT, description TEXT, notes TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE component_instances (
                id INTEGER PRIMARY KEY, model_id INTEGER NOT NULL, serial_number TEXT, notes TEXT,
                ownership_status TEXT NOT NULL, created_at TEXT NOT NULL, archived_at TEXT
            );
            CREATE TABLE custom_attributes (
                id INTEGER PRIMARY KEY, model_id INTEGER NOT NULL, name TEXT NOT NULL, value_type TEXT NOT NULL,
                value_text TEXT, value_number REAL, value_boolean INTEGER, value_enum TEXT, unit TEXT
            );
            CREATE TABLE component_images (
                id INTEGER PRIMARY KEY, model_id INTEGER NOT NULL, relative_path TEXT NOT NULL,
                caption TEXT, sort_order INTEGER NOT NULL
            );
            INSERT INTO component_models VALUES (1,'gpu','M','G',NULL,NULL,NULL,'created','updated');
            INSERT INTO component_instances VALUES (2,1,'SN','notes','owned','created',NULL);
            INSERT INTO custom_attributes VALUES (3,1,'label','text','saved',NULL,NULL,NULL,NULL);
            INSERT INTO component_images VALUES (4,1,'images/card.png','caption',0);
            PRAGMA user_version = 2;
        """)

    initialize_database(path)
    initialize_database(path)

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("SELECT serial_number FROM component_instances WHERE id=2").fetchone()[0] == "SN"
        assert connection.execute("SELECT value_text FROM custom_attributes WHERE id=3").fetchone()[0] == "saved"
        assert connection.execute("SELECT relative_path FROM component_images WHERE id=4").fetchone()[0] == "images/card.png"
        assert connection.execute("SELECT COUNT(*) FROM gpu_specs").fetchone()[0] == 0


def test_failed_migration_rolls_back_schema_and_version(tmp_path):
    path = tmp_path / "conflict.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE component_models (id INTEGER PRIMARY KEY, component_type TEXT NOT NULL)")
        connection.execute("CREATE TABLE component_instances (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE custom_attributes (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE component_images (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE cpu_specs (legacy TEXT)")
        connection.execute("PRAGMA user_version = 2")

    with pytest.raises(DatabaseError, match="миграцию"):
        initialize_database(path)

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "motherboard_specs" not in names
    assert "cpu_specs" in names


def test_v4_migration_preserves_specs_custom_values_and_child_relations(tmp_path):
    path = tmp_path / "version4.db"
    from pc_builder.schema_v4 import migrate_schema_v4
    from pc_builder.database import _create_schema_v2
    from pc_builder.schema_v3 import create_schema_v3

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        _create_schema_v2(connection)
        create_schema_v3(connection)
        connection.execute("PRAGMA user_version=3")
        migrate_schema_v4(connection)
        models = [(1, "gpu"), (2, "motherboard"), (3, "cpu"), (4, "ram"), (5, "psu"),
                  (6, "ssd"), (7, "hdd"), (8, "cpu_cooler"), (9, "case_fan"), (10, "case")]
        connection.executemany(
            "INSERT INTO component_models(id,component_type,manufacturer,model_name) VALUES (?,?,'Maker','Model')",
            models,
        )
        connection.execute("INSERT INTO gpu_specs(model_id,vram_gb,vram_type) VALUES (1,0.125,'gddr6')")
        connection.execute("INSERT INTO gpu_power_connectors VALUES (1,'pcie_8pin',2)")
        connection.execute("INSERT INTO motherboard_specs(model_id,socket,form_factor,ram_type,pcie_version) VALUES (2,'AM5','atx','ddr5','5.0')")
        connection.execute("INSERT INTO cpu_specs(model_id,socket,cores,base_clock_mhz) VALUES (3,'AM5',8,4200)")
        connection.execute("INSERT INTO ram_specs(model_id,ram_type,capacity_gb,frequency_mhz,form_factor) VALUES (4,'ddr5',0.125,6000,'dimm')")
        connection.execute("INSERT INTO psu_specs(model_id,rated_power_w,form_factor,efficiency_rating) VALUES (5,850,'atx','80_plus_gold')")
        connection.execute("INSERT INTO ssd_specs(model_id,capacity_gb,form_factor,interface_type,pcie_version) VALUES (6,1000,'m2_2280','pcie_nvme','4.0')")
        connection.execute("INSERT INTO hdd_specs(model_id,capacity_gb,form_factor,interface_type) VALUES (7,4000,'3_5_in','sata')")
        connection.execute("INSERT INTO cpu_cooler_specs(model_id,cooling_type,height_mm) VALUES (8,'air',160)")
        connection.execute("INSERT INTO cpu_cooler_supported_sockets VALUES (8,'AM5')")
        connection.execute("INSERT INTO case_fan_specs(model_id,size_mm,connector_type) VALUES (9,120,'4_pin_pwm')")
        connection.execute("INSERT INTO case_specs(model_id,max_gpu_length_mm) VALUES (10,350)")
        connection.execute("INSERT INTO case_supported_form_factors VALUES (10,'atx')")
        connection.execute("INSERT INTO case_radiator_support VALUES (10,360)")
        connection.execute("INSERT INTO custom_attributes(model_id,name,value_type,value_enum) VALUES (1,'Режим','enum','старое')")

    initialize_database(path)
    initialize_database(path)

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("SELECT vram_gb,vram_type,chip_manufacturer FROM gpu_specs WHERE model_id=1").fetchone() == (0.125, "gddr6", None)
        assert connection.execute("SELECT connector_type,quantity FROM gpu_power_connectors WHERE model_id=1").fetchone() == ("pcie_8pin", 2)
        assert connection.execute("SELECT socket,form_factor,ram_type,pcie_version FROM motherboard_specs WHERE model_id=2").fetchone() == ("AM5", "atx", "ddr5", "5.0")
        assert connection.execute("SELECT capacity_gb,frequency_mhz FROM ram_specs WHERE model_id=4").fetchone() == (0.125, 6000.0)
        assert connection.execute("SELECT socket,cores,base_clock_mhz FROM cpu_specs WHERE model_id=3").fetchone() == ("AM5", 8, 4200.0)
        assert connection.execute("SELECT form_factor,efficiency_rating FROM psu_specs WHERE model_id=5").fetchone() == ("atx", "80_plus_gold")
        assert connection.execute("SELECT capacity_gb,interface_type,protocol FROM ssd_specs WHERE model_id=6").fetchone() == (1000.0, "pcie", "nvme")
        assert connection.execute("SELECT cooling_type,height_mm FROM cpu_cooler_specs WHERE model_id=8").fetchone() == ("air", 160.0)
        assert connection.execute("SELECT socket FROM cpu_cooler_supported_sockets WHERE model_id=8").fetchone()[0] == "AM5"
        assert connection.execute("SELECT connector_type FROM case_fan_specs WHERE model_id=9").fetchone()[0] == "4_pin_pwm"
        assert connection.execute("SELECT form_factor FROM case_supported_form_factors WHERE model_id=10").fetchone()[0] == "atx"
        assert connection.execute("SELECT size_mm FROM case_radiator_support WHERE model_id=10").fetchone()[0] == 360
        assert connection.execute("SELECT value_enum FROM custom_attributes WHERE model_id=1").fetchone()[0] == "старое"
        assert connection.execute("SELECT COUNT(*) FROM custom_attribute_options").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_dynamic_specification_options_are_persisted_and_checked(db):
    model_id = _model(db, "motherboard")
    create_component_spec(
        model_id, socket="Socket Future", pcie_version="7.0", form_factor="XL-ATX",
        database_path=db,
    )
    from pc_builder.specifications import list_specification_options

    assert {row["value"] for row in list_specification_options("motherboard", "socket", db)} >= {"Socket Future", "LGA775", "AM4", "AM5"}
    assert {row["value"] for row in list_specification_options("motherboard", "pcie_version", db)} >= {"7.0", "4.0"}
    assert {row["value"] for row in list_specification_options("motherboard", "form_factor", db)} >= {"XL-ATX", "atx"}
    with pytest.raises(DatabaseError):
        with get_connection(db) as connection:
            connection.execute("UPDATE motherboard_specs SET pcie_version='8.0' WHERE model_id=?", (model_id,))
