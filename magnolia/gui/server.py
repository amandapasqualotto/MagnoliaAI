"""Servidor local da interface: a tela abre numa janela do Edge ou do Chrome.

Por que assim? Janelas "nativas" em Python dependem de componentes do sistema
(como o .NET no Windows) que falham em alguns computadores. Edge ou Chrome
todo computador tem, e em "modo aplicativo" a janela não tem barra de
endereço: parece um programa normal.

Como funciona:
  - GET  /                  -> entrega as páginas da pasta web/
  - POST /api/<método>      -> chama Api.<método>(...) e devolve JSON
  - GET  /eventos           -> eventos ao vivo para a tela (Server-Sent Events)
  - POST /anexar?nome=...   -> recebe um arquivo para anexar

Segurança: o servidor só aceita conexões do próprio computador (127.0.0.1)
e exige um código secreto criado a cada execução. Sem ele, nenhum site
aberto no navegador consegue conversar com a Magnólia.
"""

import json
import mimetypes
import os
import platform
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from magnolia import config

WEB_DIR = Path(__file__).parent / "web"

# Métodos da Api que a tela pode chamar (nada fora desta lista é acessível)
ALLOWED = {
    "list_accounts", "login", "create_account", "logout", "save_settings", "ask",
    "start_voice", "stop_voice", "status", "remove_document", "google_connect", "google_disconnect",
}
MAX_UPLOAD = 30 * 1024 * 1024  # 30 MB


def make_handler(api, token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # não polui o terminal
            pass

        # ── Respostas ───────────────────────────────────────────────────────
        def _json(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            query = parse_qs(urlparse(self.path).query)
            given = self.headers.get("X-Token") or query.get("t", [""])[0]
            return secrets.compare_digest(given, token)

        # ── GET: páginas e eventos ──────────────────────────────────────────
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/eventos":
                return self._events() if self._authorized() else self._json({"erro": "proibido"}, 403)

            file = (WEB_DIR / (unquote(path).lstrip("/") or "index.html")).resolve()
            if not file.is_relative_to(WEB_DIR.resolve()) or not file.is_file():
                return self._json({"erro": "não encontrado"}, 404)
            body = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q = api.subscribe()
            try:
                while True:
                    try:
                        event = q.get(timeout=15)
                        chunk = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    except Exception:  # noqa: BLE001 - fila vazia: manda um "estou vivo"
                        chunk = ": ping\n\n"
                    self.wfile.write(chunk.encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass  # a janela foi fechada
            finally:
                api.unsubscribe(q)

        # ── POST: chamadas da tela ──────────────────────────────────────────
        def do_POST(self):
            if not self._authorized():
                return self._json({"erro": "proibido"}, 403)
            url = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD:
                return self._json({"erro": "Arquivo grande demais (máximo 30 MB)."}, 413)
            body = self.rfile.read(length)

            if url.path == "/anexar":
                return self._attach(parse_qs(url.query).get("nome", ["documento.txt"])[0], body)

            method = url.path.removeprefix("/api/")
            if method not in ALLOWED:
                return self._json({"erro": "método desconhecido"}, 404)
            args = json.loads(body or b"[]")
            try:
                return self._json(getattr(api, method)(*args))
            except Exception as e:  # noqa: BLE001
                return self._json({"ok": False, "erro": str(e)}, 500)

        def _attach(self, name: str, data: bytes):
            folder = Path(tempfile.mkdtemp(prefix="magnolia-"))
            try:
                file = folder / Path(name).name  # só o nome, sem pastas
                file.write_bytes(data)
                return self._json(api.attach_documents([str(file)]))
            finally:
                shutil.rmtree(folder, ignore_errors=True)

    return Handler


def start_server(api, port: int = 0):
    """Liga o servidor numa porta livre. Devolve (servidor, endereço com o código secreto)."""
    token = secrets.token_urlsafe(24)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(api, token))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={token}"
    return server, url


def find_browser() -> str | None:
    """Procura o Edge ou o Chrome instalados."""
    system = platform.system()
    if system == "Windows":
        roots = [os.environ.get(k, "") for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        relative = ["Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"]
        for rel in relative:
            for root in roots:
                if root and (Path(root) / rel).exists():
                    return str(Path(root) / rel)
        return None
    if system == "Darwin":
        for app in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"):
            if Path(app).exists():
                return app
        return None
    for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def open_window(url: str):
    """Abre a janela em modo aplicativo. Devolve o processo (ou None se usou o navegador comum)."""
    browser = find_browser()
    if browser:
        profile = config.DATA_DIR / "janela"  # perfil separado: a janela vira um "programa" à parte
        return subprocess.Popen([
            browser, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1280,820",
            "--no-first-run", "--no-default-browser-check",
        ])
    webbrowser.open(url)
    return None


def run(api):
    server, url = start_server(api)
    print("✿ Magnólia aberta. Feche a janela (ou aperte Ctrl+C aqui) para sair.")
    window = open_window(url)
    try:
        started = time.monotonic()
        if window:
            window.wait()  # fecha tudo quando a janela fecha
        if not window or time.monotonic() - started < 5:
            # Navegador comum, ou a janela foi entregue a um Edge/Chrome que já estava aberto:
            # não dá para saber quando ela fecha, então espera o Ctrl+C.
            print(f"Se a janela não abriu, copie no navegador: {url}")
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        api.assistant.stop_voice()
        server.shutdown()
