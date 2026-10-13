"""Первые базовые проверки совместимости по явно сохранённым характеристикам."""

from .models import BuildSnapshot, CompatibilityResult, CompatibilityStatus, ComponentSnapshot


def _text_value(component: ComponentSnapshot, field: str) -> tuple[str | None, str | None]:
    value = component.specifications.get(field)
    if value is None or value == "":
        return None, f"У комплектующего не заполнена характеристика «{field}»."
    if not isinstance(value, str):
        return None, f"Характеристика «{field}» имеет неожиданный формат {type(value).__name__}; ожидался текст."
    normalized = value.strip()
    if not normalized:
        return None, f"Характеристика «{field}» не заполнена."
    return normalized, None


def _components(build: BuildSnapshot, component_type: str) -> list[ComponentSnapshot]:
    return [item.component for item in build.slots
            if item.component is not None and item.component.component_type == component_type]


class CpuMotherboardSocketRule:
    rule_id = "cpu.motherboard.socket"
    component_types = frozenset({"cpu", "motherboard"})

    def applies_to(self, build: BuildSnapshot) -> bool:
        return bool(self.component_types & build.component_types)

    def evaluate(self, build: BuildSnapshot) -> CompatibilityResult | tuple[CompatibilityResult, ...]:
        cpus = _components(build, "cpu")
        boards = _components(build, "motherboard")
        if not cpus or not boards:
            missing = []
            if not cpus:
                missing.append("процессор")
            if not boards:
                missing.append("материнская плата")
            return CompatibilityResult(
                self.rule_id, CompatibilityStatus.UNKNOWN,
                "Недостаточно данных для проверки сокета.",
                tuple(item.component_id for item in (*cpus, *boards)),
                "Не выбрано: " + ", ".join(missing) + ".",
            )
        results = []
        for cpu in cpus:
            for board in boards:
                cpu_socket, cpu_error = _text_value(cpu, "socket")
                board_socket, board_error = _text_value(board, "socket")
                if cpu_error or board_error:
                    reasons = [error for error in (cpu_error, board_error) if error]
                    results.append(CompatibilityResult(
                        self.rule_id, CompatibilityStatus.UNKNOWN,
                        "Сокеты CPU и материнской платы не удалось сопоставить.",
                        (cpu.component_id, board.component_id), "; ".join(reasons),
                        {"cpu_socket": cpu.specifications.get("socket"),
                         "motherboard_socket": board.specifications.get("socket")},
                    ))
                elif cpu_socket.casefold() == board_socket.casefold():
                    results.append(CompatibilityResult(
                        self.rule_id, CompatibilityStatus.COMPATIBLE,
                        "Сокеты процессора и материнской платы совпадают.",
                        (cpu.component_id, board.component_id),
                        details={"socket": cpu_socket},
                    ))
                else:
                    results.append(CompatibilityResult(
                        self.rule_id, CompatibilityStatus.INCOMPATIBLE,
                        "Сокеты процессора и материнской платы различаются.",
                        (cpu.component_id, board.component_id),
                        f"CPU: {cpu_socket}; материнская плата: {board_socket}.",
                        {"cpu_socket": cpu_socket, "motherboard_socket": board_socket},
                    ))
        # Для ожидаемой конфигурации CPU и платы по одному будет один результат.
        # Если данные старой сборки содержат несколько таких слотов, сохраняем результат каждой пары.
        return results[0] if len(results) == 1 else tuple(results)


class RamMotherboardDdrRule:
    rule_id = "ram.motherboard.ddr"
    component_types = frozenset({"ram", "motherboard"})

    def applies_to(self, build: BuildSnapshot) -> bool:
        return bool(self.component_types & build.component_types)

    def evaluate(self, build: BuildSnapshot) -> CompatibilityResult | tuple[CompatibilityResult, ...]:
        modules = [
            slot for slot in build.slots
            if slot.component is not None and slot.component.component_type == "ram"
        ]
        boards = _components(build, "motherboard")
        if not modules:
            return CompatibilityResult(
                self.rule_id, CompatibilityStatus.UNKNOWN,
                "Нет выбранных модулей памяти для проверки.",
                tuple(board.component_id for board in boards),
                "Добавьте модуль оперативной памяти в сборку.",
            )
        if not boards:
            return tuple(CompatibilityResult(
                self.rule_id, CompatibilityStatus.UNKNOWN,
                "Тип DDR модуля нельзя проверить без материнской платы.",
                (slot.component.component_id,),
                "Материнская плата не выбрана.",
                {"ram_slot_id": slot.slot_id},
            ) for slot in modules)

        results = []
        for slot in modules:
            module = slot.component
            module_type, module_error = _text_value(module, "ram_type")
            for board in boards:
                supported, board_error = _supported_board_ram_types(board)
                if module_error or board_error:
                    reasons = [error for error in (module_error, board_error) if error]
                    results.append(CompatibilityResult(
                        self.rule_id, CompatibilityStatus.UNKNOWN,
                        "Тип DDR памяти и поддержка платы не удалось сопоставить.",
                        (module.component_id, board.component_id), "; ".join(reasons),
                        {"ram_slot_id": slot.slot_id},
                    ))
                elif module_type.casefold() in {value.casefold() for value in supported}:
                    results.append(CompatibilityResult(
                        self.rule_id, CompatibilityStatus.COMPATIBLE,
                        "Тип DDR модуля поддерживается материнской платой.",
                        (module.component_id, board.component_id),
                        details={"ram_type": module_type, "supported_ram_types": supported,
                                 "ram_slot_id": slot.slot_id},
                    ))
                else:
                    results.append(CompatibilityResult(
                        self.rule_id, CompatibilityStatus.INCOMPATIBLE,
                        "Тип DDR модуля не входит в список поддерживаемых платой.",
                        (module.component_id, board.component_id),
                        f"Модуль: {module_type}; плата поддерживает: {', '.join(supported)}.",
                        {"ram_type": module_type, "supported_ram_types": supported,
                         "ram_slot_id": slot.slot_id},
                    ))
        return results[0] if len(results) == 1 else tuple(results)


def _supported_board_ram_types(board: ComponentSnapshot) -> tuple[tuple[str, ...], str | None]:
    """Читает типизированный список при его наличии и поддерживает текущий scalar ram_type."""
    if "supported_ram_types" in board.specifications:
        value = board.specifications["supported_ram_types"]
        if not isinstance(value, (list, tuple, set, frozenset)):
            return (), "Список supported_ram_types имеет неожиданный формат."
        if not value:
            return (), "У материнской платы не указаны поддерживаемые типы памяти."
        if any(not isinstance(item, str) or not item.strip() for item in value):
            return (), "Список поддерживаемых типов памяти содержит значение неверного формата."
        return tuple(sorted((item.strip() for item in value), key=str.casefold)), None
    value, error = _text_value(board, "ram_type")
    return ((value,) if value else ()), error


class CpuCoolerSocketRule:
    rule_id = "cpu.cooler.socket"
    component_types = frozenset({"cpu", "cpu_cooler"})

    def applies_to(self, build: BuildSnapshot) -> bool:
        return bool(self.component_types & build.component_types)

    def evaluate(self, build: BuildSnapshot) -> CompatibilityResult | tuple[CompatibilityResult, ...]:
        cpus = _components(build, "cpu")
        coolers = _components(build, "cpu_cooler")
        if not cpus or not coolers:
            missing = []
            if not cpus:
                missing.append("процессор")
            if not coolers:
                missing.append("кулер процессора")
            return CompatibilityResult(
                self.rule_id, CompatibilityStatus.UNKNOWN,
                "Недостаточно данных для проверки сокета кулера.",
                tuple(item.component_id for item in (*cpus, *coolers)),
                "Не выбрано: " + ", ".join(missing) + ".",
            )
        results = []
        for cpu in cpus:
            cpu_socket, cpu_error = _text_value(cpu, "socket")
            for cooler in coolers:
                supported = cooler.specifications.get("supported_sockets")
                cooler_error = None
                if supported is None or supported == () or supported == []:
                    cooler_error = "У кулера не указаны поддерживаемые сокеты."
                elif not isinstance(supported, (list, tuple, set, frozenset)):
                    cooler_error = "Список сокетов кулера имеет неожиданный формат."
                elif any(not isinstance(item, str) or not item.strip() for item in supported):
                    cooler_error = "Список сокетов кулера содержит значение неверного формата."
                supported_values = tuple(item.strip() for item in supported) if not cooler_error else ()
                if cpu_error or cooler_error:
                    reasons = [error for error in (cpu_error, cooler_error) if error]
                    results.append(CompatibilityResult(
                        self.rule_id, CompatibilityStatus.UNKNOWN,
                        "Сокет процессора и поддержка кулера не удалось сопоставить.",
                        (cpu.component_id, cooler.component_id), "; ".join(reasons),
                        {"supported_sockets": supported_values},
                    ))
                elif cpu_socket.casefold() in {item.casefold() for item in supported_values}:
                    results.append(CompatibilityResult(
                        self.rule_id, CompatibilityStatus.COMPATIBLE,
                        "Кулер поддерживает сокет установленного процессора.",
                        (cpu.component_id, cooler.component_id),
                        details={"cpu_socket": cpu_socket, "supported_sockets": supported_values},
                    ))
                else:
                    results.append(CompatibilityResult(
                        self.rule_id, CompatibilityStatus.INCOMPATIBLE,
                        "Кулер не указан как совместимый с сокетом процессора.",
                        (cpu.component_id, cooler.component_id),
                        f"Сокет CPU: {cpu_socket}; кулер поддерживает: {', '.join(supported_values)}.",
                        {"cpu_socket": cpu_socket, "supported_sockets": supported_values},
                    ))
        return results[0] if len(results) == 1 else tuple(results)


def default_rules() -> tuple:
    """Возвращает текущий набор базовых проверок."""
    return CpuMotherboardSocketRule(), RamMotherboardDdrRule(), CpuCoolerSocketRule()
