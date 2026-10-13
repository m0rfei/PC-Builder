"""Структурированная поддержка нескольких типов памяти материнской платы."""

import sqlite3


def migrate_schema_v12(connection: sqlite3.Connection) -> None:
    """Создаёт список поддерживаемой DDR и переносит старое scalar-значение.

    Старый столбец motherboard_specs.ram_type сохраняется для обратной
    совместимости. Операция должна выполняться в транзакции мигратора.
    """
    connection.execute(
        """CREATE TABLE IF NOT EXISTS motherboard_supported_ram_types (
            model_id INTEGER NOT NULL REFERENCES motherboard_specs(model_id) ON DELETE CASCADE,
            ram_type TEXT NOT NULL CHECK (length(trim(ram_type)) > 0),
            PRIMARY KEY (model_id, ram_type)
        )"""
    )
    connection.execute(
        """INSERT OR IGNORE INTO motherboard_supported_ram_types(model_id, ram_type)
           SELECT model_id, ram_type FROM motherboard_specs
           WHERE ram_type IS NOT NULL AND length(trim(ram_type)) > 0"""
    )
    connection.execute("PRAGMA user_version = 12")
