"""Sites salvos nos favoritos do navegador (Chrome, Edge ou Brave).

O Google não tem uma API pública para os favoritos da conta, mas o
navegador guarda uma cópia deles num arquivo JSON no seu computador.
A Magnólia só LÊ esse arquivo; nunca altera nada.
"""

import json
import os
import platform
import webbrowser
from difflib import SequenceMatcher
from pathlib import Path

from magnolia.tools import tool
from magnolia.wakeword import _normalize


def _browser_folders() -> list[Path]:
    """Pastas onde Chrome, Edge e Brave guardam os dados em cada sistema."""
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        return [base / "Google/Chrome/User Data", base / "Microsoft/Edge/User Data",
                base / "BraveSoftware/Brave-Browser/User Data"]
    if system == "Darwin":
        base = home / "Library/Application Support"
        return [base / "Google/Chrome", base / "Microsoft Edge", base / "BraveSoftware/Brave-Browser"]
    base = home / ".config"
    return [base / "google-chrome", base / "microsoft-edge", base / "BraveSoftware/Brave-Browser"]


def _walk(node: dict, folder: str, out: list[dict]):
    if node.get("type") == "url":
        out.append({"nome": node.get("name", ""), "url": node.get("url", ""), "pasta": folder})
    for child in node.get("children", []):
        _walk(child, node.get("name", folder) if node.get("type") == "folder" else folder, out)


def load_bookmarks(folders: list[Path] | None = None) -> list[dict]:
    """Lê os favoritos de todos os perfis de todos os navegadores encontrados."""
    found, seen = [], set()
    for base in folders or _browser_folders():
        for file in sorted(base.glob("*/Bookmarks")):  # Default, Profile 1, Profile 2...
            try:
                roots = json.loads(file.read_text(encoding="utf-8")).get("roots", {})
            except (OSError, json.JSONDecodeError):
                continue
            items: list[dict] = []
            for root in roots.values():
                if isinstance(root, dict):
                    _walk(root, root.get("name", ""), items)
            for item in items:
                if item["url"] not in seen:
                    seen.add(item["url"])
                    found.append(item)
    return found


def _score(term: str, item: dict) -> float:
    term = _normalize(term).strip()
    text = _normalize(f"{item['nome']} {item['url']} {item['pasta']}")
    if term in text:
        return 1.0
    return max((SequenceMatcher(None, term, w).ratio() for w in text.split()), default=0.0)


def search_bookmarks(term: str, bookmarks: list[dict] | None = None, limit: int = 8) -> list[dict]:
    bookmarks = load_bookmarks() if bookmarks is None else bookmarks
    ranked = sorted(bookmarks, key=lambda b: _score(term, b), reverse=True)
    return [b for b in ranked[:limit] if _score(term, b) >= 0.6]


@tool
def procurar_favoritos(termo: str) -> str:
    """Procura sites salvos nos favoritos do navegador do usuário (Chrome, Edge ou Brave).

    Args:
        termo: parte do nome, do endereço ou da pasta do favorito, por exemplo "portal da faculdade".
    """
    results = search_bookmarks(termo)
    if not results:
        return f"Não encontrei favoritos com '{termo}'."
    return "\n".join(f"{b['nome']} ({b['pasta']}): {b['url']}" for b in results)


@tool
def abrir_favorito(nome: str) -> str:
    """Abre no navegador um site que o usuário salvou nos favoritos.

    Args:
        nome: nome ou parte do nome do favorito, por exemplo "AVA UFMS".
    """
    results = search_bookmarks(nome, limit=1)
    if not results:
        return f"Não encontrei '{nome}' nos favoritos."
    webbrowser.open(results[0]["url"])
    return f"Abri '{results[0]['nome']}' ({results[0]['url']})."
