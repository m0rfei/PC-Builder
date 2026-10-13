"""Типизированные спецификации моделей комплектующих."""

import math
from pathlib import Path
from typing import Any

from .database import DatabaseError, get_connection
from .schema_v3 import COMPONENT_SPEC_TABLES


SPEC_FIELDS = {
    "cpu": {"socket", "ram_type", "pcie_version", "cores", "threads", "base_clock_mhz", "boost_clock_mhz", "tdp_w", "has_integrated_gpu"},
    "motherboard": {"socket", "chipset", "form_factor", "ram_type", "ram_slots", "max_ram_gb", "max_ram_clock_mhz", "m2_slots", "sata_ports", "pcie_version"},
    "ram": {"ram_type", "capacity_gb", "frequency_mhz", "form_factor", "ecc"},
    "gpu": {"chip_manufacturer", "cooling_type", "vram_gb", "vram_type", "length_mm", "thickness_mm", "slot_width", "power_w", "recommended_psu_w"},
    "psu": {"rated_power_w", "modularity", "form_factor", "efficiency_rating", "pcie_6_2pin_count", "eps_4_4pin_count", "native_12vhpwr", "native_12v2x6", "sata_power_count"},
    "ssd": {"capacity_gb", "form_factor", "interface_type", "protocol", "pcie_version", "power_w"},
    "hdd": {"capacity_gb", "form_factor", "interface_type", "power_w"},
    "cpu_cooler": {"height_mm", "power_w"},
    "case_fan": {"size_mm", "thickness_mm", "connector_type", "power_w", "max_rpm", "lighting"},
    "case": {"max_gpu_length_mm", "max_cpu_cooler_height_mm", "max_psu_length_mm", "drive_2_5_bays", "drive_3_5_bays"},
}

LIST_FIELDS = {
    "gpu": {"power_connectors"},
    "cpu_cooler": {"supported_sockets"},
    "case": {"form_factors_supported", "radiator_support"},
    "motherboard": {"supported_ram_types"},
}

INTEGER_FIELDS = {
    "cores", "threads", "ram_slots", "m2_slots", "sata_ports", "pcie_6_2pin_count",
    "eps_4_4pin_count", "sata_power_count", "max_rpm", "drive_2_5_bays", "drive_3_5_bays",
}
POSITIVE_FIELDS = {"cores", "threads", "capacity_gb", "frequency_mhz", "base_clock_mhz", "boost_clock_mhz", "max_ram_gb", "max_ram_clock_mhz", "vram_gb", "size_mm"}
NON_NEGATIVE_FIELDS = {
    "ram_slots", "m2_slots", "sata_ports", "length_mm", "thickness_mm", "slot_width", "power_w",
    "recommended_psu_w", "rated_power_w", "pcie_6_2pin_count", "eps_4_4pin_count", "sata_power_count",
    "height_mm", "max_rpm", "max_gpu_length_mm", "max_cpu_cooler_height_mm", "max_psu_length_mm",
    "drive_2_5_bays", "drive_3_5_bays", "tdp_w",
}
BOOLEAN_FIELDS = {"has_integrated_gpu", "native_12vhpwr", "native_12v2x6", "ecc", "lighting"}
TEXT_FIELDS = {"socket", "chipset"}
OPTION_TEXT_FIELDS = {"socket", "chipset", "chip_manufacturer"}

ENUM_FIELDS = {
    ("motherboard", "form_factor"): {"atx", "micro_atx", "mini_itx", "extended_atx", "mini_dtx", "dtx", "ssi_eeb"},
    ("motherboard", "ram_type"): {"ddr2", "ddr3", "ddr3l", "ddr4", "ddr5"},
    ("ram", "ram_type"): {"ddr", "ddr2", "ddr3", "ddr3l", "ddr4", "ddr5"},
    ("cpu", "ram_type"): {"ddr", "ddr2", "ddr3", "ddr3l", "ddr4", "ddr5"},
    ("ram", "form_factor"): {"dimm", "so_dimm", "micro_dimm", "udimm", "rdimm", "lrdimm"},
    ("gpu", "vram_type"): {"gddr3", "gddr5", "gddr5x", "gddr6", "gddr6x", "gddr7", "hbm", "hbm2", "hbm2e", "hbm3", "hbm3e"},
    ("gpu", "cooling_type"): {"air", "passive"},
    ("psu", "form_factor"): {"atx", "sfx", "sfx_l", "tfx", "flex_atx", "1u", "2u", "proprietary"},
    ("psu", "modularity"): {"modular", "semi_modular", "non_modular"},
    ("psu", "efficiency_rating"): {"80_plus", "80_plus_bronze", "80_plus_silver", "80_plus_gold", "80_plus_platinum", "80_plus_titanium"},
    ("ssd", "form_factor"): {"2_5_in", "m2_2230", "m2_2242", "m2_2260", "m2_2280", "m2_22110", "u2", "u3", "add_in_card"},
    ("ssd", "interface_type"): {"sata", "pcie", "pcie_nvme"},
    ("ssd", "protocol"): {"nvme"},
    ("hdd", "form_factor"): {"2_5_in", "3_5_in"},
    ("hdd", "interface_type"): {"sata", "sas", "ide"},
    ("case_fan", "connector_type"): {"3_pin", "4_pin_pwm", "molex_4pin", "sata_power", "proprietary", "other"},
}
ENUM_FIELDS.update({
    (component_type, "pcie_version"): {"1.0", "2.0", "3.0", "4.0", "5.0", "6.0"}
    for component_type in ("motherboard", "ssd", "cpu")
})

FORM_FACTORS_SUPPORTED = {"atx", "micro_atx", "mini_itx", "extended_atx", "mini_dtx", "dtx", "ssi_eeb"}
GPU_CONNECTOR_TYPES = {"pcie_6pin", "pcie_8pin", "12vhpwr", "12v_2x6"}
LEGACY_MOTHERBOARD_RAM_TYPES = frozenset({"ddr2", "ddr3", "ddr3l", "ddr4", "ddr5"})


def _legacy_motherboard_ram_type(values: list[str] | tuple[str, ...]) -> str | None:
    """Returns a value accepted by the old scalar column, without constraining the new list."""
    return next((value for value in values if value in LEGACY_MOTHERBOARD_RAM_TYPES), None)


def _model_type(connection, model_id: int) -> str:
    row = connection.execute(
        "SELECT component_type FROM component_models WHERE id = ?", (model_id,)
    ).fetchone()
    if row is None:
        raise DatabaseError(f"Модель с идентификатором {model_id} не найдена.")
    component_type = row[0]
    if component_type not in COMPONENT_SPEC_TABLES:
        raise DatabaseError(f"Для неизвестного типа модели «{component_type}» спецификации не поддерживаются.")
    return component_type


def _validate_values(component_type: str, values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed = SPEC_FIELDS[component_type] | LIST_FIELDS.get(component_type, set())
    unknown = set(values) - allowed
    if unknown:
        raise DatabaseError(f"Для типа «{component_type}» неизвестные поля спецификаций: {', '.join(sorted(unknown))}.")

    scalars = {key: value for key, value in values.items() if key not in LIST_FIELDS.get(component_type, set())}
    lists = {key: value for key, value in values.items() if key in LIST_FIELDS.get(component_type, set())}
    for name, value in scalars.items():
        if value is None:
            continue
        if name in BOOLEAN_FIELDS:
            valid = isinstance(value, bool)
        elif name in INTEGER_FIELDS:
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif name in POSITIVE_FIELDS or name in NON_NEGATIVE_FIELDS:
            valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        elif name in TEXT_FIELDS:
            valid = isinstance(value, str) and bool(value.strip())
        elif (component_type, name) in ENUM_FIELDS:
            valid = isinstance(value, str) and bool(value.strip())
        elif name in OPTION_TEXT_FIELDS:
            valid = isinstance(value, str) and bool(value.strip())
        else:
            valid = False
        if not valid:
            raise DatabaseError(f"Недопустимое значение для характеристики «{name}»: {value!r}.")
        if name in POSITIVE_FIELDS and value <= 0:
            raise DatabaseError(f"Характеристика «{name}» должна быть больше нуля.")
        if name in NON_NEGATIVE_FIELDS and value < 0:
            raise DatabaseError(f"Характеристика «{name}» не может быть отрицательной.")

    for name, value in lists.items():
        if component_type == "gpu" and name == "power_connectors":
            if not isinstance(value, dict):
                raise DatabaseError("power_connectors должен быть словарём вида {тип_разъёма: количество}.")
            if any(not isinstance(kind, str) or not kind.strip() or not isinstance(count, int) or isinstance(count, bool) or count <= 0
                   for kind, count in value.items()):
                raise DatabaseError("Недопустимый тип или количество разъёма питания видеокарты.")
        else:
            if not isinstance(value, (list, tuple)):
                raise DatabaseError(f"Характеристика «{name}» должна быть списком значений.")
            if name in {"supported_sockets", "supported_ram_types"}:
                valid = all(isinstance(item, str) and bool(item.strip()) for item in value)
                duplicate = valid and len(value) != len(set(value))
            elif name == "form_factors_supported":
                valid = all(isinstance(item, str) and bool(item.strip()) for item in value)
                duplicate = valid and len(value) != len(set(value))
            elif name == "radiator_support":
                valid = all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value)
                duplicate = valid and len(value) != len(set(value))
            else:
                valid = False
                duplicate = False
            if duplicate:
                raise DatabaseError(f"Список «{name}» содержит повторы.")
            if not valid:
                raise DatabaseError(f"Недопустимые значения в списке «{name}».")
    return scalars, lists


def _save_lists(connection, component_type: str, model_id: int, lists: dict[str, Any]) -> None:
    for name, values in lists.items():
        if name == "power_connectors":
            connection.execute("DELETE FROM gpu_power_connectors WHERE model_id = ?", (model_id,))
            connection.executemany(
                "INSERT INTO gpu_power_connectors (model_id, connector_type, quantity) VALUES (?, ?, ?)",
                [(model_id, kind, count) for kind, count in values.items()],
            )
        elif name == "supported_sockets":
            connection.execute("DELETE FROM cpu_cooler_supported_sockets WHERE model_id = ?", (model_id,))
            connection.executemany(
                "INSERT INTO cpu_cooler_supported_sockets (model_id, socket) VALUES (?, ?)",
                [(model_id, socket) for socket in values],
            )
        elif name == "supported_ram_types":
            connection.execute("DELETE FROM motherboard_supported_ram_types WHERE model_id = ?", (model_id,))
            connection.executemany(
                "INSERT INTO motherboard_supported_ram_types (model_id, ram_type) VALUES (?, ?)",
                [(model_id, value) for value in values],
            )
        elif name == "form_factors_supported":
            connection.execute("DELETE FROM case_supported_form_factors WHERE model_id = ?", (model_id,))
            connection.executemany(
                "INSERT INTO case_supported_form_factors (model_id, form_factor) VALUES (?, ?)",
                [(model_id, form_factor) for form_factor in values],
            )
        elif name == "radiator_support":
            connection.execute("DELETE FROM case_radiator_support WHERE model_id = ?", (model_id,))
            connection.executemany(
                "INSERT INTO case_radiator_support (model_id, size_mm) VALUES (?, ?)",
                [(model_id, size_mm) for size_mm in values],
            )


def _save_options(connection, component_type: str, scalars: dict[str, Any], lists: dict[str, Any]) -> None:
    """Сохраняет введённые справочные значения, чтобы их можно было выбирать позже."""
    option_fields = {name for (kind, name) in ENUM_FIELDS if kind == component_type} | OPTION_TEXT_FIELDS
    for field, value in scalars.items():
        if field in option_fields and value is not None:
            connection.execute(
                "INSERT OR IGNORE INTO specification_options(component_type, field_name, value, display_value) VALUES (?, ?, ?, ?)",
                (component_type, field, value, value),
            )
    list_options = {
        "power_connectors": lists.get("power_connectors", {}).keys(),
        "supported_sockets": lists.get("supported_sockets", []),
        "supported_ram_types": lists.get("supported_ram_types", []),
        "form_factors_supported": lists.get("form_factors_supported", []),
    }
    for field, values in list_options.items():
        for value in values:
            option_field = "socket" if field == "supported_sockets" else (
                "ram_type" if field == "supported_ram_types" else field
            )
            connection.execute(
                "INSERT OR IGNORE INTO specification_options(component_type, field_name, value, display_value) VALUES (?, ?, ?, ?)",
                (component_type, option_field, value, value),
            )


def list_specification_options(
    component_type: str, field_name: str, database_path: Path | str | None = None
) -> list[dict[str, str]]:
    """Возвращает справочные значения, включая добавленные пользователем."""
    with get_connection(database_path) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT value, display_value FROM specification_options WHERE component_type=? AND field_name=? ORDER BY sort_order, display_value COLLATE NOCASE, value",
            (component_type, field_name),
        ).fetchall()]


def create_component_spec(
    model_id: int,
    *,
    database_path: Path | str | None = None,
    **specifications: Any,
) -> None:
    """Создаёт типизированную спецификацию для модели её собственного типа."""
    with get_connection(database_path) as connection:
        component_type = _model_type(connection, model_id)
        scalars, lists = _validate_values(component_type, specifications)
        if component_type == "motherboard":
            if "supported_ram_types" not in lists and scalars.get("ram_type") is not None:
                lists["supported_ram_types"] = [scalars["ram_type"]]
            if "supported_ram_types" in lists:
                supported = lists["supported_ram_types"]
                scalars["ram_type"] = _legacy_motherboard_ram_type(supported)
        table = COMPONENT_SPEC_TABLES[component_type]
        _save_options(connection, component_type, scalars, lists)
        columns = ["model_id", *scalars]
        placeholders = ", ".join("?" for _ in columns)
        connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            (model_id, *scalars.values()),
        )
        _save_lists(connection, component_type, model_id, lists)


def get_component_spec(model_id: int, database_path: Path | str | None = None) -> dict[str, Any] | None:
    """Возвращает спецификацию модели, включая связанные списки, или None."""
    with get_connection(database_path) as connection:
        component_type = _model_type(connection, model_id)
        table = COMPONENT_SPEC_TABLES[component_type]
        row = connection.execute(f"SELECT * FROM {table} WHERE model_id = ?", (model_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        for boolean_field in BOOLEAN_FIELDS.intersection(result):
            if result[boolean_field] is not None:
                result[boolean_field] = bool(result[boolean_field])
        if component_type == "gpu":
            result["power_connectors"] = {
                item["connector_type"]: item["quantity"] for item in connection.execute(
                    "SELECT connector_type, quantity FROM gpu_power_connectors WHERE model_id = ? ORDER BY connector_type",
                    (model_id,),
                ).fetchall()
            }
        elif component_type == "cpu_cooler":
            result["supported_sockets"] = [item[0] for item in connection.execute(
                "SELECT socket FROM cpu_cooler_supported_sockets WHERE model_id = ? ORDER BY socket", (model_id,)
            ).fetchall()]
        elif component_type == "case":
            result["form_factors_supported"] = [item[0] for item in connection.execute(
                "SELECT form_factor FROM case_supported_form_factors WHERE model_id = ? ORDER BY form_factor", (model_id,)
            ).fetchall()]
            result["radiator_support"] = [item[0] for item in connection.execute(
                "SELECT size_mm FROM case_radiator_support WHERE model_id = ? ORDER BY size_mm", (model_id,)
            ).fetchall()]
        elif component_type == "motherboard":
            result["supported_ram_types"] = [item[0] for item in connection.execute(
                "SELECT ram_type FROM motherboard_supported_ram_types WHERE model_id = ? ORDER BY ram_type COLLATE NOCASE",
                (model_id,),
            ).fetchall()]
        return result


def update_component_spec(
    model_id: int,
    *,
    database_path: Path | str | None = None,
    **changes: Any,
) -> None:
    """Изменяет переданные поля спецификации; списки заменяются целиком."""
    if not changes:
        raise DatabaseError("Укажите характеристики для изменения.")
    with get_connection(database_path) as connection:
        component_type = _model_type(connection, model_id)
        scalars, lists = _validate_values(component_type, changes)
        if component_type == "motherboard":
            if "supported_ram_types" in lists:
                supported = lists["supported_ram_types"]
                scalars["ram_type"] = _legacy_motherboard_ram_type(supported)
            elif "ram_type" in scalars:
                # Сохранение прежнего API: scalar-ввод задаёт единственный тип.
                lists["supported_ram_types"] = [scalars["ram_type"]] if scalars["ram_type"] else []
                scalars["ram_type"] = _legacy_motherboard_ram_type(lists["supported_ram_types"])
        table = COMPONENT_SPEC_TABLES[component_type]
        _save_options(connection, component_type, scalars, lists)
        if connection.execute(f"SELECT 1 FROM {table} WHERE model_id = ?", (model_id,)).fetchone() is None:
            raise DatabaseError(f"Для модели {model_id} спецификация ещё не создана.")
        if scalars:
            assignments = ", ".join(f"{field} = ?" for field in scalars)
            connection.execute(
                f"UPDATE {table} SET {assignments} WHERE model_id = ?",
                (*scalars.values(), model_id),
            )
        _save_lists(connection, component_type, model_id, lists)
