"""O que a tela da Magnólia pode pedir para o Python fazer.

A tela é feita em HTML, CSS e JavaScript (pasta web/). O server.py entrega
essas páginas e repassa os pedidos da tela para os métodos desta classe:

  JavaScript -> Python:  api.login(...)          (vira POST /api/login)
  Python -> JavaScript:  window.onMagnolia({...}) (eventos enviados ao vivo: voz, estado, lembretes)
"""

import queue
import threading
from pathlib import Path

import psutil

from magnolia import accounts, config, documents, google_auth
from magnolia.assistant import Assistant
from magnolia.tools import fontes, lembretes


def friendly_error(e: Exception) -> str:
    """Traduz os erros mais comuns do Gemini para algo que dá para resolver."""
    text = str(e)
    if "API_KEY_INVALID" in text or "API key not valid" in text:
        return ("Sua chave do Gemini não é válida. Copie de novo em aistudio.google.com/apikey "
                "e troque nas configurações.")
    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        return "A cota grátis do Gemini acabou por agora. Espere alguns minutos e tente de novo."
    if "404" in text or "NOT_FOUND" in text:
        return "Nenhum modelo do Gemini disponível para a sua chave respondeu. Feche e abra a Magnólia de novo."
    if "getaddrinfo" in text or "ConnectError" in text or "timed out" in text:
        return "Sem conexão com a internet (ou o Gemini não respondeu). Confira a internet e tente de novo."
    return f"Não consegui falar com o Gemini: {text[:300]}"


class Api:
    """Tudo o que a tela pode pedir para o Python fazer."""

    def __init__(self):
        self.account: accounts.Account | None = None
        self.assistant = Assistant(on_event=self._send_event)
        self._listeners: list[queue.Queue] = []  # uma fila por janela aberta
        self._lock = threading.Lock()
        lembretes.on_fire = lambda texto: self._send_event("lembrete", {"texto": texto})

    # ── Eventos ao vivo para a tela ─────────────────────────────────────────
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._listeners.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            if q in self._listeners:
                self._listeners.remove(q)

    def _send_event(self, name: str, data: dict):
        with self._lock:
            for q in self._listeners:
                q.put({"tipo": name, **data})

    def _session_info(self) -> dict:
        return {
            "ok": True,
            "nome": self.account.name,
            "usuario": self.account.username,
            "config": self.account.settings,
            "google": google_auth.is_connected(),
            "vozes": config.FEMALE_VOICES,
            "fontes": [s["site"] for s in fontes.load_sources()],
        }

    # ── Contas ──────────────────────────────────────────────────────────────
    def list_accounts(self):
        return accounts.list_accounts()

    def login(self, username, password):
        try:
            self.account = accounts.login(username, password)
        except accounts.AccountError as e:
            return {"ok": False, "erro": str(e)}
        self.account.activate()
        return self._session_info()

    def create_account(self, form):
        try:
            self.account = accounts.create_account(
                form.get("usuario", ""), form.get("senha", ""), form.get("nome", ""),
                form.get("chave", ""), form.get("cidade", ""),
            )
        except accounts.AccountError as e:
            return {"ok": False, "erro": str(e)}
        self.account.activate()
        return self._session_info()

    def logout(self):
        self.assistant.reset()
        self.account = None
        config.use_user(config.DATA_DIR / "dev", "", "", "", "")
        return True

    def save_settings(self, form):
        s = self.account.settings
        for key in ("cidade", "voz", "fone", "ei_magnolia"):
            if key in form:
                s[key] = form[key]
        if form.get("chave"):
            self.account.set_api_key(form["chave"])
        if "fontes" in form:
            fontes.set_sites(form["fontes"])
        self.account.save()
        self.account.activate()
        self.assistant.reset()  # recomeça com a voz e a cidade novas
        return self._session_info()

    # ── Conversa ────────────────────────────────────────────────────────────
    def ask(self, text):
        try:
            answer = self.assistant.ask(text)
            return {"ok": True, "resposta": answer}  # None = resposta virá por voz
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "erro": friendly_error(e)}

    def start_voice(self):
        s = self.account.settings
        self.assistant.start_voice(wake_word=s.get("ei_magnolia", True), headphones=s.get("fone", False))
        return True

    def stop_voice(self):
        self.assistant.stop_voice()
        return True

    # ── Painéis ─────────────────────────────────────────────────────────────
    def status(self):
        battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        return {
            "cpu": psutil.cpu_percent(),
            "ram": psutil.virtual_memory().percent,
            "bateria": round(battery.percent) if battery else None,
            "lembretes": lembretes.pending(),
            "documentos": documents.names(),
        }

    # ── Documentos ──────────────────────────────────────────────────────────
    def attach_documents(self, paths):
        """Anexa os arquivos (a tela envia o arquivo e o server.py salva antes de chamar aqui)."""
        added, errors = [], []
        for path in paths:
            try:
                added.append(documents.add(path))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{Path(path).name}: {e}")
        if added:
            self.assistant.refresh_prompt()  # para ela saber dos documentos novos
        return {"anexados": added, "erros": errors, "documentos": documents.names()}

    def remove_document(self, name):
        documents.remove(name)
        self.assistant.refresh_prompt()
        return documents.names()

    def google_connect(self):
        try:
            msg = google_auth.connect()
        except Exception as e:  # noqa: BLE001
            msg = f"Não consegui conectar: {e}"
        return {"mensagem": msg, "google": google_auth.is_connected()}

    def google_disconnect(self):
        google_auth.disconnect()
        return {"google": False}


def run():
    from magnolia.gui.server import run as run_server

    run_server(Api())
