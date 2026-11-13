"""Ferramentas para o Jarvis lembrar (e esquecer) coisas sobre você."""

from jarvis import memory
from jarvis.tools import tool


@tool
def lembrar_fato(fato: str) -> str:
    """Guarda na memória permanente um fato importante sobre o usuário.

    Use quando o usuário contar preferências, rotina, metas ou pessoas
    importantes, ou quando pedir explicitamente para lembrar algo.

    Args:
        fato: o fato, escrito de forma curta e clara.
    """
    memory.add_fact(fato)
    return f"Guardado na memória: {fato}"


@tool
def esquecer_fato(termo: str) -> str:
    """Apaga da memória os fatos que contêm um termo.

    Args:
        termo: palavra ou trecho do fato a esquecer.
    """
    n = memory.remove_facts(termo)
    return f"{n} fato(s) apagado(s)." if n else "Não encontrei nada com esse termo."


@tool
def listar_memoria() -> str:
    """Lista tudo o que o Jarvis sabe sobre o usuário."""
    facts = memory.load_facts()
    if not facts:
        return "A memória está vazia."
    return "\n".join(f"- {f['fato']} (desde {f['data']})" for f in facts)
