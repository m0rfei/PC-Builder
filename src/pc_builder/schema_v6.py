"""Миграция 6: одна запись каталога соответствует одной физической единице."""

import sqlite3

from .schema_v3 import COMPONENT_SPEC_TABLES


CHILD_SPEC_TABLES = (
    "gpu_power_connectors",
    "cpu_cooler_supported_sockets",
    "case_supported_form_factors",
    "case_radiator_support",
)


def _copy_model_dependents(connection: sqlite3.Connection, source_id: int, target_id: int) -> None:
    """Копирует спецификацию и пользовательские значения без повторного использования ID."""
    for table in COMPONENT_SPEC_TABLES.values():
        row = connection.execute(f"SELECT * FROM {table} WHERE model_id=?", (source_id,)).fetchone()
        if row is None:
            continue
        columns = [item[1] for item in connection.execute(f"PRAGMA table_info({table})")]
        values = dict(zip(columns, tuple(row)))
        values["model_id"] = target_id
        names = ", ".join(f'"{name}"' for name in columns)
        placeholders = ", ".join("?" for _ in columns)
        connection.execute(
            f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
            tuple(values[name] for name in columns),
        )

    for table in CHILD_SPEC_TABLES:
        rows = connection.execute(f"SELECT * FROM {table} WHERE model_id=?", (source_id,)).fetchall()
        if not rows:
            continue
        columns = [item[1] for item in connection.execute(f"PRAGMA table_info({table})")]
        names = ", ".join(f'"{name}"' for name in columns)
        placeholders = ", ".join("?" for _ in columns)
        for row in rows:
            values = dict(zip(columns, tuple(row)))
            values["model_id"] = target_id
            connection.execute(
                f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
                tuple(values[name] for name in columns),
            )

    attributes = connection.execute(
        "SELECT * FROM custom_attributes WHERE model_id=? ORDER BY id", (source_id,)
    ).fetchall()
    attribute_columns = [item[1] for item in connection.execute("PRAGMA table_info(custom_attributes)")]
    copied_columns = [name for name in attribute_columns if name not in {"id", "model_id"}]
    names = ", ".join(["model_id", *(f'"{name}"' for name in copied_columns)])
    placeholders = ", ".join("?" for _ in range(len(copied_columns) + 1))
    for row in attributes:
        values = dict(zip(attribute_columns, tuple(row)))
        cursor = connection.execute(
            f"INSERT INTO custom_attributes ({names}) VALUES ({placeholders})",
            (target_id, *(values[name] for name in copied_columns)),
        )
        new_attribute_id = cursor.lastrowid
        if "custom_attribute_options" in {
            item[0] for item in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='custom_attribute_options'"
            )
        }:
            options = connection.execute(
                "SELECT value, sort_order FROM custom_attribute_options WHERE attribute_id=? ORDER BY sort_order, value",
                (values["id"],),
            ).fetchall()
            connection.executemany(
                "INSERT INTO custom_attribute_options(attribute_id,value,sort_order) VALUES (?,?,?)",
                [(new_attribute_id, option[0], option[1]) for option in options],
            )


def migrate_schema_v6(connection: sqlite3.Connection) -> int:
    """Размножает строки по старому количеству и удаляет агрегатный столбец.

    Существующая строка сохраняет свой ID; добавленные записи получают новые ID.
    Для копий сохраняются общие поля, статус/дата архивации и все спецификации и
    пользовательские характеристики. Изображения остаются у исходной записи.
    Возвращает количество созданных дополнительных комплектующих.
    """
    columns = {row[1] for row in connection.execute("PRAGMA table_info(component_models)")}
    if "quantity" not in columns:
        connection.execute("PRAGMA user_version=6")
        return 0

    rows = connection.execute(
        "SELECT * FROM component_models WHERE quantity > 1 ORDER BY id"
    ).fetchall()
    # Сохраняем исходный порядок столбцов, который выдаёт PRAGMA.
    model_columns = [row[1] for row in connection.execute("PRAGMA table_info(component_models)") if row[1] not in {"id", "quantity"}]
    names = ", ".join(f'"{name}"' for name in model_columns)
    placeholders = ", ".join("?" for _ in model_columns)
    created = 0

    for source in rows:
        source_values = dict(source)
        for _ in range(source_values["quantity"] - 1):
            cursor = connection.execute(
                f"INSERT INTO component_models ({names}) VALUES ({placeholders})",
                tuple(source_values[name] for name in model_columns),
            )
            duplicate_id = cursor.lastrowid
            _copy_model_dependents(connection, source_values["id"], duplicate_id)
            created += 1

    connection.execute("ALTER TABLE component_models DROP COLUMN quantity")
    connection.execute("PRAGMA user_version=6")
    return created
