"""Миграция 10: общие определения пользовательских характеристик по категориям."""

import sqlite3


def migrate_schema_v10(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS custom_attribute_definitions (
        id INTEGER PRIMARY KEY,
        component_type TEXT NOT NULL,
        name TEXT NOT NULL CHECK(length(trim(name)) > 0),
        value_type TEXT NOT NULL CHECK(value_type IN ('text','number','boolean','enum')),
        unit TEXT,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS custom_attribute_definition_options (
        definition_id INTEGER NOT NULL REFERENCES custom_attribute_definitions(id) ON DELETE CASCADE,
        value TEXT NOT NULL CHECK(length(trim(value)) > 0),
        sort_order INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(definition_id,value)
    )""")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(custom_attributes)")}
    if "definition_id" not in columns:
        connection.execute(
            "ALTER TABLE custom_attributes ADD COLUMN definition_id INTEGER "
            "REFERENCES custom_attribute_definitions(id) ON DELETE CASCADE"
        )
    rows = connection.execute("""SELECT a.*,m.component_type
        FROM custom_attributes a JOIN component_models m ON m.id=a.model_id
        ORDER BY a.id""").fetchall()
    definitions: dict[tuple, int] = {}
    has_options = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='custom_attribute_options'"
    ).fetchone() is not None
    for row in rows:
        key = (row["component_type"], row["name"], row["value_type"], row["unit"])
        definition_id = definitions.get(key)
        if definition_id is None:
            cursor = connection.execute(
                "INSERT INTO custom_attribute_definitions(component_type,name,value_type,unit) VALUES(?,?,?,?)",
                key,
            )
            definition_id = cursor.lastrowid
            definitions[key] = definition_id
        connection.execute(
            "UPDATE custom_attributes SET definition_id=? WHERE id=?", (definition_id, row["id"])
        )
        if has_options and row["value_type"] == "enum":
            options = connection.execute(
                "SELECT value,sort_order FROM custom_attribute_options WHERE attribute_id=?",
                (row["id"],),
            ).fetchall()
            connection.executemany(
                "INSERT OR IGNORE INTO custom_attribute_definition_options(definition_id,value,sort_order) VALUES(?,?,?)",
                [(definition_id, option["value"], option["sort_order"]) for option in options],
            )
            if row["value_enum"]:
                connection.execute(
                    "INSERT OR IGNORE INTO custom_attribute_definition_options(definition_id,value,sort_order) VALUES(?,?,?)",
                    (definition_id, row["value_enum"], 0),
                )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_custom_attr_definition ON custom_attributes(definition_id)")
    connection.execute("PRAGMA user_version=10")
