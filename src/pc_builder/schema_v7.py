"""Миграция 7: категорийные справочники производителей и недостающие поля."""

import sqlite3

from .reference_data import INITIAL_MANUFACTURERS, INITIAL_SPEC_OPTIONS


NEW_COLUMNS = {
    "cpu_specs": ("ram_type TEXT", "pcie_version TEXT"),
    "ram_specs": ("ecc INTEGER CHECK (ecc IS NULL OR ecc IN (0, 1))",),
    "gpu_specs": ("cooling_type TEXT",),
    "ssd_specs": ("protocol TEXT",),
    "case_fan_specs": ("lighting INTEGER CHECK (lighting IS NULL OR lighting IN (0, 1))",),
}


def _option(connection: sqlite3.Connection, kind: str, field: str, value: str, label: str) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO specification_options(component_type,field_name,value,display_value) VALUES(?,?,?,?)",
        (kind, field, value, label),
    )


def migrate_schema_v7(connection: sqlite3.Connection) -> None:
    """Добавляет поля и справочники, не удаляя старые столбцы или значения."""
    connection.execute("""CREATE TABLE IF NOT EXISTS manufacturer_options (
        component_type TEXT NOT NULL,
        value TEXT NOT NULL CHECK(length(trim(value)) > 0),
        PRIMARY KEY(component_type, value)
    )""")

    for table, columns in NEW_COLUMNS.items():
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for definition in columns:
            name = definition.split()[0]
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    for component_type, values in INITIAL_MANUFACTURERS.items():
        connection.executemany(
            "INSERT OR IGNORE INTO manufacturer_options(component_type,value) VALUES(?,?)",
            [(component_type, value) for value in values],
        )
    # Старые и пользовательские производители также становятся видны в своём разделе.
    connection.execute("""INSERT OR IGNORE INTO manufacturer_options(component_type,value)
        SELECT component_type, trim(manufacturer) FROM component_models
        WHERE manufacturer IS NOT NULL AND length(trim(manufacturer)) > 0""")

    for component_type, fields in INITIAL_SPEC_OPTIONS.items():
        for field, options in fields.items():
            for value, label in options.items():
                _option(connection, component_type, field, value, label)
    for component_type, field, values in (
        ("gpu", "cooling_type", {"air": "Воздушное", "passive": "Пассивное"}),
        ("ssd", "interface_type", {"sata": "SATA", "pcie": "PCIe"}),
    ):
        for value, label in values.items():
            _option(connection, component_type, field, value, label)

    # Существовавшее значение PCIe/NVMe уже однозначно задаёт обе характеристики.
    connection.execute("""UPDATE ssd_specs SET interface_type='pcie', protocol='nvme'
        WHERE interface_type='pcie_nvme' AND protocol IS NULL""")

    # Новые ограниченные поля проверяются тем же расширяемым справочником v5.
    for component_type, table, field in (
        ("cpu", "cpu_specs", "ram_type"), ("cpu", "cpu_specs", "pcie_version"),
        ("gpu", "gpu_specs", "cooling_type"), ("ssd", "ssd_specs", "protocol"),
    ):
        for action in ("INSERT", "UPDATE"):
            trigger = f"spec_option_v7_{component_type}_{field}_{action.lower()}"
            connection.execute(f"""CREATE TRIGGER IF NOT EXISTS {trigger} BEFORE {action} ON {table}
                WHEN NEW.{field} IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM specification_options WHERE component_type='{component_type}'
                    AND field_name='{field}' AND value=NEW.{field})
                BEGIN SELECT RAISE(ABORT, 'unknown specification option'); END""")
    connection.execute("PRAGMA user_version=7")
