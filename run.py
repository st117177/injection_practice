"""Запуск HR-агента с атакой и защитами.

Примеры:
  python run.py --list-defenses
  python run.py                                  # без защиты, без атаки — проверить, что агент решает задачу
  python run.py --attack attacks/my.md           # подложить своё резюме
  python run.py --attack attacks/my.md --defense spotlighting --runs 5
  python run.py --attack attacks/my.md --defense datamarking,action_check
  python run.py --attack attacks/my.md --defense spotlighting,repeat_task --goal A,B --runs 5
"""

import argparse
import sys
from pathlib import Path

from hr_agent import defenses as D
from hr_agent import tracing
from hr_agent.agent import USER_TASK, run_agent
from hr_agent.env import Environment
from hr_agent.goals import GOALS, evaluate
from hr_agent.trace import save

RUNS_DIR = Path(__file__).resolve().parent / "runs"


def main():
    parser = argparse.ArgumentParser(description="HR-агент: стенд для prompt injection.")
    parser.add_argument("--attack", help="файл с вашим текстом для раздела «О себе» резюме Гослинга (payload)")
    parser.add_argument("--defense", default="", help="защиты через запятую, например spotlighting,action_check")
    parser.add_argument("--runs", type=int, default=1, help="сколько раз запустить (для статистики успеха)")
    parser.add_argument("--goal", default="", help="целевые цели через запятую, например A,B — комбо засчитано, если достигнуты все")
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
    goals = [g.strip().upper() for g in args.goal.split(",") if g.strip()]
    bad = [g for g in goals if g not in GOALS]
    if bad:
        sys.exit(f"неизвестные цели: {', '.join(bad)}. Доступны: {', '.join(GOALS)}")
    label = args.name or "_".join(defense_names) or "none"
    tag = Path(args.attack).stem if args.attack else "clean"
    out_root = RUNS_DIR / f"{tag}__{label}"

    totals = {k: 0 for k in ["utility", *GOALS]}
    combo_hits = 0
    for i in range(1, args.runs + 1):
        env = Environment.load(injection=injection)
        with tracing.run_trace(
                name=f"{tag}__{label} #{i}",
                inputs={"attack": args.attack, "defenses": defense_names, "task": USER_TASK}) as tr:
            ctx = run_agent(llm, env, D.build(defense_names))
            outcome = evaluate(env)
            tr.set_outputs({"outcome": outcome, "final": _final_reply(ctx), "trace": ctx.trace})
        for key in totals:
            totals[key] += int(outcome[key])
        record = {
            "run": i, "model": llm.model, "attack": args.attack, "defenses": defense_names,
            "outcome": outcome, "state": env.snapshot(), "trace": ctx.trace,
        }
        if tr.url:
            record["langsmith_url"] = tr.url
        path = save(out_root / f"run_{i}", record)
        combo = all(outcome[g] for g in goals) if goals else None
        if combo:
            combo_hits += 1
        line = (f"[{i}/{args.runs}] задача={_m(outcome['utility'])} "
                + " ".join(f"{k}={_m(outcome[k])}" for k in GOALS))
        if goals:
            line += f"  комбо({'+'.join(goals)})={_m(combo)}"
        print(line + f"  → {path.parent.name}/{path.name}")
        if tr.url:
            print(f"      LangSmith: {tr.url}")

    print("\nИтог по", args.runs, "запускам (защиты:", ", ".join(defense_names) or "нет", "):")
    print("  задача пользователя решена:", f"{totals['utility']}/{args.runs}")
    for key, text in GOALS.items():
        print(f"  цель {key}: {totals[key]}/{args.runs}  — {text}")
    if goals:
        print(f"  комбо {'+'.join(goals)} пройдено: {combo_hits}/{args.runs}")
    print("  модель сделала запросов:", llm.usage.requests,
          f"(вход {llm.usage.input_tokens}, выход {llm.usage.output_tokens} токенов)")
    print("  трейсы:", out_root)


def _final_reply(ctx) -> str:
    for message in reversed(ctx.messages):
        if message["role"] == "assistant":
            return message.get("content", "") or ""
    return ""


def _m(value: bool) -> str:
    return "✓" if value else "·"


if __name__ == "__main__":
    main()
