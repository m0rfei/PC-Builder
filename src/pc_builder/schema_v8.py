"""Миграция 8: сохранённые сборки ПК и их состав."""

import sqlite3


def migrate_schema_v8(connection: sqlite3.Connection) -> None:
    """Создаёт таблицы сборок без изменения существующих записей каталога."""
    connection.execute("""CREATE TABLE IF NOT EXISTS builds (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL CHECK(length(trim(name)) > 0),
        description TEXT,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS build_components (
        id INTEGER PRIMARY KEY,
        build_id INTEGER NOT NULL REFERENCES builds(id) ON DELETE CASCADE,
        component_id INTEGER NOT NULL REFERENCES component_models(id) ON DELETE CASCADE,
        quantity INTEGER NOT NULL DEFAULT 1 CHECK(typeof(quantity)='integer' AND quantity >= 1),
        UNIQUE(build_id, component_id)
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_build_components_component_id ON build_components(component_id)")
    connection.execute("PRAGMA user_version=8")
