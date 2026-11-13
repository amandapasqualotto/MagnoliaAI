"""Pesquisa na internet e abertura de sites."""

import webbrowser
from urllib.parse import quote_plus

from magnolia.tools import tool


@tool
def pesquisar_na_web(pergunta: str, max_resultados: int = 5) -> str:
    """Pesquisa na internet (DuckDuckGo) e devolve títulos, trechos e links.

    Use para notícias, fatos atuais, preços, placares ou qualquer coisa que
    possa ter mudado recentemente.

    Args:
        pergunta: o que pesquisar.
        max_resultados: quantos resultados trazer (padrão 5).
    """
    from ddgs import DDGS  # importado aqui para a Magnólia abrir rápido

    results = DDGS().text(pergunta, region="br-pt", max_results=max_resultados)
    if not results:
        return "Nenhum resultado encontrado."
    return "\n\n".join(
        f"{r.get('title')}\n{r.get('body')}\nFonte: {r.get('href')}" for r in results
    )


@tool
def pesquisar_noticias(assunto: str) -> str:
    """Busca as notícias mais recentes sobre um assunto.

    Args:
        assunto: tema das notícias, por exemplo "tecnologia" ou "Campo Grande".
    """
    from ddgs import DDGS

    results = DDGS().news(assunto, region="br-pt", max_results=5)
    if not results:
        return "Nenhuma notícia encontrada."
    return "\n\n".join(
        f"{r.get('title')} ({r.get('source')}, {r.get('date', '')[:10]})\n{r.get('body')}"
        for r in results
    )


@tool
def abrir_site(endereco: str) -> str:
    """Abre um site no navegador do usuário.

    Args:
        endereco: URL ou domínio, por exemplo "github.com".
    """
    if not endereco.startswith(("http://", "https://")):
        endereco = "https://" + endereco
    webbrowser.open(endereco)
    return f"Abri {endereco} no navegador."


@tool
def tocar_no_youtube(busca: str) -> str:
    """Abre o YouTube com a busca de um vídeo ou música.

    Args:
        busca: nome do vídeo, música ou artista.
    """
    webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(busca)}")
    return f"Abri o YouTube buscando por '{busca}'."
