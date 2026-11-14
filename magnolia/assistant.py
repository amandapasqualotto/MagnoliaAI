"""O "maestro" da Magnólia: junta o modo texto, o modo voz e o "Ei, Magnólia".

A interface gráfica (e o terminal) só conversam com esta classe.
"""

import asyncio
import threading
import time
import traceback

from magnolia import config
from magnolia.voice import VoiceSession, explain_voice_error

IDLE_SECONDS = 40  # depois de chamada, volta a "dormir" após 40 s de silêncio


class Assistant:
    def __init__(self, on_event=None):
        self.on_event = on_event or (lambda name, data: None)
        self._brain = None
        self._session: VoiceSession | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._text_lock = threading.Lock()  # uma pergunta de texto por vez

    def emit(self, name: str, **data):
        self.on_event(name, data)

    # ── Texto ───────────────────────────────────────────────────────────────
    def ask(self, text: str) -> str | None:
        """Responde uma mensagem digitada.

        Se uma conversa de voz estiver acontecendo, a mensagem entra nela e a
        resposta vem falada (devolve None). Senão, responde por texto.
        """
        if self._session is not None:
            self._session.send_text(text)
            return None
        with self._text_lock:
            if self._brain is None:
                from magnolia.brain import Brain  # só carrega quando precisa

                self._brain = Brain()
            return self._brain.ask(text)

    def refresh_prompt(self):
        """Recria a conversa de texto para ela ver informações novas (ex.: documentos)."""
        if self._brain is not None:
            from magnolia.brain import Brain

            history = self._brain.chat.get_history()
            self._brain = Brain()
            self._brain.chat = self._brain._new_chat(history)

    def reset(self):
        """Esquece a conversa atual (usado ao trocar de conta ou de configuração)."""
        self.stop_voice()
        self._brain = None

    # ── Voz ─────────────────────────────────────────────────────────────────
    @property
    def voice_active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start_voice(self, wake_word: bool = True, headphones: bool = False):
        if self.voice_active:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._voice_loop, args=(wake_word, headphones), daemon=True)
        self._thread.start()

    def stop_voice(self):
        self._stop.set()
        if self._session:
            self._session.stop()

    def _run_session(self, wake_word: bool, headphones: bool, style: str) -> BaseException | None:
        """Roda uma conversa de voz. Devolve o erro, se a conexão caiu."""
        self._session = VoiceSession(
            on_event=self.on_event, headphones=headphones,
            idle_timeout=IDLE_SECONDS if wake_word else None, greet=wake_word, style=style,
        )
        try:
            asyncio.run(self._session.run())
            return None
        except BaseException as e:  # noqa: BLE001 - inclui o ExceptionGroup do TaskGroup
            if isinstance(e, KeyboardInterrupt):
                raise
            print(f"[Magnólia] a conversa de voz caiu (modelo {self._session.model}):", flush=True)
            traceback.print_exception(e)  # detalhes completos no terminal / data/magnolia.log
            return e
        finally:
            self._session = None

    def _voice_loop(self, wake_word: bool, headphones: bool):
        style = config.VOICE_STYLE
        failures = 0
        try:
            while not self._stop.is_set():
                if wake_word:
                    from magnolia.wakeword import wait_for_wake_word

                    self.emit("estado", estado="dormindo")
                    heard = wait_for_wake_word(self._stop, on_status=lambda t: self.emit("aviso", texto=t),
                                               on_level=lambda v: self.emit("nivel", valor=round(v, 3)))
                    if not heard:
                        break
                    # Retorno imediato: um "plim" e a flor acende, enquanto a conexão com o Gemini abre
                    self.emit("acordou")
                    self.emit("estado", estado="ouvindo")
                error = self._run_session(wake_word, headphones, style)
                if error is None:
                    failures = 0
                    if not wake_word:
                        break
                    continue
                failures += 1
                message = explain_voice_error(error)
                if failures >= 2 and style == "natural":
                    # A voz natural falhou duas vezes seguidas: passa para a voz rápida
                    style, failures = "rapida", 0
                    self.emit("aviso", texto="A voz natural deu problema; mudei para a voz rápida.")
                if failures >= 3:
                    self.emit("erro", texto=f"A voz parou depois de várias tentativas. {message}")
                    break
                self.emit("erro", texto=message + (" Voltando a esperar 'Ei, Magnólia'." if wake_word
                                                     else " Reconectando..."))
                time.sleep(1)
        except Exception as e:  # noqa: BLE001
            print(f"[Magnólia] erro na voz: {e!r}", flush=True)
            traceback.print_exc()
            self.emit("erro", texto=f"Problema no modo voz: {explain_voice_error(e)}")
        finally:
            self._session = None
            self.emit("estado", estado="parada")

