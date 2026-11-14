"""O que a tela da Magnólia pode pedir para o Python fazer.

A tela é feita em HTML, CSS e JavaScript (pasta web/). O server.py entrega
essas páginas e repassa os pedidos da tela para os métodos desta classe:

  JavaScript -> Python:  api.login(...)          (vira POST /api/login)
  Python -> JavaScript:  window.onMagnolia({...}) (eventos enviados ao vivo: voz, estado, lembretes)
"""

import queue
import re
import threading
from pathlib import Path

import psutil

from magnolia import accounts, alerts, config, google_auth, library, spotify_api
from magnolia.assistant import Assistant
from magnolia.tools import lembretes, timers


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
    if "getaddrinfo" in text or "ConnectError" in text or "timed out" in text.lower() or "Timeout" in text:
        return "Sem conexão com a internet (ou o Gemini não respondeu). Confira a internet e tente de novo."
    return f"Não consegui falar com o Gemini: {text[:300]}"


class Api:
    """Tudo o que a tela pode pedir para o Python fazer."""

    def __init__(self):
        self.account: accounts.Account | None = None
        self.assistant = Assistant(on_event=self._send_event)
        self._listeners: list[queue.Queue] = []  # uma fila por janela aberta
        self._lock = threading.Lock()
        # "categoria" (e não "tipo"): o campo "tipo" já é o nome do evento
        alerts.listener = lambda categoria, texto: self._send_event("alarme", {"categoria": categoria, "texto": texto})
        alerts.on_change = lambda estado: self._send_event("timers", estado)

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
            "spotify": spotify_api.is_connected(),
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
        for key in ("cidade", "voz", "fone", "ei_magnolia", "spotify_client_id", "estilo_voz"):
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
            print(f"[Magnólia] erro ao responder: {e}", flush=True)
            return {"ok": False, "erro": friendly_error(e)}

    def start_voice(self):
        s = self.account.settings
        self.assistant.start_voice(wake_word=s.get("ei_magnolia", True), headphones=s.get("fone", False))
        return True

    def stop_voice(self):
        self.assistant.stop_voice()
        return True

    def beep(self):
        """Toca o alarme pelo Windows (quando o navegador bloqueia o som da janela)."""
        alerts.beep_async()
        return True

    def cancel_timer(self, timer_id):
        timers.cancel(timer_id)
        return timers.state()

    def stop_stopwatch(self):
        timers.stop_stopwatch()
        return timers.state()

    def open_url(self, url):
        """Abre um link no navegador padrão (onde a pessoa já está logada no Google)."""
        import webbrowser

        if not str(url).startswith(("http://", "https://")):
            return False
        webbrowser.open(url)
        return True

    # ── Painéis ─────────────────────────────────────────────────────────────
    def status(self):
        battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        return {
            "cpu": psutil.cpu_percent(),
            "ram": psutil.virtual_memory().percent,
            "bateria": round(battery.percent) if battery else None,
            "lembretes": lembretes.pending(),
            "timers": timers.state(),
            "biblioteca": self.library_state(),
        }

    # ── Biblioteca ──────────────────────────────────────────────────────────
    def library_state(self):
        data = library.load()
        return {"itens": data["itens"], "comandos": data["comandos"], "colecoes": library.collections()}

    def _changed(self):
        self.assistant.refresh_prompt()  # para ela saber das novidades na biblioteca
        return self.library_state()

    def add_files(self, paths, collections=""):
        """Adiciona arquivos (a tela envia o arquivo e o server.py salva antes de chamar aqui)."""
        added, errors = [], []
        for path in paths:
            try:
                added.append(library.add_file(path, collections)["titulo"])
            except Exception as e:  # noqa: BLE001
                errors.append(f"{Path(path).name}: {e}")
        return {"adicionados": added, "erros": errors, "biblioteca": self._changed()}

    def add_link(self, text, collections="", kind="auto"):
        """Adiciona um ou vários links (separados por linha, espaço ou vírgula)."""
        urls = [u for u in re.split(r"[\s,]+", text or "") if "." in u]
        if not urls:
            return {"ok": False, "erro": "Cole pelo menos um link."}
        added, errors = [], []
        for url in urls:
            try:
                added.append(library.add_link(url, collections, kind))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{url}: {e}")
        if not added:
            return {"ok": False, "erro": "Não consegui adicionar: " + " · ".join(errors)}
        return {"ok": True, "itens": added, "erros": errors, "biblioteca": self._changed()}

    def remove_item(self, item_id):
        library.remove(item_id)
        return self._changed()

    def organize_item(self, item_id, collections):
        library.set_collections(item_id, collections)
        return self._changed()

    def remove_command(self, name):
        library.remove_command(name)
        return self._changed()

    def google_connect(self):
        try:
            msg = google_auth.connect()
        except Exception as e:  # noqa: BLE001
            msg = f"Não consegui conectar: {e}"
        return {"mensagem": msg, "google": google_auth.is_connected()}

    def google_disconnect(self):
        google_auth.disconnect()
        return {"google": False}

    def spotify_connect(self, client_id=""):
        if client_id:
            self.save_settings({"spotify_client_id": client_id.strip()})
        try:
            msg = spotify_api.connect()
        except Exception as e:  # noqa: BLE001
            msg = f"Não consegui conectar: {e}"
        return {"mensagem": msg, "spotify": spotify_api.is_connected()}

    def spotify_disconnect(self):
        spotify_api.disconnect()
        return {"spotify": False}


def run():
    from magnolia.gui.server import run as run_server

    run_server(Api())
