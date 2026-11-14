"""Leitores de arquivos: transformam PDF, Word, PowerPoint, Excel, HTML, JSON...
em texto que a Magnólia consegue consultar.
"""

import json
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path

SUPPORTED = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".txt", ".md", ".csv", ".json", ".xml"}

# Tipo de conteúdo informado pelo site -> extensão do arquivo
CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/html": ".html", "application/xhtml+xml": ".html",
    "application/json": ".json", "text/csv": ".csv", "text/markdown": ".md",
    "text/plain": ".txt", "application/xml": ".xml", "text/xml": ".xml",
}


def extension_for(content_type: str, filename: str = "") -> str:
    """Descobre a extensão pelo nome do arquivo ou, se não der, pelo tipo de conteúdo."""
    suffix = Path(filename).suffix.lower()
    if suffix in SUPPORTED:
        return suffix
    return CONTENT_TYPES.get(content_type, ".html")


# ── HTML ────────────────────────────────────────────────────────────────────
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


# ── Arquivos ────────────────────────────────────────────────────────────────
def _pdf(path: Path) -> str:
    from pypdf import PdfReader

    pages = PdfReader(str(path)).pages
    return "\n\n".join(f"[página {i}]\n{p.extract_text() or ''}" for i, p in enumerate(pages, 1))


def _docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:  # cronogramas costumam estar em tabelas
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(parts)


def _pptx(path: Path) -> str:
    from pptx import Presentation

    slides = []
    for i, slide in enumerate(Presentation(str(path)).slides, 1):
        texts = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame and shape.text_frame.text]
        slides.append(f"[slide {i}]\n" + "\n".join(texts))
    return "\n\n".join(slides)


def _xlsx(path: Path, max_rows: int = 2000) -> str:
    from openpyxl import load_workbook

    book = load_workbook(str(path), read_only=True, data_only=True)
    parts = []
    for sheet in book.worksheets:
        rows = []
        for row in sheet.iter_rows(values_only=True, max_row=max_rows):
            if any(cell is not None for cell in row):
                rows.append(" | ".join("" if cell is None else str(cell) for cell in row))
        parts.append(f"[aba {sheet.title}]\n" + "\n".join(rows))
    book.close()
    return "\n\n".join(parts)


def extract_file_text(path: Path) -> str:
    """Texto de um arquivo, de acordo com a extensão."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf(path)
    if suffix == ".docx":
        return _docx(path)
    if suffix == ".pptx":
        return _pptx(path)
    if suffix == ".xlsx":
        return _xlsx(path)
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if suffix in (".html", ".htm"):
        title, text = html_to_text(raw)
        return f"{title}\n\n{text}" if title else text
    if suffix == ".json":
        try:
            return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return raw
    if suffix == ".xml":
        return re.sub(r"\s+\n", "\n", re.sub(r"<[^>]+>", " ", raw))
    return raw


def extract_bytes(data: bytes, filename: str) -> str:
    """Texto de um arquivo que veio da internet (salva num arquivo temporário e lê)."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / Path(filename).name
        path.write_bytes(data)
        return extract_file_text(path)
