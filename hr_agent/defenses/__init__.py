"""Реестр защит. Девять штук, из них на семинаре предлагаем выбрать пять."""

from .architecture import DualLLM, LeastPrivilege, PlanThenExecute
from .base import Defense
from .detection import ActionCheck, InjectionDetector, Sanitizer
from .prompt_based import Datamarking, RepeatTask, Spotlighting

ALL = [
    Spotlighting,
    Datamarking,
    RepeatTask,
    InjectionDetector,
    Sanitizer,
    ActionCheck,
    LeastPrivilege,
    PlanThenExecute,
    DualLLM,
]

BY_NAME = {d.name: d for d in ALL}

# Рекомендованная пятёрка по нарастанию сложности обхода — по одной каждого типа.
RECOMMENDED = ["spotlighting", "repeat_task", "sanitizer", "action_check", "dual_llm"]


def build(names: list[str]) -> list[Defense]:
    chosen = []
    for name in names:
        name = name.strip()
        if not name or name == "none":
            continue
        if name not in BY_NAME:
            raise SystemExit(f"Неизвестная защита: {name!r}. Список: python run.py --list-defenses")
        chosen.append(BY_NAME[name]())
    return chosen


def catalog() -> str:
    lines = ["Доступные защиты (--defense имя1,имя2):", ""]
    for d in ALL:
        star = " *" if d.name in RECOMMENDED else "  "
        lines.append(f"{star} {d.name:16} [{d.kind}] {d.title}")
        lines.append(f"      {d.description}")
    lines += ["", "  * — рекомендованная пятёрка для последовательного прохождения.",
              "  Защиты можно комбинировать: --defense datamarking,action_check"]
    return "\n".join(lines)
