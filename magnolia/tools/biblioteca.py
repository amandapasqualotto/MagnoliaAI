"""Ferramentas da Biblioteca: consultar, organizar e criar comandos personalizados."""

import webbrowser

from magnolia import library
from magnolia.tools import tool


def _label(item: dict) -> str:
    cols = f" [{', '.join(item['colecoes'])}]" if item["colecoes"] else ""
    return f"{item['titulo']} ({library.KIND_LABEL[item['tipo']]}){cols}"


# ── Consultar ───────────────────────────────────────────────────────────────
@tool
def biblioteca_listar(colecao: str = "") -> str:
    """Lista o que há na biblioteca do usuário (arquivos, páginas salvas e sites de notícias).

    Args:
        colecao: mostra só uma coleção, por exemplo "faculdade". Vazio = tudo.
    """
    items = library.items_in(colecao)
    if not items:
        return f"Nada na coleção '{colecao}'." if colecao else "A biblioteca está vazia."
    text = "\n".join(_label(i) for i in items)
    cols = library.collections()
    return text + (f"\nColeções existentes: {', '.join(cols)}" if cols and not colecao else "")


@tool
def biblioteca_ler(item: str, assunto: str = "") -> str:
    """Lê um item da biblioteca: o texto de um arquivo ou página, ou as manchetes atuais de um site.

    Args:
        item: título, endereço ou parte do nome do item (ex.: "cronograma", "g1").
        assunto: para sites de notícias, filtra as manchetes por um tema (opcional).
    """
    found = library.find(item)
    if not found:
        return f"Não há '{item}' na biblioteca."
    text = library.read(found, assunto)
    if len(text) > 10_000:
        return text[:10_000] + "\n[...item longo: use biblioteca_buscar para achar trechos específicos]"
    return f"{_label(found)}\n\n{text}"


@tool
def biblioteca_abrir(item: str) -> str:
    """Abre no navegador um link da biblioteca (página salva, Google Docs ou site de notícias).

    Args:
        item: título, endereço ou parte do nome do item.
    """
    found = library.find(item)
    if not found:
        return f"Não há '{item}' na biblioteca."
    if found["tipo"] == "arquivo":
        return f"'{found['titulo']}' é um arquivo anexado; posso ler o conteúdo para você."
    webbrowser.open(found["origem"])
    return f"Abri '{found['titulo']}' no navegador."


@tool
def biblioteca_buscar(termo: str, colecao: str = "") -> str:
    """Procura uma palavra, data ou assunto dentro dos arquivos e páginas salvas da biblioteca.

    Args:
        termo: o que procurar, por exemplo "17/11", "prova" ou "prescrição".
        colecao: procura só dentro de uma coleção (opcional).
    """
    hits = library.search(termo, colecao)
    if not hits:
        where = f" na coleção '{colecao}'" if colecao else ""
        return f"'{termo}' não aparece nos textos salvos{where}."
    return "\n".join(hits[:12])


@tool
def biblioteca_noticias(colecao: str = "", assunto: str = "", por_site: int = 5) -> str:
    """Traz as últimas manchetes dos sites de notícias da biblioteca.

    Use PRIMEIRO sempre que pedirem notícias, manchetes ou "o que está em alta".

    Args:
        colecao: usa só os sites de uma coleção (opcional).
        assunto: filtra as manchetes por um tema, por exemplo "economia" (opcional).
        por_site: quantas manchetes de cada site (padrão 5).
    """
    sites = [i for i in library.items_in(colecao) if i["tipo"] == "noticias"]
    if not sites:
        return "Não há sites de notícias na biblioteca" + (f" na coleção '{colecao}'" if colecao else "") + \
            ". Use pesquisar_noticias."
    blocks = []
    for site in sites:
        try:
            body = library.read(site, assunto, por_site)
        except Exception as e:  # noqa: BLE001
            body = f"- não consegui ler este site agora ({e.__class__.__name__})"
        blocks.append(f"[{site['titulo']}]\n{body}")
    return "\n\n".join(blocks)


# ── Organizar ───────────────────────────────────────────────────────────────
@tool
def biblioteca_adicionar_link(endereco: str, colecoes: str = "", tipo: str = "auto") -> str:
    """Adiciona um link à biblioteca.

    Args:
        endereco: o link, por exemplo "g1.globo.com" ou o link de um artigo ou Google Docs.
        colecoes: coleções separadas por vírgula, por exemplo "notícias, economia" (opcional).
        tipo: "noticias" (site cujas manchetes ela lê na hora), "pagina" (salva o conteúdo)
            ou "auto" (decide sozinha; padrão).
    """
    item = library.add_link(endereco, colecoes, tipo)
    return f"Adicionado à biblioteca: {_label(item)}"


@tool
def biblioteca_organizar(item: str, colecoes: str) -> str:
    """Define as coleções de um item da biblioteca (substitui as atuais).

    Args:
        item: título ou parte do nome do item.
        colecoes: coleções separadas por vírgula, por exemplo "faculdade, direito". Vazio = nenhuma.
    """
    found = library.find(item)
    if not found:
        return f"Não há '{item}' na biblioteca."
    updated = library.set_collections(found["id"], colecoes)
    return f"Organizado: {_label(updated)}"


@tool
def biblioteca_atualizar(item: str) -> str:
    """Baixa de novo o conteúdo de uma página salva na biblioteca (para pegar mudanças).

    Args:
        item: título ou parte do nome da página.
    """
    found = library.find(item)
    if not found or found["tipo"] != "pagina":
        return f"Não há página salva chamada '{item}'."
    library.refresh(found)
    return f"Página '{found['titulo']}' atualizada."


@tool
def biblioteca_remover(item: str) -> str:
    """Remove um item da biblioteca.

    Args:
        item: título ou parte do nome do item.
    """
    found = library.find(item)
    if not found:
        return f"Não há '{item}' na biblioteca."
    library.remove(found["id"])
    return f"Removido: {found['titulo']}."


# ── Comandos personalizados ─────────────────────────────────────────────────
@tool
def criar_comando(nome: str, instrucao: str, colecoes: str = "") -> str:
    """Cria (ou substitui) um comando personalizado: um atalho que o usuário pode dizer depois.

    Exemplo: nome "resumo jurídico", instrução "busque as novidades e resuma em 5 tópicos",
    coleções "direito". Escreva a instrução completa, como uma ordem clara.

    Args:
        nome: o que o usuário vai dizer para usar o comando.
        instrucao: o que fazer quando o comando for dito.
        colecoes: coleções da biblioteca que o comando deve consultar, separadas por vírgula (opcional).
    """
    cmd = library.add_command(nome, instrucao, colecoes)
    where = f" usando a coleção {', '.join(cmd['colecoes'])}" if cmd["colecoes"] else ""
    return f'Comando "{cmd["nome"]}" criado{where}. É só dizer "{cmd["nome"]}".'


@tool
def listar_comandos() -> str:
    """Lista os comandos personalizados do usuário."""
    cmds = library.commands()
    if not cmds:
        return "Nenhum comando criado ainda."
    return "\n".join(f'"{c["nome"]}": {c["instrucao"]}' for c in cmds)


@tool
def apagar_comando(nome: str) -> str:
    """Apaga um comando personalizado.

    Args:
        nome: nome do comando.
    """
    return "Comando apagado." if library.remove_command(nome) else f'Não existe comando "{nome}".'
