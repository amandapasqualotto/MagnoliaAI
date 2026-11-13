"""Ferramentas para consultar os documentos anexados (cronograma, apostilas...)."""

from magnolia import documents
from magnolia.tools import tool


@tool
def listar_documentos() -> str:
    """Lista os documentos que o usuário anexou na Magnólia."""
    docs = documents.names()
    return "\n".join(docs) if docs else "Nenhum documento anexado."


@tool
def ler_documento(nome: str) -> str:
    """Lê o texto de um documento anexado (por exemplo o cronograma).

    Use para responder perguntas sobre o conteúdo do documento, como
    "o que tenho no cronograma esta semana?".

    Args:
        nome: nome ou parte do nome do documento.
    """
    found = documents.find(nome)
    if not found:
        return f"Não há documento com '{nome}'. Anexados: {', '.join(documents.names()) or 'nenhum'}."
    text = documents.read(found)
    if len(text) > 30_000:
        return text[:30_000] + "\n[...documento longo: use buscar_nos_documentos para achar trechos]"
    return text


@tool
def buscar_nos_documentos(termo: str) -> str:
    """Procura uma palavra ou data em todos os documentos anexados e mostra os trechos.

    Args:
        termo: o que procurar, por exemplo "17/11", "prova" ou "Direito Civil".
    """
    term = termo.lower()
    hits = []
    for name in documents.names():
        lines = documents.read(name).splitlines()
        for i, line in enumerate(lines):
            if term in line.lower():
                context = " / ".join(line.strip() for line in lines[max(0, i - 1): i + 2] if line.strip())
                hits.append(f"[{name}] {context}")
    if not hits:
        return f"'{termo}' não aparece nos documentos."
    return "\n".join(hits[:25])
