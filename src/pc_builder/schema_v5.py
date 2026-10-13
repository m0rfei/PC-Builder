"""Миграция 5: редактируемые справочники и значения пользовательских списков."""

import re
import sqlite3

from .reference_data import INITIAL_SPEC_OPTIONS
from .schema_v3 import COMPONENT_SPEC_TABLES


CHILD_TABLES = (
    "gpu_power_connectors", "cpu_cooler_supported_sockets",
    "case_supported_form_factors", "case_radiator_support",
)


def _remove_enum_checks(sql: str) -> str:
    """Снимает только ограничения фиксированного списка; числовые CHECK остаются."""
    fields = ("form_factor", "ram_type", "pcie_version", "vram_type", "efficiency_rating",
              "interface_type", "cooling_type", "connector_type")
    for field in fields:
        pattern = rf"(\b{field}\s+TEXT(?:\s+NOT NULL)?)\s+CHECK\s*\(\s*(?:{field}\s+IS NULL\s+OR\s+)?{field}\s+IN\s*\([^)]*\)\s*\)"
        sql = re.sub(pattern, r"\1", sql, flags=re.IGNORECASE)
    return sql


def _rebuild_table(connection: sqlite3.Connection, table: str, *, added_columns: tuple[str, ...] = ()) -> None:
    row = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if row is None:
        return
    old_sql = row[0]
    columns = [item[1] for item in connection.execute(f"PRAGMA table_info({table})")]
    create_sql = _remove_enum_checks(old_sql)
    temp_name = f"__v5_{table}"
    create_sql = re.sub(rf"CREATE\s+TABLE\s+{re.escape(table)}\b", f"CREATE TABLE {temp_name}", create_sql, count=1, flags=re.IGNORECASE)
    if added_columns:
        create_sql = create_sql.rstrip().removesuffix(")") + ", " + ", ".join(f"{column} TEXT" for column in added_columns) + ")"
    connection.execute(create_sql)
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    connection.execute(f"INSERT INTO {temp_name} ({quoted_columns}) SELECT {quoted_columns} FROM {table}")
    connection.execute(f"DROP TABLE {table}")
    connection.execute(f"ALTER TABLE {temp_name} RENAME TO {table}")


def _option(connection: sqlite3.Connection, component_type: str, field: str, value: str, label: str | None = None) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO specification_options(component_type, field_name, value, display_value) VALUES (?, ?, ?, ?)",
        (component_type, field, value, label or value),
    )


def _seed_current_values(connection: sqlite3.Connection) -> None:
    for component_type, fields in INITIAL_SPEC_OPTIONS.items():
        for field, options in fields.items():
            for value, label in options.items():
                _option(connection, component_type, field, value, label)
    scalar_fields = {
        "motherboard": ("socket", "chipset", "form_factor", "ram_type", "pcie_version"),
        "cpu": ("socket",),
        "ram": ("ram_type", "form_factor"),
        "gpu": ("vram_type", "chip_manufacturer"),
        "psu": ("modularity", "form_factor", "efficiency_rating"),
        "ssd": ("form_factor", "interface_type", "pcie_version"),
        "hdd": ("form_factor", "interface_type"),
        "cpu_cooler": ("cooling_type",),
        "case_fan": ("connector_type",),
    }
    for component_type, fields in scalar_fields.items():
        table = COMPONENT_SPEC_TABLES[component_type]
        existing = {item[1] for item in connection.execute(f"PRAGMA table_info({table})")}
        for field in fields:
            if field not in existing:
                continue
            for (value,) in connection.execute(f"SELECT DISTINCT {field} FROM {table} WHERE {field} IS NOT NULL"):
                _option(connection, component_type, field, value)
    for row in connection.execute("SELECT DISTINCT socket FROM cpu_cooler_supported_sockets"):
        _option(connection, "cpu_cooler", "socket", row[0])
    for row in connection.execute("SELECT DISTINCT connector_type FROM gpu_power_connectors"):
        _option(connection, "gpu", "power_connectors", row[0])
    for row in connection.execute("SELECT DISTINCT form_factor FROM case_supported_form_factors"):
        _option(connection, "case", "form_factors_supported", row[0])


def _create_option_triggers(connection: sqlite3.Connection) -> None:
    fields_by_type = {
        "motherboard": ("socket", "chipset", "form_factor", "ram_type", "pcie_version"),
        "cpu": ("socket",),
        "ram": ("ram_type", "form_factor"),
        "gpu": ("vram_type", "chip_manufacturer"),
        "psu": ("modularity", "form_factor", "efficiency_rating"),
        "ssd": ("form_factor", "interface_type", "pcie_version"),
        "hdd": ("form_factor", "interface_type"),
        "cpu_cooler": ("cooling_type",),
        "case_fan": ("connector_type",),
    }
    for component_type, fields in fields_by_type.items():
        table = COMPONENT_SPEC_TABLES[component_type]
        for field in fields:
            for action in ("INSERT", "UPDATE"):
                name = f"spec_option_{component_type}_{field}_{action.lower()}"
                connection.execute(
                    f"""CREATE TRIGGER {name} BEFORE {action} ON {table}
                    WHEN NEW.{field} IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM specification_options
                        WHERE component_type='{component_type}' AND field_name='{field}' AND value=NEW.{field}
                    ) BEGIN SELECT RAISE(ABORT, 'unknown specification option'); END"""
                )
    for table, value_field, component_type, option_field in (
        ("gpu_power_connectors", "connector_type", "gpu", "power_connectors"),
        ("cpu_cooler_supported_sockets", "socket", "cpu_cooler", "socket"),
        ("case_supported_form_factors", "form_factor", "case", "form_factors_supported"),
    ):
        for action in ("INSERT", "UPDATE"):
            name = f"spec_option_{table}_{action.lower()}"
            connection.execute(
                f"""CREATE TRIGGER {name} BEFORE {action} ON {table}
                WHEN NOT EXISTS (SELECT 1 FROM specification_options
                    WHERE component_type='{component_type}' AND field_name='{option_field}' AND value=NEW.{value_field})
                BEGIN SELECT RAISE(ABORT, 'unknown specification option'); END"""
            )


def migrate_schema_v5(connection: sqlite3.Connection) -> None:
    """Добавляет справочники и сохраняет спецификации и пользовательские значения."""
    child_data = {}
    child_sql = {}
    for table in CHILD_TABLES:
        statement = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if statement is None:
            continue
        child_sql[table] = statement[0]
        child_data[table] = [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
    for table in CHILD_TABLES:
        if table in child_sql:
            connection.execute(f"DROP TABLE {table}")

    connection.execute("""CREATE TABLE specification_options (
        component_type TEXT NOT NULL,
        field_name TEXT NOT NULL,
        value TEXT NOT NULL,
        display_value TEXT NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(component_type, field_name, value)
    )""")
    connection.execute("""CREATE TABLE custom_attribute_options (
        attribute_id INTEGER NOT NULL REFERENCES custom_attributes(id) ON DELETE CASCADE,
        value TEXT NOT NULL CHECK(length(trim(value)) > 0),
        sort_order INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(attribute_id, value)
    )""")

    for component_type, table in COMPONENT_SPEC_TABLES.items():
        added_columns = ()
        if component_type == "gpu":
            added_columns = ("chip_manufacturer",)
        elif component_type == "psu":
            added_columns = ("modularity",)
        _rebuild_table(connection, table, added_columns=added_columns)
    for table, sql in child_sql.items():
        connection.execute(_remove_enum_checks(sql))
        if child_data[table]:
            columns = [item[1] for item in connection.execute(f"PRAGMA table_info({table})")]
            columns_sql = ", ".join(f'"{column}"' for column in columns)
            placeholders = ", ".join("?" for _ in columns)
            connection.executemany(f"INSERT INTO {table} ({columns_sql}) VALUES ({placeholders})", child_data[table])

    _seed_current_values(connection)

    # Enum checks are now backed by a user-extensible reference table.
    _create_option_triggers(connection)

    for component_type, table in COMPONENT_SPEC_TABLES.items():
        connection.execute(
            f"""CREATE TRIGGER {table}_component_type_insert BEFORE INSERT ON {table}
            WHEN (SELECT component_type FROM component_models WHERE id=NEW.model_id) != '{component_type}'
            BEGIN SELECT RAISE(ABORT, 'specification type does not match component model'); END"""
        )
        connection.execute(
            f"""CREATE TRIGGER {table}_component_type_update BEFORE UPDATE ON {table}
            WHEN (SELECT component_type FROM component_models WHERE id=NEW.model_id) != '{component_type}'
            BEGIN SELECT RAISE(ABORT, 'specification type does not match component model'); END"""
        )
    connection.execute("PRAGMA user_version=5")
