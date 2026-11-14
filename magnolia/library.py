"""Biblioteca da Magnólia: tudo o que você quer que ela consulte, num lugar só.

Tipos de item:
  - "arquivo":  PDF, Word ou texto anexado (o texto é extraído e guardado)
  - "pagina":   link de uma página ou de um Google Docs (o conteúdo é salvo)
  - "noticias": site de notícias (as manchetes são buscadas na hora, pelo feed)

Cada item pode estar em "coleções" (ex.: "faculdade", "direito", "notícias"),
e os "comandos" são atalhos que você cria no chat, como:
  "resumo jurídico" -> "busque novidades na coleção direito e resuma em 5 tópicos"

Arquivos: data/usuarios/<você>/biblioteca.json (a lista) e
data/usuarios/<você>/biblioteca/<id>.txt (os textos, criptografados).
"""

import json
import re
import secrets
from datetime import datetime
from pathlib import Path

from magnolia import config, feeds

SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".csv"}
MAX_CHARS = 200_000  # limite de texto por item (~100 páginas)


# ── Armazenamento ───────────────────────────────────────────────────────────
def _index_file() -> Path:
    return config.USER_DIR / "biblioteca.json"


def _texts() -> Path:
    folder = config.USER_DIR / "biblioteca"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load() -> dict:
    try:
        data = json.loads(_index_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {"itens": [], "comandos": []}
        _migrate_old_data(data)
    data.setdefault("itens", [])
    data.setdefault("comandos", [])
    return data


def save(data: dict) -> None:
    _index_file().parent.mkdir(parents=True, exist_ok=True)
    _index_file().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(item_id: str, text: str):
    data = text[:MAX_CHARS].encode()
    (_texts() / f"{item_id}.txt").write_bytes(config.CIPHER.encrypt(data) if config.CIPHER else data)


def _read_text(item_id: str) -> str:
    data = (_texts() / f"{item_id}.txt").read_bytes()
    return (config.CIPHER.decrypt(data) if config.CIPHER else data).decode()


def _clean_collections(collections) -> list[str]:
    if isinstance(collections, str):
        collections = collections.split(",")
    return sorted({c.strip().lower() for c in collections or [] if c and c.strip()})


def _new_item(kind: str, title: str, origin: str, collections, **extra) -> dict:
    return {"id": secrets.token_hex(4), "tipo": kind, "titulo": title.strip()[:120], "origem": origin,
            "colecoes": _clean_collections(collections), "adicionado": datetime.now().strftime("%Y-%m-%d"),
            **extra}


# ── Adicionar ───────────────────────────────────────────────────────────────
def extract_file_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        pages = PdfReader(str(path)).pages
        return "\n\n".join(f"[página {i}]\n{p.extract_text() or ''}" for i, p in enumerate(pages, 1))
    if suffix == ".docx":
        from docx import Document

        doc = Document(str(path))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:  # cronogramas costumam estar em tabelas
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        return "\n".join(parts)
    return path.read_text(encoding="utf-8", errors="ignore")


def add_file(path: str | Path, collections=None) -> dict:
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Formato não suportado: {path.suffix}. Use PDF, Word (.docx) ou texto.")
    text = extract_file_text(path).strip()
    if not re.sub(r"\[página \d+\]", "", text).strip():
        raise ValueError("Não encontrei texto nesse arquivo (pode ser um PDF escaneado, só com imagem).")
    item = _new_item("arquivo", path.stem, path.name, collections)
    _write_text(item["id"], text)
    data = load()
    data["itens"].append(item)
    save(data)
    return item


def add_link(url: str, collections=None, kind: str = "auto") -> dict:
    """Adiciona um link. kind: "pagina", "noticias" ou "auto" (decide sozinha).

    No automático: endereço de site sem caminho (ex.: g1.globo.com) que tem feed
    vira "noticias"; qualquer outro link vira "pagina" (o conteúdo é salvo).
    """
    url = feeds.normalize_url(url)
    site = feeds.clean_site(url)
    if not site:
        raise ValueError("Não entendi esse endereço.")
    data = load()
    if any(feeds.clean_site(i["origem"]) == site for i in data["itens"] if i["tipo"] != "arquivo"):
        raise ValueError(f"{site} já está na biblioteca.")

    feed = None
    if kind in ("auto", "noticias"):
        is_homepage = "/" not in site
        if kind == "noticias" or is_homepage:
            feed = feeds.discover_feed(site)
            if feed or kind == "noticias":
                item = _new_item("noticias", site, url, collections, feed=feed or "")
                data["itens"].append(item)
                save(data)
                return item

    title, text = feeds.fetch_page(url)
    if not text.strip():
        raise ValueError("Não consegui ler o conteúdo dessa página.")
    item = _new_item("pagina", title or site, url, collections, atualizado=datetime.now().strftime("%Y-%m-%d"))
    _write_text(item["id"], text)
    data["itens"].append(item)
    save(data)
    return item


# ── Consultar ───────────────────────────────────────────────────────────────
def find(term: str) -> dict | None:
    """Acha um item pelo título, endereço ou id (exato primeiro, depois parcial)."""
    term_l = term.strip().lower()
    items = load()["itens"]
    for item in items:
        if term_l in (item["id"], item["titulo"].lower(), item["origem"].lower()):
            return item
    for item in items:
        if term_l in item["titulo"].lower() or term_l in item["origem"].lower():
            return item
    return None


def items_in(collection: str = "") -> list[dict]:
    items = load()["itens"]
    if not collection:
        return items
    c = collection.strip().lower()
    return [i for i in items if any(c in col for col in i["colecoes"])]


def read(item: dict, subject: str = "", limit: int = 8) -> str:
    """Conteúdo de um item: texto salvo, ou manchetes atuais (sites de notícias)."""
    if item["tipo"] == "noticias":
        news = feeds.headlines(feeds.clean_site(item["origem"]), item.get("feed", ""), subject, limit)
        return "\n".join(f"- {n['titulo']} ({n['data']})" for n in news) or "(nada recente sobre isso)"
    return _read_text(item["id"])


def search(term: str, collection: str = "") -> list[str]:
    """Procura um termo nos textos salvos (arquivos e páginas) e devolve os trechos."""
    term_l = term.lower()
    hits = []
    for item in items_in(collection):
        if item["tipo"] == "noticias":
            continue
        lines = _read_text(item["id"]).splitlines()
        for i, line in enumerate(lines):
            if term_l in line.lower():
                context = " / ".join(x.strip() for x in lines[max(0, i - 1): i + 2] if x.strip())
                hits.append(f"[{item['titulo']}] {context}")
    return hits


def refresh(item: dict) -> dict:
    """Baixa de novo o conteúdo de uma página salva."""
    title, text = feeds.fetch_page(item["origem"])
    _write_text(item["id"], text)
    data = load()
    for i in data["itens"]:
        if i["id"] == item["id"]:
            i["atualizado"] = datetime.now().strftime("%Y-%m-%d")
    save(data)
    return item


def remove(item_id: str) -> bool:
    data = load()
    before = len(data["itens"])
    data["itens"] = [i for i in data["itens"] if i["id"] != item_id]
    (_texts() / f"{item_id}.txt").unlink(missing_ok=True)
    save(data)
    return len(data["itens"]) < before


def set_collections(item_id: str, collections) -> dict | None:
    data = load()
    for item in data["itens"]:
        if item["id"] == item_id:
            item["colecoes"] = _clean_collections(collections)
            save(data)
            return item
    return None


def collections() -> list[str]:
    return sorted({c for i in load()["itens"] for c in i["colecoes"]})


# ── Comandos ────────────────────────────────────────────────────────────────
def add_command(name: str, instruction: str, collections=None) -> dict:
    name = name.strip().strip('"“”').lower()
    if not name or not instruction.strip():
        raise ValueError("O comando precisa de um nome e do que ele deve fazer.")
    data = load()
    data["comandos"] = [c for c in data["comandos"] if c["nome"] != name]  # recriar = substituir
    command = {"nome": name, "instrucao": instruction.strip(), "colecoes": _clean_collections(collections)}
    data["comandos"].append(command)
    save(data)
    return command


def remove_command(name: str) -> bool:
    data = load()
    before = len(data["comandos"])
    data["comandos"] = [c for c in data["comandos"] if c["nome"] != name.strip().lower()]
    save(data)
    return len(data["comandos"]) < before


def commands() -> list[dict]:
    return load()["comandos"]


# ── Para o prompt ───────────────────────────────────────────────────────────
KIND_LABEL = {"arquivo": "arquivo", "pagina": "página salva", "noticias": "site de notícias"}


def for_prompt() -> str:
    data = load()
    parts = []
    if data["itens"]:
        lines = [f"- {i['titulo']} ({KIND_LABEL[i['tipo']]}"
                 + (f"; coleções: {', '.join(i['colecoes'])}" if i["colecoes"] else "") + ")"
                 for i in data["itens"][:60]]
        parts.append("[BIBLIOTECA DO USUÁRIO]\n" + "\n".join(lines)
                     + "\nConsulte a biblioteca com as ferramentas biblioteca_* quando o pedido tiver a ver com ela.")
    if data["comandos"]:
        lines = [f'- "{c["nome"]}": {c["instrucao"]}'
                 + (f" (use a coleção: {', '.join(c['colecoes'])})" if c["colecoes"] else "")
                 for c in data["comandos"]]
        parts.append("[COMANDOS PERSONALIZADOS]\nQuando o usuário disser o nome de um comando (ou algo "
                     "muito parecido), faça exatamente o que ele descreve:\n" + "\n".join(lines))
    return "\n\n".join(parts) + "\n" if parts else ""


# ── Migração das versões anteriores (documentos e fontes separados) ─────────
def _migrate_old_data(data: dict) -> None:
    old_docs = config.USER_DIR / "documentos"
    if old_docs.exists():
        for file in sorted(old_docs.glob("*.txt")):
            raw = file.read_bytes()
            try:
                text = (config.CIPHER.decrypt(raw) if config.CIPHER else raw).decode()
            except Exception:  # noqa: BLE001
                continue
            item = _new_item("arquivo", file.stem, file.name, [])
            _write_text(item["id"], text)
            data["itens"].append(item)
    old_sources = config.USER_DIR / "fontes.json"
    if old_sources.exists():
        try:
            for s in json.loads(old_sources.read_text(encoding="utf-8")):
                data["itens"].append(_new_item("noticias", s["site"], f"https://{s['site']}", ["notícias"],
                                               feed=s.get("feed") or ""))
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    if data["itens"]:
        save(data)
