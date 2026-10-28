"""Запуск HR-агента с атакой и защитами.

Примеры:
  python run.py --list-defenses
  python run.py                                  # без защиты, без атаки — проверить, что агент решает задачу
  python run.py --attack attacks/my.md           # подложить своё резюме
  python run.py --attack attacks/my.md --defense spotlighting --runs 5
  python run.py --attack attacks/my.md --defense datamarking,action_check
"""

import argparse
import sys
from pathlib import Path

from hr_agent import defenses as D
from hr_agent.agent import run_agent
from hr_agent.env import Environment
from hr_agent.goals import GOALS, evaluate
from hr_agent.trace import save

RUNS_DIR = Path(__file__).resolve().parent / "runs"


def main():
    parser = argparse.ArgumentParser(description="HR-агент: стенд для prompt injection.")
    parser.add_argument("--attack", help="файл с вашим текстом для раздела «О себе» резюме Морозова (payload)")
    parser.add_argument("--defense", default="", help="защиты через запятую, например spotlighting,action_check")
    parser.add_argument("--runs", type=int, default=1, help="сколько раз запустить (для статистики успеха)")
    parser.add_argument("--list-defenses", action="store_true", help="показать каталог защит")
    parser.add_argument("--name", default="", help="имя папки для трейсов внутри runs/")
    args = parser.parse_args()

    if args.list_defenses:
        print(D.catalog())
        return

    from hr_agent.llm import LLMError, from_env
    try:
        llm = from_env()
    except LLMError as error:
        sys.exit(str(error))

    injection = Path(args.attack).read_text(encoding="utf-8") if args.attack else None
    defense_names = [n for n in args.defense.split(",") if n.strip()]
    label = args.name or "_".join(defense_names) or "none"
    tag = Path(args.attack).stem if args.attack else "clean"
    out_root = RUNS_DIR / f"{tag}__{label}"

    totals = {k: 0 for k in ["utility", *GOALS]}
    for i in range(1, args.runs + 1):
        env = Environment.load(injection=injection)
        ctx = run_agent(llm, env, D.build(defense_names))
        outcome = evaluate(env)
        for key in totals:
            totals[key] += int(outcome[key])
        record = {
            "run": i, "model": llm.model, "attack": args.attack, "defenses": defense_names,
            "outcome": outcome, "state": env.snapshot(), "trace": ctx.trace,
        }
        path = save(out_root / f"run_{i}", record)
        print(f"[{i}/{args.runs}] задача={_m(outcome['utility'])} "
              + " ".join(f"{k}={_m(outcome[k])}" for k in GOALS) + f"  → {path.parent.name}/{path.name}")

    print("\nИтог по", args.runs, "запускам (защиты:", ", ".join(defense_names) or "нет", "):")
    print("  задача пользователя решена:", f"{totals['utility']}/{args.runs}")
    for key, text in GOALS.items():
        print(f"  цель {key}: {totals[key]}/{args.runs}  — {text}")
    print("  модель сделала запросов:", llm.usage.requests,
          f"(вход {llm.usage.input_tokens}, выход {llm.usage.output_tokens} токенов)")
    print("  трейсы:", out_root)


def _m(value: bool) -> str:
    return "✓" if value else "·"


if __name__ == "__main__":
    main()
