"""Загрузка снимка сборки через существующий слой доступа к данным."""

from pathlib import Path

from ..database import (
    DatabaseError, get_build, get_custom_attribute_definition_options,
    list_build_slots, list_component_custom_values,
)
from ..specifications import get_component_spec
from .models import (
    BuildSlotSnapshot, BuildSnapshot, ComponentSnapshot, CustomAttributeSnapshot,
)


def _custom_attribute_value(row: dict):
    return {
        "text": row["value_text"],
        "number": row["value_number"],
        "boolean": None if row["value_boolean"] is None else bool(row["value_boolean"]),
        "enum": row["value_enum"],
    }.get(row["value_type"])


def load_build_snapshot(
    build_id: int, database_path: Path | str | None = None,
) -> BuildSnapshot:
    """Загружает сборку, пустые слоты, спецификации и пользовательские значения."""
    build = get_build(build_id, database_path)
    if build is None:
        raise DatabaseError(f"Сборка {build_id} не найдена.")
    rows = list_build_slots(build_id, database_path)
    component_cache: dict[int, ComponentSnapshot] = {}
    slots: list[BuildSlotSnapshot] = []
    for row in rows:
        component_id = row["component_id"]
        component = None
        if component_id is not None:
            component_id = int(component_id)
            component = component_cache.get(component_id)
            if component is None:
                component_type = row["component_type"]
                raw_specifications = get_component_spec(component_id, database_path) or {}
                custom_values = list_component_custom_values(component_id, component_type, database_path)
                attributes = []
                for value in custom_values:
                    selected_value = _custom_attribute_value(value)
                    options = (
                        get_custom_attribute_definition_options(int(value["definition_id"]), database_path)
                        if value["value_type"] == "enum" else []
                    )
                    attributes.append(CustomAttributeSnapshot(
                        definition_id=int(value["definition_id"]),
                        name=value["name"],
                        value_type=value["value_type"],
                        value=selected_value,
                        unit=value["unit"],
                        options=tuple(options),
                    ))
                component = ComponentSnapshot(
                    component_id=component_id,
                    component_type=component_type,
                    manufacturer=row["manufacturer"],
                    model_name=row["model_name"],
                    status=row["status"],
                    specifications=raw_specifications,
                    custom_attributes=tuple(attributes),
                )
                component_cache[component_id] = component
        slots.append(BuildSlotSnapshot(
            slot_id=int(row["slot_id"]),
            category=row["category"],
            slot_index=int(row["slot_index"]),
            quantity=int(row["quantity"]),
            component=component,
        ))
    return BuildSnapshot(
        build_id=int(build["id"]),
        name=build["name"],
        description=build["description"],
        slots=tuple(slots),
    )
