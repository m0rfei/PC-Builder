"""Чтение и безопасное изменение справочников PC-Builder."""

from pathlib import Path

from .catalog import COMPONENT_TYPE_LABELS
from .database import DatabaseError, VALID_COMPONENT_TYPES, get_connection
from .reference_data import INITIAL_MANUFACTURERS, INITIAL_SPEC_OPTIONS
from .schema_v3 import COMPONENT_SPEC_TABLES
from .specifications import ENUM_FIELDS, OPTION_TEXT_FIELDS, SPEC_FIELDS


LIST_REFERENCE_COLUMNS = {
    ("gpu", "power_connectors"): ("gpu_power_connectors", "connector_type"),
    ("cpu_cooler", "socket"): ("cpu_cooler_supported_sockets", "socket"),
    ("case", "form_factors_supported"): ("case_supported_form_factors", "form_factor"),
}

FIELD_LABELS = {
    "manufacturer": "Производитель",
    "chip_manufacturer": "Производитель GPU-чипа",
    "socket": "Сокет",
    "chipset": "Чипсет",
    "form_factor": "Форм-фактор",
    "ram_type": "Поколение памяти",
    "vram_type": "Тип видеопамяти",
    "pcie_version": "Версия PCIe",
    "vram_type": "Тип видеопамяти",
    "power_connectors": "Разъёмы питания видеокарты",
    "modularity": "Модульность БП",
    "efficiency_rating": "Сертификация БП",
    "interface_type": "Интерфейс",
    "protocol": "Протокол",
    "cooling_type": "Тип охлаждения GPU",
    "connector_type": "Тип подключения вентилятора",
    "form_factors_supported": "Поддерживаемые форм-факторы корпуса",
}


def _normalize(value: str) -> str:
    return " ".join(value.split())


def get_reference_fields(component_type: str) -> list[dict[str, str]]:
    """Возвращает реально используемые справочники выбранной категории."""
    if component_type not in VALID_COMPONENT_TYPES:
        raise DatabaseError(f"Неизвестная категория: {component_type!r}.")
    fields = {"manufacturer"}
    fields.update(field for kind, field in ENUM_FIELDS if kind == component_type)
    fields.update(field for field in OPTION_TEXT_FIELDS if field in SPEC_FIELDS[component_type])
    fields.update(field for kind, field in LIST_REFERENCE_COLUMNS if kind == component_type)
    return [
        {"field": field, "label": FIELD_LABELS.get(field, field)}
        for field in sorted(fields, key=lambda field: (field != "manufacturer", FIELD_LABELS.get(field, field).casefold()))
    ]


def _validate_reference(component_type: str, field: str) -> None:
    if component_type not in VALID_COMPONENT_TYPES:
        raise DatabaseError(f"Неизвестная категория: {component_type!r}.")
    if field not in {item["field"] for item in get_reference_fields(component_type)}:
        raise DatabaseError(f"Для категории «{COMPONENT_TYPE_LABELS[component_type]}» нет справочника «{field}».")


def _initial_values(component_type: str, field: str) -> set[str]:
    if field == "manufacturer":
        return set(INITIAL_MANUFACTURERS.get(component_type, ()))
    return set(INITIAL_SPEC_OPTIONS.get(component_type, {}).get(field, {}))


def _used_by(connection, component_type: str, field: str, value: str) -> list[dict]:
    if field == "manufacturer":
        rows = connection.execute(
            "SELECT id, manufacturer, model_name FROM component_models WHERE component_type=? AND trim(manufacturer)=? COLLATE NOCASE ORDER BY model_name,id",
            (component_type, value),
        ).fetchall()
    elif (component_type, field) in LIST_REFERENCE_COLUMNS:
        table, column = LIST_REFERENCE_COLUMNS[(component_type, field)]
        rows = connection.execute(
            f"""SELECT m.id,m.manufacturer,m.model_name FROM component_models m
                JOIN {table} s ON s.model_id=m.id WHERE m.component_type=? AND trim(s.{column})=? COLLATE NOCASE
                ORDER BY m.model_name,m.id""",
            (component_type, value),
        ).fetchall()
    else:
        table = COMPONENT_SPEC_TABLES[component_type]
        rows = connection.execute(
            f"""SELECT m.id,m.manufacturer,m.model_name FROM component_models m
                JOIN {table} s ON s.model_id=m.id WHERE m.component_type=? AND trim(s.{field})=? COLLATE NOCASE
                ORDER BY m.model_name,m.id""",
            (component_type, value),
        ).fetchall()
    return [dict(row) for row in rows]


def _list_reference_values(connection, component_type: str, field: str) -> list[dict]:
    raw_entries = []
    if field == "manufacturer":
        raw_entries.extend((row[0], row[0]) for row in connection.execute(
            "SELECT value FROM manufacturer_options WHERE component_type=?", (component_type,)
        ))
        for (value,) in connection.execute(
            "SELECT DISTINCT manufacturer FROM component_models WHERE component_type=?", (component_type,)
        ):
            if value:
                raw_entries.append((value, value))
    else:
        raw_entries.extend((row[0], row[1]) for row in connection.execute(
            "SELECT value,display_value FROM specification_options WHERE component_type=? AND field_name=?",
            (component_type, field),
        ))
        if (component_type, field) in LIST_REFERENCE_COLUMNS:
            table, column = LIST_REFERENCE_COLUMNS[(component_type, field)]
            query = f"SELECT DISTINCT {column} FROM {table}"
        else:
            table = COMPONENT_SPEC_TABLES[component_type]
            query = f"SELECT DISTINCT {field} FROM {table} WHERE {field} IS NOT NULL"
        for (value,) in connection.execute(query):
            raw_entries.append((value, value))

    # Старые БД могли содержать варианты, различающиеся только регистром или
    # пробелами. Показываем их одним пунктом; операции ниже обновляют все варианты.
    entries = {}
    for value, label in raw_entries:
        if value is not None:
            entries.setdefault(_normalize(value).casefold(), (value, label))

    initial = _initial_values(component_type, field)
    result = []
    for value, label in entries.values():
        used_by = _used_by(connection, component_type, field, value)
        result.append({
            "value": value, "label": label, "usage_count": len(used_by), "used_by": used_by,
            "origin": "Начальное" if value in initial else "Дополнительное или ранее сохранённое",
        })
    return sorted(result, key=lambda item: (item["label"].casefold(), item["value"].casefold()))


def list_reference_values(
    component_type: str, field: str, database_path: Path | str | None = None,
) -> list[dict]:
    """Возвращает значения, происхождение и использующие их комплектующие."""
    _validate_reference(component_type, field)
    with get_connection(database_path) as connection:
        return _list_reference_values(connection, component_type, field)


def _check_new_value(connection, component_type: str, field: str, value: str, *, old_value: str | None = None) -> str:
    value = _normalize(value)
    if not value:
        raise DatabaseError("Значение справочника не может быть пустым.")
    existing = _list_reference_values(connection, component_type, field)
    for item in existing:
        if old_value is not None and item["value"] == old_value:
            continue
        if _normalize(item["value"]).casefold() == value.casefold():
            raise DatabaseError(f"Значение «{item['label']}» уже есть в этом справочнике.")
    return value


def add_reference_value(
    component_type: str, field: str, value: str, database_path: Path | str | None = None,
) -> str:
    """Добавляет значение, ограничивая повторения с учётом регистра и пробелов."""
    _validate_reference(component_type, field)
    value = _normalize(value)
    if not value:
        raise DatabaseError("Значение справочника не может быть пустым.")
    with get_connection(database_path) as connection:
        _check_new_value(connection, component_type, field, value)
        if field == "manufacturer":
            connection.execute("INSERT INTO manufacturer_options(component_type,value) VALUES(?,?)", (component_type, value))
        else:
            connection.execute(
                "INSERT INTO specification_options(component_type,field_name,value,display_value) VALUES(?,?,?,?)",
                (component_type, field, value, value),
            )
    return value


def _apply_reference_update(connection, component_type: str, field: str, old_value: str, new_value: str) -> None:
    """Заменяет ссылки; объединяет повторы в табличных списках."""
    if field == "manufacturer":
        connection.execute(
            "UPDATE component_models SET manufacturer=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE component_type=? AND trim(manufacturer)=? COLLATE NOCASE",
            (new_value, component_type, old_value),
        )
        connection.execute(
            "DELETE FROM manufacturer_options WHERE component_type=? AND trim(value)=? COLLATE NOCASE", (component_type, old_value)
        )
        connection.execute(
            "INSERT OR IGNORE INTO manufacturer_options(component_type,value) VALUES(?,?)", (component_type, new_value)
        )
        return

    if (component_type, field) in LIST_REFERENCE_COLUMNS:
        table, column = LIST_REFERENCE_COLUMNS[(component_type, field)]
        if table == "gpu_power_connectors":
            connection.execute(
                f"""INSERT INTO {table}(model_id,{column},quantity)
                    SELECT model_id,?,quantity FROM {table} WHERE trim({column})=? COLLATE NOCASE
                    ON CONFLICT(model_id,{column}) DO UPDATE SET quantity=quantity+excluded.quantity""",
                (new_value, old_value),
            )
        else:
            connection.execute(
                f"INSERT OR IGNORE INTO {table}(model_id,{column}) SELECT model_id,? FROM {table} WHERE trim({column})=? COLLATE NOCASE",
                (new_value, old_value),
            )
        connection.execute(f"DELETE FROM {table} WHERE trim({column})=? COLLATE NOCASE", (old_value,))
    else:
        table = COMPONENT_SPEC_TABLES[component_type]
        connection.execute(f"UPDATE {table} SET {field}=? WHERE trim({field})=? COLLATE NOCASE", (new_value, old_value))

    # New option must exist before updating spec rows because SQLite triggers check it.
    connection.execute(
        "DELETE FROM specification_options WHERE component_type=? AND field_name=? AND trim(value)=? COLLATE NOCASE",
        (component_type, field, old_value),
    )
    connection.execute(
        "INSERT OR IGNORE INTO specification_options(component_type,field_name,value,display_value) VALUES(?,?,?,?)",
        (component_type, field, new_value, new_value),
    )


def rename_reference_value(
    component_type: str, field: str, old_value: str, new_value: str,
    database_path: Path | str | None = None,
) -> None:
    """Переименовывает пункт и его связи в одной транзакции."""
    _validate_reference(component_type, field)
    new_value = _normalize(new_value)
    if not new_value:
        raise DatabaseError("Новое значение не может быть пустым.")
    with get_connection(database_path) as connection:
        _check_new_value(connection, component_type, field, new_value, old_value=old_value)
        if old_value == new_value:
            return
        if field != "manufacturer":
            connection.execute(
                "INSERT OR IGNORE INTO specification_options(component_type,field_name,value,display_value) VALUES(?,?,?,?)",
                (component_type, field, new_value, new_value),
            )
        _apply_reference_update(connection, component_type, field, old_value, new_value)


def replace_reference_value(
    component_type: str, field: str, old_value: str, new_value: str,
    database_path: Path | str | None = None,
) -> None:
    """Заменяет используемое значение другим существующим пунктом того же справочника."""
    _validate_reference(component_type, field)
    if old_value == new_value:
        raise DatabaseError("Выберите другое значение для замены.")
    with get_connection(database_path) as connection:
        values = {item["value"] for item in _list_reference_values(connection, component_type, field)}
        if old_value not in values or new_value not in values:
            raise DatabaseError("Исходное и новое значения должны находиться в одном выбранном справочнике.")
        if not _used_by(connection, component_type, field, old_value):
            raise DatabaseError("Выбранное значение уже не используется комплектующими.")
        if field != "manufacturer":
            # Целевое значение уже зарегистрировано, триггерам будет разрешено обновление.
            pass
        _apply_reference_update(connection, component_type, field, old_value, new_value)


def delete_reference_value(
    component_type: str, field: str, value: str, database_path: Path | str | None = None,
) -> None:
    """Удаляет только неиспользуемое значение справочника."""
    _validate_reference(component_type, field)
    with get_connection(database_path) as connection:
        used_by = _used_by(connection, component_type, field, value)
        if used_by:
            raise DatabaseError(f"Значение «{value}» используется комплектующими ({len(used_by)}). Сначала замените его.")
        if field == "manufacturer":
            cursor = connection.execute(
                "DELETE FROM manufacturer_options WHERE component_type=? AND value=?", (component_type, value)
            )
        else:
            cursor = connection.execute(
                "DELETE FROM specification_options WHERE component_type=? AND field_name=? AND value=?",
                (component_type, field, value),
            )
        if cursor.rowcount == 0:
            raise DatabaseError(f"Значение «{value}» не найдено в справочнике.")

