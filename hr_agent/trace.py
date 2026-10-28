"""Сохранение запуска: trace.json для программ и trace.md для чтения."""

import json
from pathlib import Path

from .goals import GOALS

LABELS = {
    "system": "СИСТЕМНЫЙ ПРОМПТ",
    "user": "ПОЛЬЗОВАТЕЛЬ",
    "assistant": "АГЕНТ ПИШЕТ",
    "call": "АГЕНТ ВЫЗЫВАЕТ",
    "result": "РЕЗУЛЬТАТ",
    "blocked": "ЗАЩИТА ОТКЛОНИЛА ВЫЗОВ",
    "defense": "ЗАЩИТА",
    "final": "ОТВЕТ АГЕНТА ПОЛЬЗОВАТЕЛЮ",
    "limit": "ЛИМИТ ШАГОВ",
    "error": "ОШИБКА",
}


def save(folder: Path, record: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "trace.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    path = folder / "trace.md"
    path.write_text(to_markdown(record), encoding="utf-8")
    return path


def to_markdown(record: dict) -> str:
    out = [f"# Запуск {record['run']}", "",
           f"- защиты: {', '.join(record['defenses']) or 'нет'}",
           f"- атака: {record['attack'] or 'нет'}",
           f"- модель: {record['model']}", "",
           "## Исход (по состоянию среды)", "",
           f"- задача пользователя решена: {_yes(record['outcome']['utility'])}"]
    for key, text in GOALS.items():
        out.append(f"- цель {key} ({text}): {_yes(record['outcome'][key])}")
    out += ["", "## Состояние среды после запуска", "", "```json",
            json.dumps(record["state"], ensure_ascii=False, indent=1), "```", "", "## Ход работы", ""]
    for event in record["trace"]:
        label = LABELS.get(event["type"], event["type"])
        if event["type"] == "call":
            out += [f"### {label}: `{event['name']}`", "```json",
                    json.dumps(event["args"], ensure_ascii=False, indent=1), "```"]
        elif event["type"] in ("result", "blocked"):
            extra = f" · {event['defense']}" if "defense" in event else ""
            out += [f"### {label} `{event['name']}`{extra}", "```", event["content"], "```"]
            if "shown" in event:
                out += ["Агент получил после защит:", "```", event["shown"], "```"]
        elif event["type"] == "defense":
            out += [f"### {label} · {event['defense']}: {event['note']}", "```", event["content"], "```"]
        else:
            out += [f"### {label}", "```", event.get("content", ""), "```"]
    return "\n".join(out) + "\n"


def _yes(value: bool) -> str:
    return "да" if value else "нет"
