"""Опциональный трейсинг в LangSmith.

По умолчанию выключен. Активируется, только если в .env задано
LANGSMITH_TRACING=true и установлен пакет langsmith (pip install langsmith).
Без этого модуль ничего не делает — работают локальные трейсы в runs/.

Включённый трейсинг на каждый прогон отправляет в LangSmith один run
(вход: атака/защиты/задача, выход: цели + финальный ответ + ход работы)
и возвращает ссылку на него, которую студент прикладывает к сдаче.
"""

import contextlib
import os

_TRUE = {"1", "true", "yes", "on"}


def enabled() -> bool:
    if os.getenv("LANGSMITH_TRACING", "").strip().lower() not in _TRUE:
        return False
    try:
        import langsmith  # noqa: F401
    except Exception:
        return False
    return True


class _Handle:
    """Ручка одного прогона: сюда кладём выход, отсюда читаем ссылку."""
    url = None
    _outputs = None

    def set_outputs(self, outputs: dict):
        self._outputs = outputs


@contextlib.contextmanager
def run_trace(name: str, inputs: dict):
    """Контекст одного прогона агента. Если трейсинг выключен или недоступен —
    пустышка: yield-ит ручку с url=None и ничего не отправляет. Трейсинг никогда
    не роняет прогон — любые ошибки LangSmith проглатываются."""
    handle = _Handle()
    if not enabled():
        yield handle
        return

    # Пытаемся начать трейс. Не вышло — работаем локально.
    try:
        from langsmith import Client
        from langsmith import trace as ls_trace
        project = os.getenv("LANGSMITH_PROJECT", "hr-agent")
        cm = ls_trace(name=name, run_type="chain", inputs=inputs, project_name=project)
        run_tree = cm.__enter__()
    except Exception:
        yield handle
        return

    # Трейс начат — ровно один yield, остальное в finally.
    try:
        yield handle
    finally:
        try:
            if handle._outputs is not None:
                run_tree.end(outputs=handle._outputs)
        except Exception:
            pass
        try:
            cm.__exit__(None, None, None)
        except Exception:
            pass
        try:
            client = Client()
            try:
                handle.url = client.share_run(run_tree.id)
            except Exception:
                handle.url = client.get_run_url(run=run_tree)
        except Exception:
            handle.url = None
