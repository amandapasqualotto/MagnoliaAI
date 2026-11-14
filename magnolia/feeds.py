"""Leitura da internet: feeds de notícias (RSS/Atom) e texto de páginas.

- Feed: uma lista das últimas notícias que quase todo portal oferece. A
  Magnólia descobre sozinha o endereço do feed de um site.
- Página: baixamos o HTML e guardamos só o texto (títulos, parágrafos, listas).
"""

import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

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


# ── Páginas ─────────────────────────────────────────────────────────────────
class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"}
    BLOCKS = {"p", "h1", "h2", "h3", "h4", "li", "td", "th", "blockquote", "pre", "div", "br", "tr"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    """Devolve (título, texto) de uma página HTML."""
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return parser.title.strip(), "\n".join(line for line in lines if len(line) > 1)


def fetch_page(url: str) -> tuple[str, str]:
    """Baixa uma página e devolve (título, texto). Entende links do Google Docs."""
    url = normalize_url(url)
    doc = re.search(r"docs\.google\.com/document/d/([\w-]+)", url)
    if doc:
        try:  # com o Google conectado, lê pela API (funciona até em documentos privados)
            from magnolia.tools.google_docs_drive import documento_ler

            text = documento_ler.__wrapped__(doc.group(1))
            return "Google Docs", text
        except Exception:  # noqa: BLE001 - tenta como documento público
            url = f"https://docs.google.com/document/d/{doc.group(1)}/export?format=txt"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    if "html" not in r.headers.get("Content-Type", "html"):
        return urlparse(url).path.rsplit("/", 1)[-1] or url, r.text
    return html_to_text(r.text)
