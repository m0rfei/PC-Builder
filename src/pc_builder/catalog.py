"""Запросы каталога и операции над комплектующими для интерфейса."""

from pathlib import Path

from .database import (
    DatabaseError,
    VALID_COMPONENT_TYPES,
    archive_component,
    create_component,
    delete_component,
    get_component,
    list_components,
    restore_component,
)
from .database import (
    create_custom_attribute,
    get_custom_attributes,
    get_custom_attribute_options,
    get_custom_attribute_definition_options,
)
from .specifications import create_component_spec, get_component_spec


COMPONENT_TYPE_LABELS = {
    "motherboard": "Материнская плата",
    "cpu": "Процессор",
    "ram": "Оперативная память",
    "gpu": "Видеокарта",
    "psu": "Блок питания",
    "ssd": "SSD",
    "hdd": "HDD",
    "cpu_cooler": "Кулер процессора",
    "case_fan": "Корпусный вентилятор",
    "case": "Корпус",
}


def list_owned_models(
    *, search: str = "", component_type: str | None = None,
    descending: bool = False, database_path: Path | str | None = None,
) -> list[dict]:
    """Возвращает активные комплектующие с фильтрами и сортировкой каталога."""
    if component_type is not None and component_type not in VALID_COMPONENT_TYPES:
        raise DatabaseError(f"Неизвестный тип комплектующего: {component_type!r}.")
    rows = list_components(
        status="owned", component_type=component_type,
        search=search.strip(), database_path=database_path,
    )
    rows.sort(key=lambda row: (row["model_name"].casefold(), row["manufacturer"].casefold(), row["id"]))
    if descending:
        # Сортировка по названию в обратном порядке; вторичные поля остаются стабильными.
        rows.sort(key=lambda row: row["model_name"].casefold(), reverse=True)
    return rows


def list_archived_components(database_path: Path | str | None = None) -> list[dict]:
    """Возвращает архивные комплектующие, отсортированные по дате архивации."""
    return list_components(status="archived", database_path=database_path)


def duplicate_component(component_id: int, database_path: Path | str | None = None) -> int:
    """Создаёт активную копию комплектующего с характеристиками, но без старой истории."""
    source = get_component(component_id, database_path)
    if source is None:
        raise DatabaseError(f"Комплектующее {component_id} не найдено.")
    duplicate_id = create_component(
        source["component_type"], source["manufacturer"], source["model_name"],
        part_number=source["part_number"], description=source["description"],
        notes=source["notes"], database_path=database_path,
    )
    try:
        spec = get_component_spec(component_id, database_path)
        if spec is not None:
            spec.pop("model_id", None)
            create_component_spec(duplicate_id, database_path=database_path, **spec)
        for attribute in get_custom_attributes(component_id, database_path):
            value_column = {
                "text": "value_text", "number": "value_number",
                "boolean": "value_boolean", "enum": "value_enum",
            }[attribute["value_type"]]
            value = attribute[value_column]
            if attribute["value_type"] == "boolean":
                value = bool(value)
            create_custom_attribute(
                duplicate_id, attribute["name"], attribute["value_type"], value,
                unit=attribute["unit"],
                enum_options=(
                    get_custom_attribute_definition_options(attribute["definition_id"], database_path)
                    if attribute.get("definition_id") is not None and attribute["value_type"] == "enum"
                    else get_custom_attribute_options(attribute["id"], database_path)
                    if attribute["value_type"] == "enum"
                    else None
                ),
                definition_id=attribute.get("definition_id"),
                database_path=database_path,
            )
    except Exception:
        # Не оставляем пустой или частично скопированный дубликат при ошибке копирования.
        delete_component(duplicate_id, database_path)
        raise
    return duplicate_id


__all__ = [
    "COMPONENT_TYPE_LABELS", "list_owned_models", "list_archived_components",
    "duplicate_component", "archive_component", "restore_component", "delete_component",
]
