"""Leitura da internet: feeds de notícias (RSS/Atom) e texto de páginas.

- Feed: uma lista das últimas notícias que quase todo portal oferece. A
  Magnólia descobre sozinha o endereço do feed de um site.
- Página: baixamos o HTML e guardamos só o texto (títulos, parágrafos, listas).
"""

import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import requests

from magnolia.readers import extension_for, extract_bytes, html_to_text

HEADERS = {"User-Agent": "Mozilla/5.0 (Magnolia assistente pessoal)"}
COMMON_FEEDS = ("/feed", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml")


def clean_site(site: str) -> str:
    """'https://www.G1.globo.com/economia/' -> 'g1.globo.com/economia'."""
    site = site.strip()
    if "://" not in site:
        site = "https://" + site
    parsed = urlparse(site)
    host = parsed.netloc.lower().removeprefix("www.")
    return (host + parsed.path.rstrip("/")) if host else ""


def normalize_url(url: str) -> str:
    url = url.strip()
    return url if "://" in url else "https://" + url


# ── Feeds ───────────────────────────────────────────────────────────────────
def _looks_like_feed(text: str) -> bool:
    head = text.lstrip()[:500].lower()
    return head.startswith("<?xml") or "<rss" in head or "<feed" in head


def discover_feed(site: str) -> str | None:
    """Acha o endereço do feed de um site (procura o link na página e endereços comuns)."""
    base = f"https://{clean_site(site)}"
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
    xml_text = re.sub(r'\sxmlns(:\w+)?="[^"]+"', "", xml_text)   # tira namespaces
    xml_text = re.sub(r'\s\w+:\w+="[^"]*"', "", xml_text)       # tira atributos com prefixo
    xml_text = re.sub(r"<(/?)\w+:", r"<\1", xml_text)           # <dc:date> -> <date>
    root = ET.fromstring(xml_text.encode())
    items = root.findall(".//item") or root.findall(".//entry")
    return [
        {"titulo": _text(i, "title"), "link": _text(i, "link"),
         "data": _text(i, "pubDate", "updated", "published", "date")[:25]}
        for i in items
    ]


def headlines(site: str, feed: str, subject: str = "", limit: int = 5) -> list[dict]:
    """Últimas notícias de um site: pelo feed, ou pela busca 'site:' se não houver feed."""
    if feed:
        r = requests.get(feed, headers=HEADERS, timeout=10)
        r.raise_for_status()
        news = parse_feed(r.text)
        if subject:
            words = subject.lower().split()
            news = [n for n in news if any(w in n["titulo"].lower() for w in words)]
        return news[:limit]
    from ddgs import DDGS

    results = DDGS().news(f"site:{site} {subject}".strip(), region="br-pt", max_results=limit) or []
    return [{"titulo": r.get("title", ""), "link": r.get("url", ""), "data": (r.get("date") or "")[:10]}
            for r in results]


# ── Páginas e arquivos na internet ──────────────────────────────────────────
def fetch_page(url: str) -> tuple[str, str]:
    """Baixa um link e devolve (título, texto).

    Entende páginas HTML, links diretos para arquivos (PDF, Word, PowerPoint,
    Excel, JSON, CSV, texto...) e links do Google Docs, Planilhas e Apresentações.
    """
    url = normalize_url(url)
    title_hint = None
    doc = re.search(r"docs\.google\.com/document/d/([\w-]+)", url)
    if doc:
        try:  # com o Google conectado, lê pela API (funciona até em documentos privados)
            from magnolia.tools.google_docs_drive import documento_ler

            text = documento_ler.__wrapped__(doc.group(1))
            if not text.startswith("Erro"):
                return "Google Docs", text
        except Exception:  # noqa: BLE001 - tenta como documento público
            pass
        url = f"https://docs.google.com/document/d/{doc.group(1)}/export?format=txt"
        title_hint = "Google Docs"
    sheet = re.search(r"docs\.google\.com/spreadsheets/d/([\w-]+)", url)
    if sheet:
        url = f"https://docs.google.com/spreadsheets/d/{sheet.group(1)}/export?format=csv"
        title_hint = "Google Planilhas"
    slides = re.search(r"docs\.google\.com/presentation/d/([\w-]+)", url)
    if slides:
        url = f"https://docs.google.com/presentation/d/{slides.group(1)}/export/txt"
        title_hint = "Google Apresentações"

    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    content_type = r.headers.get("Content-Type", "text/html").split(";")[0].strip().lower()
    filename = urlparse(r.url or url).path.rsplit("/", 1)[-1] or clean_site(url)
    ext = extension_for(content_type, filename)
    if ext in (".html", ".htm"):
        title, text = html_to_text(r.text)
        return title or title_hint or clean_site(url), text
    # Arquivo (PDF, Word, planilha...): extrai o texto do conteúdo baixado
    return title_hint or filename, extract_bytes(r.content, filename if filename.endswith(ext) else filename + ext)
