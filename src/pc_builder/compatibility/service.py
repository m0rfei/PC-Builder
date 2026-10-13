"""Фасад для будущего вызова проверки из редактора сборки."""

from pathlib import Path
from typing import Iterable

from .data import load_build_snapshot
from .engine import CompatibilityEngine, CompatibilityRule
from .models import CompatibilityResult
from .rules import default_rules


def check_build_compatibility(
    build_id: int,
    rules: Iterable[CompatibilityRule] | None = None,
    database_path: Path | str | None = None,
) -> tuple[CompatibilityResult, ...]:
    """Загружает неизменяемый снимок и запускает переданные правила.

    Пустой результат означает, что применимого зарегистрированного правила пока нет;
    он не является подтверждением совместимости.
    """
    snapshot = load_build_snapshot(build_id, database_path)
    return CompatibilityEngine(default_rules() if rules is None else rules).check(snapshot)
