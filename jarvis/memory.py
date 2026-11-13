"""Memória de longo prazo do Jarvis.

Guarda fatos sobre você num arquivo JSON simples (data/memory.json), que você
pode abrir e editar à mão. Os fatos entram no prompt toda vez que o Jarvis inicia.
"""

import json
from datetime import datetime

from jarvis import config


def load_facts() -> list[dict]:
    if not config.MEMORY_FILE.exists():
        return []
    try:
        return json.loads(config.MEMORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_facts(facts: list[dict]) -> None:
    config.MEMORY_FILE.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")


def add_fact(text: str) -> None:
    facts = load_facts()
    facts.append({"fato": text.strip(), "data": datetime.now().strftime("%Y-%m-%d")})
    save_facts(facts)


def remove_facts(term: str) -> int:
    """Remove todos os fatos que contêm o termo. Devolve quantos foram removidos."""
    facts = load_facts()
    kept = [f for f in facts if term.lower() not in f["fato"].lower()]
    save_facts(kept)
    return len(facts) - len(kept)


def facts_for_prompt() -> str:
    facts = load_facts()
    if not facts:
        return ""
    lines = "\n".join(f"- {f['fato']}" for f in facts)
    return f"[O QUE VOCÊ SABE SOBRE O USUÁRIO]\n{lines}\n"
