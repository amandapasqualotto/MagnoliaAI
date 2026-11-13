"""Documentos anexados: PDFs, Word e textos que a Magnólia pode consultar.

Ao anexar, extraímos o texto do arquivo e guardamos na pasta da sua conta
(data/usuarios/<você>/documentos/), criptografado com a sua senha.
Assim ela pode responder "o que tenho no cronograma amanhã?".
"""

import re
from pathlib import Path

from magnolia import config

SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".csv"}
MAX_CHARS = 200_000  # limite por documento (~100 páginas)


def _folder() -> Path:
    folder = config.USER_DIR / "documentos"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def extract_text(path: Path) -> str:
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


def _write(file: Path, text: str):
    data = text.encode()
    file.write_bytes(config.CIPHER.encrypt(data) if config.CIPHER else data)


def _read(file: Path) -> str:
    data = file.read_bytes()
    return (config.CIPHER.decrypt(data) if config.CIPHER else data).decode()


def _slug(name: str) -> str:
    return re.sub(r"[^\w\-. ]", "", name).strip() or "documento"


def add(path: str | Path) -> str:
    """Anexa um arquivo. Devolve o nome com que ele ficou salvo."""
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Formato não suportado: {path.suffix}. Use PDF, Word (.docx) ou texto.")
    text = extract_text(path).strip()
    if not text.replace("[página", "").strip(" ]0123456789\n"):
        raise ValueError("Não encontrei texto nesse arquivo (pode ser um PDF escaneado, só com imagem).")
    name = _slug(path.stem)
    _write(_folder() / f"{name}.txt", text[:MAX_CHARS])
    return name


def remove(name: str) -> bool:
    file = _folder() / f"{_slug(name)}.txt"
    if file.exists():
        file.unlink()
        return True
    return False


def names() -> list[str]:
    return sorted(f.stem for f in _folder().glob("*.txt"))


def find(name: str) -> str | None:
    """Acha um documento pelo nome (ou parte do nome)."""
    name_l = name.lower()
    for doc in names():
        if doc.lower() == name_l:
            return doc
    for doc in names():
        if name_l in doc.lower():
            return doc
    return None


def read(name: str) -> str:
    return _read(_folder() / f"{name}.txt")


def for_prompt() -> str:
    docs = names()
    if not docs:
        return ""
    return ("[DOCUMENTOS ANEXADOS PELO USUÁRIO]\n" + "\n".join(f"- {d}" for d in docs)
            + "\nConsulte-os com as ferramentas de documento quando o pedido tiver a ver com eles.\n")
