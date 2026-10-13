"""Миграция 9: хранение основного изображения комплектующего в SQLite."""

import sqlite3


def migrate_schema_v9(connection: sqlite3.Connection) -> None:
    """Добавляет BLOB-таблицу, не затрагивая старые метаданные изображений."""
    connection.execute("""CREATE TABLE IF NOT EXISTS component_model_images (
        component_id INTEGER PRIMARY KEY
            REFERENCES component_models(id) ON DELETE CASCADE,
        image_data BLOB NOT NULL,
        mime_type TEXT NOT NULL CHECK(mime_type IN ('image/jpeg','image/png')),
        original_name TEXT,
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""")
    connection.execute("PRAGMA user_version=9")
