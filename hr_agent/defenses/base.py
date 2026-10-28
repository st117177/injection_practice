"""Общий интерфейс защиты. Каждая защита переопределяет только нужные хуки."""


class Defense:
    name = ""          # как включать: --defense <name>
    title = ""         # короткое название для списка
    kind = ""          # промпт / детекция / контроль действий / права / архитектура
    description = ""   # что делает, одной-двумя фразами

    def setup(self, ctx) -> None:
        """Перед запуском: можно поменять ctx.system, ctx.tools, подготовить ctx.state."""

    def check_call(self, call, ctx) -> str | None:
        """Перед выполнением вызова. Вернуть причину, чтобы вызов отклонить."""
        return None

    def transform_result(self, call, result: str, ctx) -> str:
        """После выполнения: что агент увидит вместо исходного результата."""
        return result

    def after_tools(self, ctx) -> list[dict]:
        """После всех результатов шага: дополнительные сообщения агенту."""
        return []


def is_untrusted(call) -> bool:
    """Недоверенные данные — содержимое файлов. Список файлов и контакты защиты не трогают."""
    return call.name == "read_file"
