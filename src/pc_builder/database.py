"""Создание базы SQLite, миграции и минимальные функции доступа к данным."""

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_default_database_path() -> Path:
    """Chooses a writable per-user location in packaged builds, project data in development."""
    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA")
        root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return root / "PC-Builder" / "pc_builder.db"
    return PROJECT_ROOT / "data" / "pc_builder.db"


DEFAULT_DATABASE_PATH = get_default_database_path()
SCHEMA_VERSION = 12
VALID_COMPONENT_TYPES = frozenset(
    {"motherboard", "cpu", "ram", "gpu", "psu", "ssd", "hdd", "cpu_cooler", "case_fan", "case"}
)
BUILD_SLOT_COMPONENT_TYPES = {
    "cpu": frozenset({"cpu"}),
    "motherboard": frozenset({"motherboard"}),
    "psu": frozenset({"psu"}),
    "case": frozenset({"case"}),
    "gpu": frozenset({"gpu"}),
    "cpu_cooler": frozenset({"cpu_cooler"}),
    "ram": frozenset({"ram"}),
    "storage": frozenset({"hdd", "ssd"}),
    "case_fan": frozenset({"case_fan"}),
}
BUILD_DEFAULT_SLOTS = (
    ("cpu", 0), ("motherboard", 0), ("psu", 0), ("case", 0),
    ("gpu", 0), ("cpu_cooler", 0), ("ram", 0), ("storage", 0),
)


class DatabaseError(RuntimeError):
    """Понятная ошибка при работе с базой PC-Builder."""


@contextmanager
def get_connection(database_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Открывает соединение с включёнными внешними ключами и закрывает его."""
    path = Path(database_path) if database_path is not None else get_default_database_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
    except (OSError, sqlite3.Error) as error:
        raise DatabaseError(f"Не удалось открыть базу данных «{path}»: {error}") from error

    try:
        with connection:
            yield connection
    except sqlite3.Error as error:
        raise DatabaseError(f"Ошибка SQLite для базы «{path}»: {error}") from error
    finally:
        connection.close()


def _create_schema_v2(connection: sqlite3.Connection) -> None:
    """Создаёт основные таблицы каталога; вызывается внутри транзакции."""
    connection.execute(
        """CREATE TABLE component_models (
            id INTEGER PRIMARY KEY,
            component_type TEXT NOT NULL CHECK (length(trim(component_type)) > 0),
            manufacturer TEXT NOT NULL CHECK (length(trim(manufacturer)) > 0),
            model_name TEXT NOT NULL CHECK (length(trim(model_name)) > 0),
            part_number TEXT,
            description TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )"""
    )
    connection.execute(
        """CREATE TABLE component_instances (
            id INTEGER PRIMARY KEY,
            model_id INTEGER NOT NULL REFERENCES component_models(id) ON DELETE RESTRICT,
            serial_number TEXT,
            notes TEXT,
            ownership_status TEXT NOT NULL DEFAULT 'owned'
                CHECK (ownership_status IN ('owned', 'archived')),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            archived_at TEXT,
            CHECK (
                (ownership_status = 'owned' AND archived_at IS NULL)
                OR (ownership_status = 'archived' AND archived_at IS NOT NULL)
            )
        )"""
    )
    connection.execute(
        """CREATE TABLE custom_attributes (
            id INTEGER PRIMARY KEY,
            model_id INTEGER NOT NULL REFERENCES component_models(id) ON DELETE RESTRICT,
            name TEXT NOT NULL CHECK (length(trim(name)) > 0),
            value_type TEXT NOT NULL CHECK (value_type IN ('text', 'number', 'boolean', 'enum')),
            value_text TEXT,
            value_number REAL,
            value_boolean INTEGER CHECK (value_boolean IN (0, 1)),
            value_enum TEXT,
            unit TEXT,
            CHECK (
                (value_type = 'text' AND value_text IS NOT NULL AND value_number IS NULL
                    AND value_boolean IS NULL AND value_enum IS NULL)
                OR (value_type = 'number' AND value_text IS NULL AND value_number IS NOT NULL
                    AND value_boolean IS NULL AND value_enum IS NULL)
                OR (value_type = 'boolean' AND value_text IS NULL AND value_number IS NULL
                    AND value_boolean IS NOT NULL AND value_enum IS NULL)
                OR (value_type = 'enum' AND value_text IS NULL AND value_number IS NULL
                    AND value_boolean IS NULL AND value_enum IS NOT NULL)
            )
        )"""
    )
    connection.execute(
        """CREATE TABLE component_images (
            id INTEGER PRIMARY KEY,
            model_id INTEGER NOT NULL REFERENCES component_models(id) ON DELETE RESTRICT,
            relative_path TEXT NOT NULL CHECK (
                length(trim(relative_path)) > 0
                AND substr(relative_path, 1, 1) NOT IN ('/', char(92))
                AND instr(relative_path, ':') = 0
                AND instr('/' || replace(relative_path, char(92), '/') || '/', '/../') = 0
            ),
            caption TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0
        )"""
    )
    connection.execute("PRAGMA user_version = 2")


def initialize_database(database_path: Path | str | None = None) -> Path:
    """Применяет необходимые миграции и возвращает путь к базе."""
    path = Path(database_path) if database_path is not None else get_default_database_path()
    with get_connection(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise DatabaseError(
                f"Версия базы ({version}) новее поддерживаемой ({SCHEMA_VERSION})."
            )
        if version < 2:
            try:
                connection.execute("BEGIN IMMEDIATE")
                _create_schema_v2(connection)
            except sqlite3.Error as error:
                raise DatabaseError(f"Не удалось применить миграцию базы «{path}»: {error}") from error
            version = 2
        if version < 3:
            try:
                from .schema_v3 import create_schema_v3

                if not connection.in_transaction:
                    connection.execute("BEGIN IMMEDIATE")
                create_schema_v3(connection)
                connection.execute("PRAGMA user_version = 3")
            except sqlite3.Error as error:
                raise DatabaseError(f"Не удалось применить миграцию базы «{path}»: {error}") from error
            version = 3
        if version < 4:
            try:
                from .schema_v4 import migrate_schema_v4

                if not connection.in_transaction:
                    connection.execute("BEGIN IMMEDIATE")
                migrate_schema_v4(connection)
            except sqlite3.Error as error:
                raise DatabaseError(f"Не удалось применить миграцию базы «{path}»: {error}") from error
            version = 4
        if version < 5:
            try:
                from .schema_v5 import migrate_schema_v5

                if not connection.in_transaction:
                    connection.execute("BEGIN IMMEDIATE")
                migrate_schema_v5(connection)
            except sqlite3.Error as error:
                raise DatabaseError(f"Не удалось применить миграцию базы «{path}»: {error}") from error
            version = 5
        if version < 6:
            try:
                from .schema_v6 import migrate_schema_v6

                if not connection.in_transaction:
                    connection.execute("BEGIN IMMEDIATE")
                migrate_schema_v6(connection)
            except (sqlite3.Error, DatabaseError) as error:
                raise DatabaseError(f"Не удалось применить миграцию базы «{path}»: {error}") from error
            version = 6
        if version < 7:
            try:
                from .schema_v7 import migrate_schema_v7

                if not connection.in_transaction:
                    connection.execute("BEGIN IMMEDIATE")
                migrate_schema_v7(connection)
            except sqlite3.Error as error:
                raise DatabaseError(f"Не удалось применить миграцию базы «{path}»: {error}") from error
            version = 7
        if version < 8:
            try:
                from .schema_v8 import migrate_schema_v8

                if not connection.in_transaction:
                    connection.execute("BEGIN IMMEDIATE")
                migrate_schema_v8(connection)
            except sqlite3.Error as error:
                raise DatabaseError(f"Не удалось применить миграцию базы «{path}»: {error}") from error
        if version < 9:
            try:
                from .schema_v9 import migrate_schema_v9

                if not connection.in_transaction:
                    connection.execute("BEGIN IMMEDIATE")
                migrate_schema_v9(connection)
            except sqlite3.Error as error:
                raise DatabaseError(f"Не удалось применить миграцию базы «{path}»: {error}") from error
        if version < 10:
            try:
                from .schema_v10 import migrate_schema_v10

                if not connection.in_transaction:
                    connection.execute("BEGIN IMMEDIATE")
                migrate_schema_v10(connection)
            except sqlite3.Error as error:
                raise DatabaseError(f"Не удалось применить миграцию базы «{path}»: {error}") from error
            version = 10
        if version < 11:
            try:
                from .schema_v11 import migrate_schema_v11

                if not connection.in_transaction:
                    connection.execute("BEGIN IMMEDIATE")
                migrate_schema_v11(connection)
            except sqlite3.Error as error:
                raise DatabaseError(f"Не удалось применить миграцию базы «{path}»: {error}") from error
            version = 11
        if version < 12:
            try:
                from .schema_v12 import migrate_schema_v12

                if not connection.in_transaction:
                    connection.execute("BEGIN IMMEDIATE")
                migrate_schema_v12(connection)
            except sqlite3.Error as error:
                raise DatabaseError(f"Не удалось применить миграцию базы «{path}»: {error}") from error
            version = 12
    return path


def _validate_build_quantity(quantity: int) -> int:
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        raise DatabaseError("Количество в сборке должно быть целым числом не меньше 1.")
    return quantity


def create_build(
    name: str, *, description: str | None = None,
    database_path: Path | str | None = None,
) -> int:
    """Создаёт сборку и возвращает её идентификатор."""
    name = name.strip() if isinstance(name, str) else ""
    if not name:
        raise DatabaseError("Укажите название сборки.")
    description = description.strip() or None if isinstance(description, str) else None
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            "INSERT INTO builds(name,description) VALUES(?,?)", (name, description)
        )
        connection.executemany(
            "INSERT INTO build_components(build_id,category,slot_index,component_id,quantity) "
            "VALUES(?,?,?,NULL,1)",
            [(cursor.lastrowid, category, slot_index) for category, slot_index in BUILD_DEFAULT_SLOTS],
        )
        return cursor.lastrowid


def list_build_slots(build_id: int, database_path: Path | str | None = None) -> list[dict]:
    """Возвращает все слоты сборки, включая пустые и архивные комплектующие."""
    return _fetchall(database_path, """SELECT bc.id AS slot_id,bc.build_id,bc.category,bc.slot_index,
        bc.component_id,bc.quantity,cm.component_type,cm.manufacturer,cm.model_name,cm.status,cm.archived_at
        FROM build_components bc LEFT JOIN component_models cm ON cm.id=bc.component_id
        WHERE bc.build_id=? ORDER BY bc.category,bc.slot_index,bc.id""", (build_id,))


def add_build_slot(
    build_id: int, category: str, database_path: Path | str | None = None,
) -> int:
    """Добавляет пустой динамический слот и возвращает его идентификатор."""
    if category not in {"ram", "storage", "case_fan"}:
        raise DatabaseError("Для этой категории нельзя добавить дополнительный слот.")
    limits = {"ram": 6, "case_fan": 8}
    with get_connection(database_path) as connection:
        if not connection.execute("SELECT 1 FROM builds WHERE id=?", (build_id,)).fetchone():
            raise DatabaseError(f"Сборка {build_id} не найдена.")
        rows = connection.execute(
            "SELECT slot_index FROM build_components WHERE build_id=? AND category=? ORDER BY slot_index",
            (build_id, category),
        ).fetchall()
        if category in limits and len(rows) >= limits[category]:
            raise DatabaseError(f"Достигнут предел слотов для категории: {limits[category]}.")
        index = max((row[0] for row in rows), default=-1) + 1
        cursor = connection.execute(
            "INSERT INTO build_components(build_id,category,slot_index,component_id,quantity) VALUES(?,?,?,NULL,1)",
            (build_id, category, index),
        )
        return cursor.lastrowid


def set_build_slot_component(
    slot_id: int, component_id: int | None, database_path: Path | str | None = None,
) -> None:
    """Назначает активное комплектующее подходящего типа либо очищает слот."""
    with get_connection(database_path) as connection:
        slot = connection.execute(
            "SELECT build_id,category FROM build_components WHERE id=?", (slot_id,)
        ).fetchone()
        if slot is None:
            raise DatabaseError(f"Слот {slot_id} не найден.")
        if component_id is None:
            connection.execute(
                "UPDATE build_components SET component_id=NULL,quantity=1 WHERE id=?", (slot_id,)
            )
            return
        component = connection.execute(
            "SELECT component_type,status FROM component_models WHERE id=?", (component_id,)
        ).fetchone()
        if component is None:
            raise DatabaseError(f"Комплектующее {component_id} не найдено.")
        if component["status"] != "owned":
            raise DatabaseError("Новое комплектующее в слот можно выбрать только из активного каталога.")
        if component["component_type"] not in BUILD_SLOT_COMPONENT_TYPES.get(slot["category"], ()):
            raise DatabaseError("Тип комплектующего не подходит для выбранного слота.")
        connection.execute(
            "UPDATE build_components SET component_id=?,quantity=1 WHERE id=?", (component_id, slot_id)
        )


def delete_build_slot(slot_id: int, database_path: Path | str | None = None) -> None:
    """Удаляет только динамический слот, не затрагивая запись каталога."""
    with get_connection(database_path) as connection:
        slot = connection.execute("SELECT category FROM build_components WHERE id=?", (slot_id,)).fetchone()
        if slot is None:
            raise DatabaseError(f"Слот {slot_id} не найден.")
        if slot["category"] not in {"ram", "storage", "case_fan"}:
            raise DatabaseError("Этот слот нельзя удалить; его можно только очистить.")
        connection.execute("DELETE FROM build_components WHERE id=?", (slot_id,))


def list_builds(database_path: Path | str | None = None) -> list[dict]:
    """Возвращает список сборок по названию."""
    return _fetchall(database_path, "SELECT * FROM builds ORDER BY name COLLATE NOCASE,id")


def get_build(build_id: int, database_path: Path | str | None = None) -> dict | None:
    """Возвращает сборку по идентификатору."""
    return _fetchone(database_path, "SELECT * FROM builds WHERE id=?", (build_id,))


def update_build(
    build_id: int, *, name: str, description: str | None = None,
    database_path: Path | str | None = None,
) -> None:
    """Изменяет название и описание сборки."""
    name = name.strip() if isinstance(name, str) else ""
    if not name:
        raise DatabaseError("Укажите название сборки.")
    description = description.strip() or None if isinstance(description, str) else None
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """UPDATE builds SET name=?,description=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
               WHERE id=?""", (name, description, build_id)
        )
        if cursor.rowcount == 0:
            raise DatabaseError(f"Сборка {build_id} не найдена.")


def delete_build(build_id: int, database_path: Path | str | None = None) -> None:
    """Удаляет сборку; позиции состава удаляются внешним ключом."""
    with get_connection(database_path) as connection:
        cursor = connection.execute("DELETE FROM builds WHERE id=?", (build_id,))
        if cursor.rowcount == 0:
            raise DatabaseError(f"Сборка {build_id} не найдена.")


def add_build_component(
    build_id: int, component_id: int, quantity: int = 1,
    database_path: Path | str | None = None,
) -> int:
    """Добавляет активное комплектующее в состав, без неявного слияния дублей."""
    quantity = _validate_build_quantity(quantity)
    with get_connection(database_path) as connection:
        if not connection.execute("SELECT 1 FROM builds WHERE id=?", (build_id,)).fetchone():
            raise DatabaseError(f"Сборка {build_id} не найдена.")
        component = connection.execute(
            "SELECT component_type,status FROM component_models WHERE id=?", (component_id,)
        ).fetchone()
        if component is None:
            raise DatabaseError(f"Комплектующее {component_id} не найдено.")
        if component["status"] != "owned":
            raise DatabaseError("В новую позицию сборки можно добавить только комплектующее из каталога, не из архива.")
        if connection.execute(
            "SELECT 1 FROM build_components WHERE build_id=? AND component_id=?",
            (build_id, component_id),
        ).fetchone():
            raise DatabaseError("Это комплектующее уже есть в сборке. Измените количество существующей позиции.")
        cursor = connection.execute(
            "INSERT INTO build_components(build_id,category,slot_index,component_id,quantity) "
            "VALUES(?,?,COALESCE((SELECT MAX(slot_index)+1 FROM build_components WHERE build_id=? AND category=?),0),?,?)",
            (build_id, "storage" if component["component_type"] in {"hdd", "ssd"} else component["component_type"],
             build_id, "storage" if component["component_type"] in {"hdd", "ssd"} else component["component_type"],
             component_id, quantity),
        )
        return cursor.lastrowid


def update_build_component_quantity(
    item_id: int, quantity: int, database_path: Path | str | None = None,
) -> None:
    """Изменяет количество одной позиции состава."""
    quantity = _validate_build_quantity(quantity)
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            "UPDATE build_components SET quantity=? WHERE id=?", (quantity, item_id)
        )
        if cursor.rowcount == 0:
            raise DatabaseError(f"Позиция состава {item_id} не найдена.")


def update_build_slot_quantity(
    slot_id: int, quantity: int, database_path: Path | str | None = None,
) -> None:
    """Меняет количество только в категориях с динамическими компонентами."""
    quantity = _validate_build_quantity(quantity)
    with get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT category,component_id FROM build_components WHERE id=?", (slot_id,)
        ).fetchone()
        if row is None:
            raise DatabaseError(f"Слот {slot_id} не найден.")
        if row["category"] not in {"ram", "storage", "case_fan"}:
            raise DatabaseError("Количество можно менять только для модулей ОЗУ, накопителей и корпусных вентиляторов.")
        if row["component_id"] is None:
            raise DatabaseError("Сначала выберите комплектующее в этом слоте.")
        connection.execute("UPDATE build_components SET quantity=? WHERE id=?", (quantity, slot_id))


def remove_build_component(
    build_id: int, component_id: int, database_path: Path | str | None = None,
) -> None:
    """Удаляет позицию из сборки, не затрагивая комплектующее в каталоге."""
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM build_components WHERE id=(SELECT id FROM build_components "
            "WHERE build_id=? AND component_id=? ORDER BY id LIMIT 1)",
            (build_id, component_id),
        )
        if cursor.rowcount == 0:
            raise DatabaseError("Позиция не найдена в этой сборке.")


def get_build_components(build_id: int, database_path: Path | str | None = None) -> list[dict]:
    """Возвращает состав сборки вместе с текущими данными и статусом деталей."""
    return _fetchall(database_path, """SELECT bc.id AS item_id,bc.build_id,bc.category,bc.slot_index,bc.component_id,bc.quantity,
        cm.component_type,cm.manufacturer,cm.model_name,cm.part_number,cm.status,cm.archived_at
        FROM build_components bc JOIN component_models cm ON cm.id=bc.component_id
        WHERE bc.build_id=? ORDER BY cm.component_type,cm.manufacturer COLLATE NOCASE,cm.model_name COLLATE NOCASE,cm.id""",
        (build_id,))


def list_manufacturer_options(component_type: str, database_path: Path | str | None = None) -> list[str]:
    """Список производителей, закреплённых за категорией комплектующего."""
    if component_type not in VALID_COMPONENT_TYPES:
        raise DatabaseError(f"Неизвестный тип комплектующего: {component_type!r}.")
    with get_connection(database_path) as connection:
        return [row[0] for row in connection.execute(
            "SELECT value FROM manufacturer_options WHERE component_type=? ORDER BY value COLLATE NOCASE",
            (component_type,),
        )]


def add_manufacturer_option(component_type: str, value: str, database_path: Path | str | None = None) -> None:
    """Добавляет новое значение, не ограничивая возможность сохранения моделей."""
    value = " ".join(value.split())
    if component_type not in VALID_COMPONENT_TYPES or not value:
        raise DatabaseError("Укажите категорию и непустое название производителя.")
    with get_connection(database_path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM manufacturer_options WHERE component_type=? AND trim(value)=? COLLATE NOCASE",
            (component_type, value),
        ).fetchone()
        if exists:
            raise DatabaseError(f"Производитель «{value}» уже есть в справочнике этой категории.")
        connection.execute(
            "INSERT INTO manufacturer_options(component_type,value) VALUES(?,?)", (component_type, value)
        )


def delete_manufacturer_option(component_type: str, value: str, database_path: Path | str | None = None) -> None:
    """Удаляет значение справочника только если оно не используется комплектующими."""
    with get_connection(database_path) as connection:
        used = connection.execute(
            "SELECT COUNT(*) FROM component_models WHERE component_type=? AND trim(manufacturer)=? COLLATE NOCASE",
            (component_type, value),
        ).fetchone()[0]
        if used:
            raise DatabaseError(f"Нельзя удалить «{value}»: это значение используется комплектующими ({used}).")
        cursor = connection.execute(
            "DELETE FROM manufacturer_options WHERE component_type=? AND trim(value)=? COLLATE NOCASE",
            (component_type, value),
        )
        if cursor.rowcount == 0:
            raise DatabaseError(f"Производитель «{value}» не найден в справочнике этой категории.")


def _execute(database_path: Path | str | None, sql: str, parameters: tuple[Any, ...] = ()) -> int:
    with get_connection(database_path) as connection:
        cursor = connection.execute(sql, parameters)
        return cursor.lastrowid or 0


def _fetchone(database_path: Path | str | None, sql: str, parameters: tuple[Any, ...] = ()):
    with get_connection(database_path) as connection:
        row = connection.execute(sql, parameters).fetchone()
        return dict(row) if row is not None else None


def _fetchall(database_path: Path | str | None, sql: str, parameters: tuple[Any, ...] = ()):
    with get_connection(database_path) as connection:
        return [dict(row) for row in connection.execute(sql, parameters).fetchall()]


def create_component_model(
    component_type: str,
    manufacturer: str,
    model_name: str,
    *,
    part_number: str | None = None,
    description: str | None = None,
    notes: str | None = None,
    database_path: Path | str | None = None,
) -> int:
    """Создаёт модель и возвращает её идентификатор."""
    if component_type not in VALID_COMPONENT_TYPES:
        raise DatabaseError(f"Неизвестный тип комплектующего: {component_type!r}.")
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """INSERT INTO component_models
                (component_type, manufacturer, model_name, part_number, description, notes)
                VALUES (?, ?, ?, ?, ?, ?)""",
            (component_type, manufacturer, model_name, part_number, description, notes),
        )
        _remember_manufacturer(connection, component_type, manufacturer)
        return cursor.lastrowid


def create_component(
    component_type: str,
    manufacturer: str,
    model_name: str,
    *,
    part_number: str | None = None,
    description: str | None = None,
    notes: str | None = None,
    database_path: Path | str | None = None,
) -> int:
    """Создаёт запись комплектующего напрямую в основном каталоге."""
    if component_type not in VALID_COMPONENT_TYPES:
        raise DatabaseError(f"Неизвестный тип комплектующего: {component_type!r}.")
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """INSERT INTO component_models
               (component_type, manufacturer, model_name, part_number, description, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (component_type, manufacturer, model_name, part_number, description, notes),
        )
        _remember_manufacturer(connection, component_type, manufacturer)
        return cursor.lastrowid


def _remember_manufacturer(connection: sqlite3.Connection, component_type: str, manufacturer: str) -> None:
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='manufacturer_options'").fetchone():
        connection.execute(
            "INSERT OR IGNORE INTO manufacturer_options(component_type,value) VALUES(?,?)",
            (component_type, manufacturer.strip()),
        )


def list_components(
    *, status: str | None = None, component_type: str | None = None,
    search: str = "", database_path: Path | str | None = None,
):
    """Возвращает записи каталога с необязательными фильтрами."""
    if status is not None and status not in {"owned", "archived"}:
        raise DatabaseError("Статус должен быть owned или archived.")
    if component_type is not None and component_type not in VALID_COMPONENT_TYPES:
        raise DatabaseError(f"Неизвестный тип комплектующего: {component_type!r}.")
    clauses, parameters = [], []
    if status is not None:
        clauses.append("status = ?")
        parameters.append(status)
    if component_type is not None:
        clauses.append("component_type = ?")
        parameters.append(component_type)
    if search:
        clauses.append("(model_name LIKE ? OR manufacturer LIKE ? OR part_number LIKE ?)")
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        clauses[-1] = "(model_name LIKE ? ESCAPE '\\' OR manufacturer LIKE ? ESCAPE '\\' OR part_number LIKE ? ESCAPE '\\')"
        parameters.extend((pattern, pattern, pattern))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return _fetchall(database_path, f"SELECT * FROM component_models{where} ORDER BY model_name, id", tuple(parameters))


def get_component(component_id: int, database_path: Path | str | None = None):
    """Возвращает комплектующее по ID или None."""
    return _fetchone(database_path, "SELECT * FROM component_models WHERE id = ?", (component_id,))


def update_component(component_id: int, *, database_path: Path | str | None = None, **changes: Any) -> None:
    """Меняет основные поля одного комплектующего."""
    allowed = {"component_type", "manufacturer", "model_name", "part_number", "description", "notes"}
    if not changes or not set(changes) <= allowed:
        raise DatabaseError("Укажите допустимые поля комплектующего для изменения.")
    if "component_type" in changes and changes["component_type"] not in VALID_COMPONENT_TYPES:
        raise DatabaseError(f"Неизвестный тип комплектующего: {changes['component_type']!r}.")
    assignments = ", ".join(f"{column} = ?" for column in changes)
    with get_connection(database_path) as connection:
        if "component_type" in changes:
            current = connection.execute(
                "SELECT component_type FROM component_models WHERE id = ?", (component_id,)
            ).fetchone()
            if current and current["component_type"] != changes["component_type"]:
                from .schema_v3 import COMPONENT_SPEC_TABLES

                for table in COMPONENT_SPEC_TABLES.values():
                    if connection.execute(
                        f"SELECT 1 FROM {table} WHERE model_id = ?", (component_id,)
                    ).fetchone():
                        raise DatabaseError(
                            "Нельзя изменить тип комплектующего, пока сохранены спецификации его прежнего типа."
                        )
        cursor = connection.execute(
            f"UPDATE component_models SET {assignments}, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (*changes.values(), component_id),
        )
        if cursor.rowcount == 0:
            raise DatabaseError(f"Комплектующее {component_id} не найдено.")
        if "manufacturer" in changes:
            kind = changes.get("component_type") or connection.execute(
                "SELECT component_type FROM component_models WHERE id=?", (component_id,)
            ).fetchone()[0]
            _remember_manufacturer(connection, kind, changes["manufacturer"])


def archive_component(component_id: int, database_path: Path | str | None = None) -> None:
    """Архивирует комплектующее целиком."""
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """UPDATE component_models SET status='archived',
               archived_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
               WHERE id=? AND status='owned'""", (component_id,)
        )
        if cursor.rowcount == 0 and not connection.execute(
            "SELECT 1 FROM component_models WHERE id=? AND status='archived'", (component_id,)
        ).fetchone():
            raise DatabaseError(f"Комплектующее {component_id} не найдено.")


def restore_component(component_id: int, database_path: Path | str | None = None) -> None:
    """Восстанавливает комплектующее из архива."""
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """UPDATE component_models SET status='owned', archived_at=NULL,
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
               WHERE id=? AND status='archived'""", (component_id,)
        )
        if cursor.rowcount == 0 and not connection.execute(
            "SELECT 1 FROM component_models WHERE id=? AND status='owned'", (component_id,)
        ).fetchone():
            raise DatabaseError(f"Комплектующее {component_id} не найдено.")


def delete_component(component_id: int, database_path: Path | str | None = None) -> None:
    """Удаляет комплектующее и все его связанные характеристики и старую историю экземпляров."""
    from .schema_v3 import COMPONENT_SPEC_TABLES

    with get_connection(database_path) as connection:
        if not connection.execute("SELECT 1 FROM component_models WHERE id=?", (component_id,)).fetchone():
            raise DatabaseError(f"Комплектующее {component_id} не найдено.")
        # В схеме v11 component_id имеет ON DELETE CASCADE. Сбрасываем ссылку
        # через бизнес-API заранее, чтобы сохранить сам именованный слот сборки:
        # фиксированные категории иначе исчезали бы целиком и их нельзя было
        # заполнить снова из редактора.
        connection.execute(
            "UPDATE build_components SET component_id=NULL,quantity=1 WHERE component_id=?",
            (component_id,),
        )
        connection.execute("DELETE FROM component_instances WHERE model_id=?", (component_id,))
        connection.execute("DELETE FROM custom_attributes WHERE model_id=?", (component_id,))
        connection.execute("DELETE FROM component_images WHERE model_id=?", (component_id,))
        connection.execute("DELETE FROM component_model_images WHERE component_id=?", (component_id,))
        for table in COMPONENT_SPEC_TABLES.values():
            connection.execute(f"DELETE FROM {table} WHERE model_id=?", (component_id,))
        connection.execute("DELETE FROM component_models WHERE id=?", (component_id,))


def get_component_model(model_id: int, database_path: Path | str | None = None):
    """Возвращает модель по идентификатору или None."""
    return _fetchone(database_path, "SELECT * FROM component_models WHERE id = ?", (model_id,))


def update_component_model(
    model_id: int,
    *,
    database_path: Path | str | None = None,
    **changes: str | None,
) -> None:
    """Изменяет переданные поля модели; допустимы только поля описания модели."""
    allowed = {"component_type", "manufacturer", "model_name", "part_number", "description", "notes"}
    if not changes or not set(changes) <= allowed:
        raise DatabaseError("Укажите допустимые поля модели для изменения.")
    if "component_type" in changes and changes["component_type"] not in VALID_COMPONENT_TYPES:
        raise DatabaseError(f"Неизвестный тип комплектующего: {changes['component_type']!r}.")
    assignments = ", ".join(f"{column} = ?" for column in changes)
    values = (*changes.values(), model_id)
    with get_connection(database_path) as connection:
        if "component_type" in changes:
            current = connection.execute(
                "SELECT component_type FROM component_models WHERE id = ?", (model_id,)
            ).fetchone()
            if current and current["component_type"] != changes["component_type"]:
                from .schema_v3 import COMPONENT_SPEC_TABLES

                for table in COMPONENT_SPEC_TABLES.values():
                    if connection.execute(
                        f"SELECT 1 FROM {table} WHERE model_id = ?", (model_id,)
                    ).fetchone():
                        raise DatabaseError(
                            "Нельзя изменить тип модели, пока у неё сохранены стандартные характеристики."
                        )
        connection.execute(
            f"UPDATE component_models SET {assignments}, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            values,
        )


def create_component_instance(
    model_id: int,
    *,
    serial_number: str | None = None,
    notes: str | None = None,
    database_path: Path | str | None = None,
) -> int:
    """Создаёт отдельный физический экземпляр модели."""
    return _execute(
        database_path,
        "INSERT INTO component_instances (model_id, serial_number, notes) VALUES (?, ?, ?)",
        (model_id, serial_number, notes),
    )


def get_component_instance(instance_id: int, database_path: Path | str | None = None):
    """Возвращает физический экземпляр по идентификатору или None."""
    return _fetchone(database_path, "SELECT * FROM component_instances WHERE id = ?", (instance_id,))


def update_component_instance(
    instance_id: int,
    *,
    database_path: Path | str | None = None,
    **changes: str | None,
) -> None:
    """Изменяет серийный номер или заметки экземпляра."""
    allowed = {"serial_number", "notes"}
    if not changes or not set(changes) <= allowed:
        raise DatabaseError("Укажите допустимые поля экземпляра для изменения.")
    assignments = ", ".join(f"{column} = ?" for column in changes)
    _execute(
        database_path,
        f"UPDATE component_instances SET {assignments} WHERE id = ?",
        (*changes.values(), instance_id),
    )


def archive_component_instance(instance_id: int, database_path: Path | str | None = None) -> None:
    """Архивирует экземпляр, сохраняя его запись."""
    _execute(
        database_path,
        """UPDATE component_instances
           SET ownership_status = 'archived', archived_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
           WHERE id = ? AND ownership_status = 'owned'""",
        (instance_id,),
    )


def restore_component_instance(instance_id: int, database_path: Path | str | None = None) -> None:
    """Восстанавливает архивный экземпляр."""
    _execute(
        database_path,
        """UPDATE component_instances SET ownership_status = 'owned', archived_at = NULL
           WHERE id = ? AND ownership_status = 'archived'""",
        (instance_id,),
    )


def create_custom_attribute(
    model_id: int,
    name: str,
    value_type: str,
    value: str | float | bool,
    *,
    unit: str | None = None,
    enum_options: list[str] | None = None,
    definition_id: int | None = None,
    database_path: Path | str | None = None,
) -> int:
    """Создаёт типизированную характеристику модели."""
    typed_values = _custom_attribute_values(value_type, value)
    normalized_options = _validate_enum_options(value_type, value, enum_options)
    if value_type != "enum" and enum_options is None:
        normalized_options = []
    with get_connection(database_path) as connection:
        if definition_id is None:
            model = connection.execute(
                "SELECT component_type FROM component_models WHERE id=?", (model_id,)
            ).fetchone()
            if model is None:
                raise DatabaseError(f"Комплектующее {model_id} не найдено.")
            definition = connection.execute(
                """SELECT * FROM custom_attribute_definitions
                   WHERE component_type=? AND name=? COLLATE NOCASE ORDER BY id LIMIT 1""",
                (model["component_type"], name),
            ).fetchone()
            if definition and definition["value_type"] != value_type:
                raise DatabaseError("Тип характеристики отличается от определения для этой категории.")
            if definition is None:
                cursor = connection.execute(
                    """INSERT INTO custom_attribute_definitions(component_type,name,value_type,unit)
                       VALUES(?,?,?,?)""",
                    (model["component_type"], name, value_type, unit),
                )
                definition_id = cursor.lastrowid
            else:
                definition_id = definition["id"]
            if value_type == "enum":
                definition_options = normalized_options or [value]
                for order, option in enumerate(definition_options):
                    connection.execute(
                        "INSERT OR IGNORE INTO custom_attribute_definition_options(definition_id,value,sort_order) VALUES(?,?,?)",
                        (definition_id, option, order),
                    )
        if definition_id is not None:
            definition = connection.execute(
                """SELECT d.* FROM custom_attribute_definitions d
                   JOIN component_models m ON m.component_type=d.component_type
                   WHERE d.id=? AND m.id=?""", (definition_id, model_id)
            ).fetchone()
            if definition is None:
                raise DatabaseError("Определение не относится к категории этого комплектующего.")
            name, value_type, unit = definition["name"], definition["value_type"], definition["unit"]
            typed_values = _custom_attribute_values(value_type, value)
            if value_type == "enum":
                allowed = [row[0] for row in connection.execute(
                    "SELECT value FROM custom_attribute_definition_options WHERE definition_id=?",
                    (definition_id,),
                )]
                if value not in allowed:
                    raise DatabaseError("Выбранное значение отсутствует в вариантах характеристики.")
        cursor = connection.execute(
            """INSERT INTO custom_attributes
               (model_id, name, value_type, value_text, value_number, value_boolean, value_enum, unit, definition_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (model_id, name, value_type, *typed_values, unit, definition_id),
        )
        attribute_id = cursor.lastrowid
        if normalized_options is not None:
            connection.executemany(
                "INSERT INTO custom_attribute_options(attribute_id, value, sort_order) VALUES (?, ?, ?)",
                [(attribute_id, option, order) for order, option in enumerate(normalized_options)],
            )
        return attribute_id


def _validate_enum_options(value_type: str, value: Any, enum_options: list[str] | None) -> list[str] | None:
    if enum_options is None:
        return None
    if value_type != "enum":
        if enum_options:
            raise DatabaseError("Варианты списка допустимы только для типа «перечисление».")
        return []
    if not isinstance(enum_options, list) or any(not isinstance(item, str) or not item.strip() for item in enum_options):
        raise DatabaseError("Варианты должны быть непустыми текстовыми значениями.")
    options = [item.strip() for item in enum_options]
    if len(options) != len(set(options)):
        raise DatabaseError("Варианты списка не должны повторяться.")
    if options and value not in options:
        raise DatabaseError("Выбранное значение должно входить в список вариантов.")
    return options


def get_custom_attribute_options(attribute_id: int, database_path: Path | str | None = None) -> list[str]:
    """Возвращает сохранённые варианты перечисляемой характеристики."""
    with get_connection(database_path) as connection:
        return [row[0] for row in connection.execute(
            "SELECT value FROM custom_attribute_options WHERE attribute_id=? ORDER BY sort_order, value",
            (attribute_id,),
        ).fetchall()]


def _custom_attribute_values(value_type: str, value: str | float | bool) -> tuple:
    """Проверяет тип значения и возвращает взаимно исключающие столбцы."""
    if value_type not in {"text", "number", "boolean", "enum"}:
        raise DatabaseError("Тип характеристики должен быть text, number, boolean или enum.")
    expected = {"text": str, "number": (int, float), "boolean": bool, "enum": str}[value_type]
    if (isinstance(value, bool) and value_type == "number") or not isinstance(value, expected):
        raise DatabaseError(f"Значение характеристики не соответствует типу «{value_type}».")
    if value_type == "number" and (value != value or value in (float("inf"), float("-inf"))):
        raise DatabaseError("Числовое значение должно быть конечным.")
    columns = {"text": 0, "number": 1, "boolean": 2, "enum": 3}
    values: list[Any] = [None, None, None, None]
    values[columns[value_type]] = int(value) if value_type == "boolean" else value
    return tuple(values)


def update_custom_attribute(
    attribute_id: int,
    name: str,
    value_type: str,
    value: str | float | bool,
    *,
    unit: str | None = None,
    enum_options: list[str] | None = None,
    database_path: Path | str | None = None,
) -> None:
    """Изменяет имя, типизированное значение и единицу характеристики."""
    typed_values = _custom_attribute_values(value_type, value)
    normalized_options = _validate_enum_options(value_type, value, enum_options)
    if value_type != "enum" and enum_options is None:
        normalized_options = []
    linked = _fetchone(
        database_path, "SELECT definition_id FROM custom_attributes WHERE id=?", (attribute_id,)
    )
    if linked and linked["definition_id"] is not None:
        definition_options = (
            enum_options if enum_options is not None else
            get_custom_attribute_definition_options(linked["definition_id"], database_path)
            if value_type == "enum" else []
        )
        update_custom_attribute_definition(
            linked["definition_id"], name=name, value_type=value_type, unit=unit,
            enum_options=definition_options, database_path=database_path,
        )
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """UPDATE custom_attributes
               SET name = ?, value_type = ?, value_text = ?, value_number = ?,
                   value_boolean = ?, value_enum = ?, unit = ?
               WHERE id = ?""",
            (name, value_type, *typed_values, unit, attribute_id),
        )
        if cursor.rowcount == 0:
            raise DatabaseError(f"Дополнительная характеристика {attribute_id} не найдена.")
        if normalized_options is not None:
            connection.execute("DELETE FROM custom_attribute_options WHERE attribute_id=?", (attribute_id,))
            connection.executemany(
                "INSERT INTO custom_attribute_options(attribute_id, value, sort_order) VALUES (?, ?, ?)",
                [(attribute_id, option, order) for order, option in enumerate(normalized_options)],
            )


def delete_custom_attribute(attribute_id: int, database_path: Path | str | None = None) -> None:
    """Удаляет дополнительную характеристику по идентификатору."""
    with get_connection(database_path) as connection:
        cursor = connection.execute("DELETE FROM custom_attributes WHERE id = ?", (attribute_id,))
        if cursor.rowcount == 0:
            raise DatabaseError(f"Дополнительная характеристика {attribute_id} не найдена.")


def get_custom_attributes(model_id: int, database_path: Path | str | None = None):
    """Возвращает все характеристики модели."""
    return _fetchall(
        database_path,
        "SELECT * FROM custom_attributes WHERE model_id = ? ORDER BY id",
        (model_id,),
    )


def list_custom_attribute_definitions(
    component_type: str | None = None, database_path: Path | str | None = None,
) -> list[dict]:
    """Возвращает определения по категориям и число заполненных значений."""
    sql = """SELECT d.*, COUNT(a.id) AS value_count
        FROM custom_attribute_definitions d
        LEFT JOIN custom_attributes a ON a.definition_id=d.id"""
    params: tuple = ()
    if component_type is not None:
        if component_type not in VALID_COMPONENT_TYPES:
            raise DatabaseError(f"Неизвестный тип комплектующего: {component_type!r}.")
        sql += " WHERE d.component_type=?"
        params = (component_type,)
    sql += " GROUP BY d.id ORDER BY d.component_type,d.name COLLATE NOCASE,d.id"
    return _fetchall(database_path, sql, params)


def create_custom_attribute_definition(
    component_type: str, name: str, value_type: str, *, unit: str | None = None,
    enum_options: list[str] | None = None, database_path: Path | str | None = None,
) -> int:
    """Добавляет общее определение; значения комплектующих остаются в custom_attributes."""
    name = name.strip() if isinstance(name, str) else ""
    if component_type not in VALID_COMPONENT_TYPES or not name:
        raise DatabaseError("Выберите категорию и укажите название характеристики.")
    if value_type not in {"text", "number", "boolean", "enum"}:
        raise DatabaseError("Неизвестный тип значения характеристики.")
    options = _normalize_definition_options(value_type, enum_options)
    unit = unit.strip() or None if isinstance(unit, str) else None
    with get_connection(database_path) as connection:
        if connection.execute(
            "SELECT 1 FROM custom_attribute_definitions WHERE component_type=? AND name=? COLLATE NOCASE",
            (component_type, name),
        ).fetchone():
            raise DatabaseError("В этой категории уже есть характеристика с таким названием.")
        cursor = connection.execute(
            "INSERT INTO custom_attribute_definitions(component_type,name,value_type,unit) VALUES(?,?,?,?)",
            (component_type, name, value_type, unit),
        )
        definition_id = cursor.lastrowid
        connection.executemany(
            "INSERT INTO custom_attribute_definition_options(definition_id,value,sort_order) VALUES(?,?,?)",
            [(definition_id, option, index) for index, option in enumerate(options)],
        )
        return definition_id


def _normalize_definition_options(value_type: str, options: list[str] | None) -> list[str]:
    if value_type != "enum":
        if options:
            raise DatabaseError("Варианты допустимы только для характеристики типа «Список».")
        return []
    if not isinstance(options, list) or not options or any(not isinstance(value, str) or not value.strip() for value in options):
        raise DatabaseError("Для характеристики типа «Список» укажите хотя бы один непустой вариант.")
    result = [value.strip() for value in options]
    if len({value.casefold() for value in result}) != len(result):
        raise DatabaseError("Варианты списка не должны повторяться.")
    return result


def get_custom_attribute_definition_options(
    definition_id: int, database_path: Path | str | None = None,
) -> list[str]:
    with get_connection(database_path) as connection:
        return [row[0] for row in connection.execute(
            "SELECT value FROM custom_attribute_definition_options WHERE definition_id=? ORDER BY sort_order,value",
            (definition_id,),
        ).fetchall()]


def update_custom_attribute_definition(
    definition_id: int, *, name: str, value_type: str, unit: str | None,
    enum_options: list[str] | None = None, database_path: Path | str | None = None,
) -> None:
    name = name.strip() if isinstance(name, str) else ""
    if not name or value_type not in {"text", "number", "boolean", "enum"}:
        raise DatabaseError("Проверьте название и тип характеристики.")
    options = _normalize_definition_options(value_type, enum_options)
    unit = unit.strip() or None if isinstance(unit, str) else None
    with get_connection(database_path) as connection:
        definition = connection.execute(
            "SELECT * FROM custom_attribute_definitions WHERE id=?", (definition_id,)
        ).fetchone()
        if definition is None:
            raise DatabaseError("Определение характеристики не найдено.")
        if connection.execute(
            "SELECT 1 FROM custom_attribute_definitions WHERE component_type=? AND name=? COLLATE NOCASE AND id<>?",
            (definition["component_type"], name, definition_id),
        ).fetchone():
            raise DatabaseError("В этой категории уже есть характеристика с таким названием.")
        values = connection.execute(
            "SELECT * FROM custom_attributes WHERE definition_id=?", (definition_id,)
        ).fetchall()
        if value_type != definition["value_type"] and values:
            raise DatabaseError(
                f"Тип нельзя изменить: характеристика уже заполнена у {len(values)} комплектующих. "
                "Сначала удалите значения или создайте отдельную характеристику."
            )
        if value_type == "enum":
            invalid = [row["value_enum"] for row in values if row["value_enum"] not in options]
            if invalid:
                raise DatabaseError(
                    "Список нельзя изменить: некоторые сохранённые значения отсутствуют среди новых вариантов."
                )
        connection.execute(
            "UPDATE custom_attribute_definitions SET name=?,value_type=?,unit=? WHERE id=?",
            (name, value_type, unit, definition_id),
        )
        connection.execute(
            "UPDATE custom_attributes SET name=?,value_type=?,unit=? WHERE definition_id=?",
            (name, value_type, unit, definition_id),
        )
        connection.execute("DELETE FROM custom_attribute_definition_options WHERE definition_id=?", (definition_id,))
        connection.executemany(
            "INSERT INTO custom_attribute_definition_options(definition_id,value,sort_order) VALUES(?,?,?)",
            [(definition_id, option, index) for index, option in enumerate(options)],
        )
        for row in values:
            connection.execute("DELETE FROM custom_attribute_options WHERE attribute_id=?", (row["id"],))
            connection.executemany(
                "INSERT INTO custom_attribute_options(attribute_id,value,sort_order) VALUES(?,?,?)",
                [(row["id"], option, index) for index, option in enumerate(options)],
            )


def delete_custom_attribute_definition(
    definition_id: int, database_path: Path | str | None = None,
) -> int:
    """Удаляет определение и его заполненные значения; возвращает число удалённых значений."""
    with get_connection(database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM custom_attributes WHERE definition_id=?", (definition_id,)
        ).fetchone()[0]
        cursor = connection.execute(
            "DELETE FROM custom_attribute_definitions WHERE id=?", (definition_id,)
        )
        if cursor.rowcount == 0:
            raise DatabaseError("Определение характеристики не найдено.")
        return count


def get_custom_attribute_definition_usage(
    definition_id: int, database_path: Path | str | None = None,
) -> list[dict]:
    return _fetchall(
        database_path,
        """SELECT m.id,m.manufacturer,m.model_name FROM custom_attributes a
           JOIN component_models m ON m.id=a.model_id WHERE a.definition_id=?
           ORDER BY m.manufacturer COLLATE NOCASE,m.model_name COLLATE NOCASE,m.id""",
        (definition_id,),
    )


def save_custom_attribute_value(
    model_id: int, definition_id: int, value: str | float | bool,
    database_path: Path | str | None = None,
) -> None:
    """Сохраняет значение определения для конкретного комплектующего."""
    with get_connection(database_path) as connection:
        definition = connection.execute(
            """SELECT d.* FROM custom_attribute_definitions d
               JOIN component_models m ON m.component_type=d.component_type
               WHERE d.id=? AND m.id=?""", (definition_id, model_id)
        ).fetchone()
        if definition is None:
            raise DatabaseError("Характеристика не относится к категории этого комплектующего.")
        kind = definition["value_type"]
        typed_values = _custom_attribute_values(kind, value)
        if kind == "enum":
            if value not in [row[0] for row in connection.execute(
                "SELECT value FROM custom_attribute_definition_options WHERE definition_id=?", (definition_id,)
            )]:
                raise DatabaseError("Выберите значение из допустимых вариантов.")
        existing = connection.execute(
            "SELECT id FROM custom_attributes WHERE model_id=? AND definition_id=?", (model_id, definition_id)
        ).fetchone()
        if existing:
            connection.execute(
                """UPDATE custom_attributes SET name=?,value_type=?,value_text=?,value_number=?,
                   value_boolean=?,value_enum=?,unit=? WHERE id=?""",
                (definition["name"], kind, *typed_values, definition["unit"], existing["id"]),
            )
            attribute_id = existing["id"]
        else:
            cursor = connection.execute(
                """INSERT INTO custom_attributes
                   (model_id,name,value_type,value_text,value_number,value_boolean,value_enum,unit,definition_id)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (model_id, definition["name"], kind, *typed_values, definition["unit"], definition_id),
            )
            attribute_id = cursor.lastrowid
        if kind == "enum":
            connection.execute("DELETE FROM custom_attribute_options WHERE attribute_id=?", (attribute_id,))
            options = connection.execute(
                "SELECT value,sort_order FROM custom_attribute_definition_options WHERE definition_id=?",
                (definition_id,),
            ).fetchall()
            connection.executemany(
                "INSERT INTO custom_attribute_options(attribute_id,value,sort_order) VALUES(?,?,?)",
                [(attribute_id, option["value"], option["sort_order"]) for option in options],
            )


def delete_custom_attribute_value(
    model_id: int, definition_id: int, database_path: Path | str | None = None,
) -> None:
    with get_connection(database_path) as connection:
        connection.execute(
            "DELETE FROM custom_attributes WHERE model_id=? AND definition_id=?",
            (model_id, definition_id),
        )


def list_component_custom_values(model_id: int, component_type: str, database_path: Path | str | None = None):
    """Возвращает определения категории со значениями этого комплектующего, если они есть."""
    return _fetchall(
        database_path,
        """SELECT d.id AS definition_id,d.component_type,d.name,d.value_type,d.unit,a.id AS attribute_id,
                  a.value_text,a.value_number,a.value_boolean,a.value_enum
           FROM custom_attribute_definitions d LEFT JOIN custom_attributes a
             ON a.definition_id=d.id AND a.model_id=?
           WHERE d.component_type=? ORDER BY d.name COLLATE NOCASE,d.id""",
        (model_id, component_type),
    )


def create_component_image(
    model_id: int,
    relative_path: str,
    *,
    caption: str | None = None,
    sort_order: int = 0,
    database_path: Path | str | None = None,
) -> int:
    """Сохраняет метаданные изображения по относительному пути."""
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts or ":" in relative_path:
        raise DatabaseError("Путь изображения должен быть относительным и оставаться внутри папки приложения.")
    return _execute(
        database_path,
        "INSERT INTO component_images (model_id, relative_path, caption, sort_order) VALUES (?, ?, ?, ?)",
        (model_id, relative_path.replace("\\", "/"), caption, sort_order),
    )


def get_component_images(model_id: int, database_path: Path | str | None = None):
    """Возвращает метаданные изображений модели в заданном порядке."""
    return _fetchall(
        database_path,
        "SELECT * FROM component_images WHERE model_id = ? ORDER BY sort_order, id",
        (model_id,),
    )


def save_component_image(
    component_id: int, image_data: bytes, mime_type: str,
    *, original_name: str | None = None, database_path: Path | str | None = None,
) -> None:
    """Создаёт или заменяет единственное подготовленное изображение комплектующего."""
    if not isinstance(image_data, (bytes, bytearray, memoryview)) or not image_data:
        raise DatabaseError("Данные изображения пусты или имеют неверный формат.")
    if len(image_data) > 15 * 1024 * 1024:
        raise DatabaseError("Подготовленное изображение превышает допустимый размер 15 МБ.")
    if mime_type not in {"image/jpeg", "image/png"}:
        raise DatabaseError("Поддерживаются только изображения JPEG и PNG после обработки.")
    with get_connection(database_path) as connection:
        if not connection.execute("SELECT 1 FROM component_models WHERE id=?", (component_id,)).fetchone():
            raise DatabaseError(f"Комплектующее {component_id} не найдено.")
        connection.execute(
            """INSERT INTO component_model_images(component_id,image_data,mime_type,original_name)
               VALUES(?,?,?,?) ON CONFLICT(component_id) DO UPDATE SET
               image_data=excluded.image_data,mime_type=excluded.mime_type,
               original_name=excluded.original_name,
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
            (component_id, sqlite3.Binary(image_data), mime_type, original_name),
        )


def get_component_image(component_id: int, database_path: Path | str | None = None):
    """Возвращает BLOB и метаданные основного изображения либо None."""
    return _fetchone(
        database_path,
        "SELECT image_data,mime_type,original_name,updated_at FROM component_model_images WHERE component_id=?",
        (component_id,),
    )


def delete_component_image(component_id: int, database_path: Path | str | None = None) -> None:
    """Удаляет изображение, не меняя саму запись комплектующего."""
    with get_connection(database_path) as connection:
        connection.execute("DELETE FROM component_model_images WHERE component_id=?", (component_id,))
