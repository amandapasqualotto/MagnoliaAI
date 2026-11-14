"""Janela da Magnólia (versão desktop).

A tela é feita em HTML, CSS e JavaScript (pasta web/) e aberta numa janela
nativa pelo pywebview. Os dois lados conversam assim:

  JavaScript -> Python:  window.pywebview.api.login(...)   (métodos da classe Api)
  Python -> JavaScript:  window.onMagnolia({...})         (eventos: voz, estado, lembretes)
"""

import json
from pathlib import Path

import psutil

from magnolia import accounts, config, documents, google_auth
from magnolia.assistant import Assistant
from magnolia.tools import lembretes

WEB_DIR = Path(__file__).parent / "web"


class Api:
    """Tudo o que a tela pode pedir para o Python fazer."""

    def __init__(self):
        self.window = None
        self.account: accounts.Account | None = None
        self.assistant = Assistant(on_event=self._send_event)
        lembretes.on_fire = lambda texto: self._send_event("lembrete", {"texto": texto})

    def _send_event(self, name: str, data: dict):
        if self.window:
            payload = json.dumps({"tipo": name, **data}, ensure_ascii=False)
            self.window.evaluate_js(f"window.onMagnolia && window.onMagnolia({payload})")

    def _session_info(self) -> dict:
        return {
            "ok": True,
            "nome": self.account.name,
            "usuario": self.account.username,
            "config": self.account.settings,
            "google": google_auth.is_connected(),
            "vozes": config.FEMALE_VOICES,
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
            return {"ok": False, "erro": f"Não consegui falar com o Gemini: {e}"}

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
    def attach_documents(self, paths=None):
        """Abre a janela de escolher arquivo e anexa os documentos escolhidos."""
        if paths is None:
            import webview

            dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
            paths = self.window.create_file_dialog(
                dialog, allow_multiple=True,
                file_types=("Documentos (*.pdf;*.docx;*.txt;*.md;*.csv)", "Todos os arquivos (*.*)"),
            ) or []
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
    import webview

    api = Api()
    api.window = webview.create_window(
        "Magnólia", str(WEB_DIR / "index.html"), js_api=api,
        width=1280, height=800, min_size=(960, 640), background_color="#24101F",
    )
    try:
        webview.start()
    finally:
        api.assistant.stop_voice()
