"""Fontes de notícias favoritas: os sites que a Magnólia consulta primeiro.

Para cada site, procuramos o "feed" (RSS ou Atom): uma lista das últimas
notícias que quase todo portal de notícias oferece. Se o site não tiver
feed, pesquisamos as notícias dele no DuckDuckGo (busca "site:...").
A lista fica em data/usuarios/<você>/fontes.json.
"""

import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import requests

from magnolia import config
from magnolia.tools import tool

HEADERS = {"User-Agent": "Mozilla/5.0 (Magnolia assistente pessoal)"}
COMMON_FEEDS = ("/feed", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml")


# ── Lista de fontes ─────────────────────────────────────────────────────────
def _file():
    return config.USER_DIR / "fontes.json"


def load_sources() -> list[dict]:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def save_sources(sources: list[dict]) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_site(site: str) -> str:
    """'https://www.g1.globo.com/economia/' -> 'g1.globo.com/economia'."""
    site = site.strip().lower()
    if "://" not in site:
        site = "https://" + site
    parsed = urlparse(site)
    host = parsed.netloc.removeprefix("www.")
    return (host + parsed.path.rstrip("/")) if host else ""


def set_sites(sites: list[str]) -> list[str]:
    """Troca a lista inteira (usado pela tela de configurações)."""
    old = {s["site"]: s for s in load_sources()}
    new = []
    for raw in sites:
        site = clean_site(raw)
        if site and site not in [s["site"] for s in new]:
            new.append(old.get(site, {"site": site, "feed": None}))
    save_sources(new)
    return [s["site"] for s in new]


# ── Feeds ───────────────────────────────────────────────────────────────────
def _looks_like_feed(text: str) -> bool:
    head = text.lstrip()[:500].lower()
    return head.startswith("<?xml") or "<rss" in head or "<feed" in head


def discover_feed(site: str) -> str | None:
    """Acha o endereço do feed de um site (procura o link na página e endereços comuns)."""
    base = f"https://{site}"
    try:
        page = requests.get(base, headers=HEADERS, timeout=10)
        if _looks_like_feed(page.text):
            return base
        for tag in re.findall(r"<link\b[^>]*>", page.text, flags=re.I):
            if re.search(r"application/(rss|atom)\+xml", tag, flags=re.I):
                href = re.search(r'href=["\']([^"\']+)', tag, flags=re.I)
                if href:
                    return urljoin(page.url, href.group(1))
    except requests.RequestException:
        pass
    for path in COMMON_FEEDS:
        try:
            r = requests.get(base + path, headers=HEADERS, timeout=8)
            if r.ok and _looks_like_feed(r.text):
                return r.url
        except requests.RequestException:
            continue
    return None


def _text(node, *names) -> str:
    for name in names:
        found = node.find(name)
        if found is not None:
            return (found.text or found.get("href") or "").strip()
    return ""


def parse_feed(xml_text: str) -> list[dict]:
    """Lê um feed RSS ou Atom e devolve [{titulo, link, data}]."""
    xml_text = re.sub(r'\sxmlns(:\w+)?="[^"]+"', "", xml_text, count=0)  # tira namespaces
    xml_text = re.sub(r'\s\w+:\w+="[^"]*"', "", xml_text)       # tira atributos com prefixo
    xml_text = re.sub(r"<(/?)\w+:", r"<\1", xml_text)           # <dc:date> -> <date>
    root = ET.fromstring(xml_text.encode())
    items = root.findall(".//item") or root.findall(".//entry")
    return [
        {"titulo": _text(i, "title"), "link": _text(i, "link"),
         "data": _text(i, "pubDate", "updated", "published", "date")[:25]}
        for i in items
    ]


def _search_fallback(site: str, subject: str, limit: int) -> list[dict]:
    from ddgs import DDGS

    results = DDGS().news(f"site:{site} {subject}".strip(), region="br-pt", max_results=limit) or []
    return [{"titulo": r.get("title", ""), "link": r.get("url", ""), "data": (r.get("date") or "")[:10]}
            for r in results]


def headlines(source: dict, subject: str, limit: int) -> list[dict]:
    if source.get("feed") is None:
        source["feed"] = discover_feed(source["site"]) or ""  # "" = já procurei e não tem
    if source["feed"]:
        r = requests.get(source["feed"], headers=HEADERS, timeout=10)
        r.raise_for_status()
        news = parse_feed(r.text)
        if subject:
            words = subject.lower().split()
            news = [n for n in news if any(w in n["titulo"].lower() for w in words)]
        return news[:limit]
    return _search_fallback(source["site"], subject, limit)


# ── Ferramentas ─────────────────────────────────────────────────────────────
@tool
def noticias_das_minhas_fontes(assunto: str = "", por_site: int = 5) -> str:
    """Traz as últimas notícias dos sites favoritos do usuário.

    Use PRIMEIRO sempre que pedirem notícias, manchetes ou "o que está em alta",
    se o usuário tiver fontes cadastradas.

    Args:
        assunto: filtra por um tema (por exemplo "economia"). Vazio = manchetes gerais.
        por_site: quantas notícias trazer de cada site (padrão 5).
    """
    sources = load_sources()
    if not sources:
        return "O usuário ainda não cadastrou sites de notícias. Use pesquisar_noticias."
    blocks = []
    for source in sources:
        try:
            news = headlines(source, assunto, por_site)
            lines = [f"- {n['titulo']} ({n['data']})" for n in news] or ["- (nada recente sobre isso)"]
        except Exception as e:  # noqa: BLE001
            lines = [f"- não consegui ler este site agora ({e.__class__.__name__})"]
        blocks.append(f"[{source['site']}]\n" + "\n".join(lines))
    save_sources(sources)  # guarda os feeds descobertos para a próxima vez
    return "\n\n".join(blocks)


@tool
def adicionar_fonte(site: str) -> str:
    """Adiciona um site à lista de fontes de notícias favoritas do usuário.

    Args:
        site: endereço do site, por exemplo "g1.globo.com" ou "folha.uol.com.br".
    """
    site = clean_site(site)
    if not site:
        return "Não entendi o endereço do site."
    sources = load_sources()
    if site in [s["site"] for s in sources]:
        return f"{site} já está nas fontes."
    sources.append({"site": site, "feed": None})
    save_sources(sources)
    return f"{site} adicionado às fontes de notícias."


@tool
def remover_fonte(site: str) -> str:
    """Remove um site da lista de fontes de notícias.

    Args:
        site: endereço ou parte do nome do site.
    """
    term = clean_site(site) or site.lower()
    sources = load_sources()
    kept = [s for s in sources if term not in s["site"]]
    save_sources(kept)
    if len(kept) == len(sources):
        return "Esse site não estava nas fontes."
    return f"Removido: {len(sources) - len(kept)} site(s)."


@tool
def listar_fontes() -> str:
    """Lista os sites de notícias favoritos do usuário."""
    sources = load_sources()
    return "\n".join(s["site"] for s in sources) if sources else "Nenhuma fonte cadastrada."
