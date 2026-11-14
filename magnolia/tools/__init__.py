"""Sistema de ferramentas (tools) da Magnólia.

Como funciona:
  1. Cada arquivo dentro desta pasta é um "módulo de habilidades".
  2. Toda função marcada com @tool vira uma ferramenta que o Gemini pode chamar.
  3. O Gemini lê o NOME, os PARÂMETROS (com tipos) e a DOCSTRING da função
     para decidir quando usá-la. Por isso as docstrings são importantes!

Para criar uma habilidade nova, basta criar um arquivo .py aqui, por exemplo:

    from magnolia.tools import tool

    @tool
    def jogar_dado(lados: int = 6) -> str:
        \"\"\"Joga um dado e devolve o resultado.\"\"\"
        import random
        return str(random.randint(1, lados))

Na próxima vez que a Magnólia abrir, ela já sabe jogar dados.
"""

import functools
import importlib
import pkgutil
from typing import Callable

_REGISTRY: dict[str, Callable] = {}

# Resultados enormes deixam o Gemini lento (e na voz podem estourar o tempo limite).
# Por isso cortamos o que as ferramentas devolvem:
MAX_TEXT_CHARS = 12_000   # conversa por texto
MAX_VOICE_CHARS = 4_000   # conversa por voz (tem que responder rápido)


def shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[...resultado cortado para responder rápido; peça um trecho mais específico]"


def tool(func: Callable) -> Callable:
    """Decorador que registra uma função como ferramenta da Magnólia.

    Também protege a função: se ela der erro, o erro vira um texto que o
    Gemini consegue ler e explicar, em vez de derrubar o programa.
    """

    @functools.wraps(func)  # mantém nome, parâmetros e docstring originais
    def safe(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            return f"Erro ao executar {func.__name__}: {e}"
        return shorten(result, MAX_TEXT_CHARS) if isinstance(result, str) else result

    _REGISTRY[func.__name__] = safe
    return safe


def load_tools() -> list[Callable]:
    """Importa todos os arquivos desta pasta e devolve as ferramentas encontradas."""
    for module in pkgutil.iter_modules(__path__):
        if not module.name.startswith("_"):
            importlib.import_module(f"{__name__}.{module.name}")
    return list(_REGISTRY.values())


def run_tool(name: str, args: dict, max_chars: int | None = None) -> str:
    """Executa uma ferramenta pelo nome (usado no modo voz).

    Nunca deixa um erro derrubar a Magnólia: devolve o erro como texto para que
    o modelo possa explicar o que aconteceu.
    """
    func = _REGISTRY.get(name)
    if func is None:
        return f"Erro: a ferramenta '{name}' não existe."
    try:
        result = str(func(**(args or {})))
        return shorten(result, max_chars) if max_chars else result
    except TypeError as e:  # o modelo mandou parâmetros errados
        return f"Erro ao executar {name}: {e}"
