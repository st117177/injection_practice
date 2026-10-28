"""Фейковая модель для офлайн-тестов. Проигрывает заранее заданные ответы.

Поддерживает «сценарий» — список шагов. Каждый шаг это либо текстовый ответ
(конец работы), либо список вызовов инструментов. Для защит, которые сами
обращаются к модели (детектор, очиститель и т. п.), ответы задаются отдельной
функцией-обработчиком по системному промпту.
"""

from hr_agent.llm import LLM, Reply, ToolCall


class FakeLLM(LLM):
    def __init__(self, script, aux=None):
        super().__init__(model="fake", rpm=0)
        self.script = list(script)
        self.aux = aux or (lambda system, user: "SAFE")
        self.step = 0

    def _chat(self, system, messages, tools) -> Reply:
        self.usage.requests += 1
        # Запрос без инструментов — это защита спрашивает модель о чём-то своём.
        if not tools:
            user = messages[-1]["content"] if messages else ""
            return Reply(self.aux(system, user))
        item = self.script[self.step]
        self.step += 1
        if isinstance(item, str):
            return Reply(item)
        calls = [ToolCall(id=f"c{self.step}_{i}", name=n, args=a) for i, (n, a) in enumerate(item)]
        return Reply("", calls)


def solve_honestly():
    """Сценарий «агент честно решает задачу»: читает всё, выбирает двух сильных, шлёт письма."""
    return [
        [("list_files", {"folder": "resumes"})],
        [("read_file", {"path": "resumes/sokolova.md"}),
         ("read_file", {"path": "resumes/petrov.md"}),
         ("read_file", {"path": "resumes/kim.md"}),
         ("read_file", {"path": "resumes/morozov.md"})],
        [("save_shortlist", {"candidates": ["resumes/sokolova.md", "resumes/petrov.md"], "reason": "сильнее всех"})],
        [("send_email", {"to": "maria.sokolova@mail.example", "subject": "Приглашение", "body": "Ждём вас"}),
         ("send_email", {"to": "ivan.petrov@mail.example", "subject": "Приглашение", "body": "Ждём вас"})],
        "Готово: шортлист сохранён, приглашения отправлены.",
    ]
