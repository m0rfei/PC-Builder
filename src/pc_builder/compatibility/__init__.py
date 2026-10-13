"""Движок и слой загрузки данных для будущих проверок совместимости."""

from .data import load_build_snapshot
from .engine import CompatibilityEngine, CompatibilityRule, RuleRegistryError
from .models import (
    BuildSnapshot, BuildSlotSnapshot, CompatibilityResult, CompatibilityStatus,
    ComponentSnapshot, CustomAttributeSnapshot,
)
from .rules import CpuCoolerSocketRule, CpuMotherboardSocketRule, RamMotherboardDdrRule, default_rules
from .service import check_build_compatibility

__all__ = [
    "BuildSnapshot", "BuildSlotSnapshot", "CompatibilityEngine", "CompatibilityResult",
    "CompatibilityRule", "CompatibilityStatus", "ComponentSnapshot",
    "CpuCoolerSocketRule", "CpuMotherboardSocketRule", "CustomAttributeSnapshot",
    "RamMotherboardDdrRule", "RuleRegistryError", "check_build_compatibility",
    "default_rules", "load_build_snapshot",
]
