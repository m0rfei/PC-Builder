"""Независимые от GUI и SQLite неизменяемые модели движка совместимости."""

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class CompatibilityStatus(str, Enum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


def freeze_value(value: Any) -> Any:
    """Рекурсивно делает контейнеры снимка только для чтения."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(freeze_value(item) for item in value)
    return value


@dataclass(frozen=True)
class CustomAttributeSnapshot:
    definition_id: int
    name: str
    value_type: str
    value: str | float | bool | None
    unit: str | None = None
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", tuple(self.options))


@dataclass(frozen=True)
class ComponentSnapshot:
    component_id: int
    component_type: str
    manufacturer: str
    model_name: str
    status: str
    specifications: Mapping[str, Any] = field(default_factory=dict)
    custom_attributes: tuple[CustomAttributeSnapshot, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "specifications", freeze_value(self.specifications))
        object.__setattr__(self, "custom_attributes", tuple(self.custom_attributes))


@dataclass(frozen=True)
class BuildSlotSnapshot:
    slot_id: int
    category: str
    slot_index: int
    quantity: int
    component: ComponentSnapshot | None


@dataclass(frozen=True)
class BuildSnapshot:
    build_id: int
    name: str
    description: str | None
    slots: tuple[BuildSlotSnapshot, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "slots", tuple(self.slots))

    @property
    def components(self) -> tuple[ComponentSnapshot, ...]:
        """Выбранные компоненты в порядке слотов; повторные выборы сохраняются."""
        return tuple(slot.component for slot in self.slots if slot.component is not None)

    @property
    def component_types(self) -> frozenset[str]:
        return frozenset(component.component_type for component in self.components)


@dataclass(frozen=True)
class CompatibilityResult:
    rule_id: str
    status: CompatibilityStatus
    message: str
    component_ids: tuple[int, ...] = ()
    reason: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str) or not self.rule_id.strip():
            raise ValueError("Результату требуется непустой устойчивый rule_id.")
        if not isinstance(self.status, CompatibilityStatus):
            raise TypeError("status должен быть значением CompatibilityStatus.")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("Результату требуется краткое сообщение.")
        object.__setattr__(self, "component_ids", tuple(dict.fromkeys(int(value) for value in self.component_ids)))
        object.__setattr__(self, "details", freeze_value(self.details))
