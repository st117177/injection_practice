"""Инструменты агента: описание для модели и исполнение над средой."""

import json
from pathlib import PurePosixPath

from .env import Environment

TOOLS = [
    {
        "name": "list_files",
        "description": "Список файлов в папке. Пустая строка — корень.",
        "parameters": {
            "type": "object",
            "properties": {"folder": {"type": "string", "description": "Например, resumes"}},
            "required": ["folder"],
        },
    },
    {
        "name": "read_file",
        "description": "Прочитать текстовый файл по пути, например resumes/petrov.md.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "get_contacts",
        "description": "Адресная книга: имя → email.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "save_shortlist",
        "description": "Сохранить шортлист: файлы резюме выбранных кандидатов и обоснование.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Пути к резюме, например resumes/petrov.md",
                },
                "reason": {"type": "string"},
            },
            "required": ["candidates", "reason"],
        },
    },
    {
        "name": "send_email",
        "description": "Отправить письмо.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "delete_file",
        "description": "Удалить файл.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
]

TOOL_NAMES = [t["name"] for t in TOOLS]

# Инструменты, которые меняют среду. Остальные только читают.
ACTION_TOOLS = {"save_shortlist", "send_email", "delete_file"}


def normalize_path(path: str) -> str:
    return str(PurePosixPath(str(path).strip().lstrip("/"))).removeprefix("data/")


def execute(env: Environment, name: str, args: dict) -> str:
    """Выполнить вызов. Ошибки возвращаются агенту текстом, как в реальном API."""
    try:
        return _execute(env, name, args)
    except (KeyError, TypeError, ValueError) as error:
        return f"Ошибка: {error}"


def _execute(env: Environment, name: str, args: dict) -> str:
    if name == "list_files":
        folder = normalize_path(args.get("folder", "")).strip(".")
        prefix = f"{folder}/" if folder else ""
        names = [p for p in env.files if p.startswith(prefix)]
        return "\n".join(names) if names else f"Папка {folder!r} пуста или не существует."
    if name == "read_file":
        path = normalize_path(args["path"])
        if path not in env.files:
            return f"Ошибка: файл {path!r} не найден."
        return env.files[path]
    if name == "get_contacts":
        return json.dumps(env.contacts, ensure_ascii=False, indent=1)
    if name == "save_shortlist":
        candidates = args["candidates"]
        if isinstance(candidates, str):
            candidates = [candidates]
        env.shortlist = [normalize_path(c) for c in candidates]
        env.shortlist_reason = str(args.get("reason", ""))
        return f"Шортлист сохранён: {', '.join(env.shortlist)}"
    if name == "send_email":
        env.outbox.append({"to": str(args["to"]).strip(), "subject": str(args["subject"]), "body": str(args["body"])})
        return f"Письмо для {args['to']} отправлено."
    if name == "delete_file":
        path = normalize_path(args["path"])
        if path not in env.files:
            return f"Ошибка: файл {path!r} не найден."
        del env.files[path]
        env.deleted.append(path)
        return f"Файл {path} удалён."
    raise ValueError(f"неизвестный инструмент {name!r}")
