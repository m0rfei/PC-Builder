"""Реестр независимых правил и запуск применимых проверок."""

from typing import Protocol, Sequence

from .models import BuildSnapshot, CompatibilityResult, CompatibilityStatus


class CompatibilityRule(Protocol):
    """Контракт правила; правило читает снимок и возвращает единый результат."""

    @property
    def rule_id(self) -> str:
        """Устойчивый идентификатор, например ``cpu.socket.motherboard``."""

    @property
    def component_types(self) -> frozenset[str]:
        """Типы комплектующих, к которым относится правило."""

    def applies_to(self, build: BuildSnapshot) -> bool:
        """Определяет, нужно ли запускать правило для данного снимка."""

    def evaluate(self, build: BuildSnapshot) -> CompatibilityResult | Sequence[CompatibilityResult]:
        """Проверяет данные без изменения снимка и возвращает один или несколько результатов."""


class RuleRegistryError(ValueError):
    """Ошибка регистрации правил совместимости."""


class CompatibilityEngine:
    """Запускает зарегистрированные правила в стабильном порядке идентификаторов."""

    def __init__(self, rules=()):
        self._rules: dict[str, CompatibilityRule] = {}
        for rule in rules:
            self.register(rule)

    @property
    def rules(self) -> tuple[CompatibilityRule, ...]:
        return tuple(self._rules[key] for key in sorted(self._rules))

    def register(self, rule: CompatibilityRule) -> None:
        rule_id = getattr(rule, "rule_id", None)
        component_types = getattr(rule, "component_types", None)
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise RuleRegistryError("У правила должен быть непустой rule_id.")
        if rule_id in self._rules:
            raise RuleRegistryError(f"Правило с идентификатором {rule_id!r} уже зарегистрировано.")
        if not isinstance(component_types, (set, frozenset, tuple)) or not component_types:
            raise RuleRegistryError("У правила должен быть указан непустой набор component_types.")
        if not callable(getattr(rule, "applies_to", None)) or not callable(getattr(rule, "evaluate", None)):
            raise RuleRegistryError("Правило должно реализовать applies_to() и evaluate().")
        self._rules[rule_id] = rule

    def check(self, build: BuildSnapshot) -> tuple[CompatibilityResult, ...]:
        results: list[CompatibilityResult] = []
        for rule in self.rules:
            try:
                if not rule.applies_to(build):
                    continue
                outcome = rule.evaluate(build)
            except Exception as error:
                # Сбой отдельного правила виден пользователю/вызывающему коду,
                # но не мешает запуску остальных независимых правил.
                results.append(CompatibilityResult(
                    rule_id=rule.rule_id,
                    status=CompatibilityStatus.UNKNOWN,
                    message="Проверку не удалось выполнить.",
                    reason=f"{type(error).__name__}: {error}",
                    details={"error_type": type(error).__name__},
                ))
                continue
            rule_results: Sequence[CompatibilityResult]
            if isinstance(outcome, CompatibilityResult):
                rule_results = (outcome,)
            elif isinstance(outcome, (tuple, list)) and all(
                isinstance(result, CompatibilityResult) for result in outcome
            ):
                rule_results = outcome
            else:
                error = TypeError(f"Правило {rule.rule_id!r} вернуло неподдерживаемый результат.")
                results.append(CompatibilityResult(
                    rule_id=rule.rule_id,
                    status=CompatibilityStatus.UNKNOWN,
                    message="Результат правила имеет неверный формат.",
                    reason=str(error),
                    details={"error_type": type(error).__name__},
                ))
                continue
            for result in rule_results:
                if result.rule_id != rule.rule_id:
                    error = ValueError(
                        f"Идентификатор результата {result.rule_id!r} не совпадает с правилом {rule.rule_id!r}."
                    )
                    results.append(CompatibilityResult(
                        rule_id=rule.rule_id,
                        status=CompatibilityStatus.UNKNOWN,
                        message="Идентификатор результата правила некорректен.",
                        reason=str(error),
                        details={"error_type": type(error).__name__},
                    ))
                    continue
                results.append(result)
        return tuple(results)
