"""Modo voz: conversa falada em tempo real com a Gemini Live API.

Cinco tarefas rodam ao mesmo tempo (asyncio):
  1. listen_mic   -> captura o microfone em pedacinhos de áudio
  2. send_audio   -> envia esses pedaços para o Gemini
  3. receive      -> recebe a voz da Magnólia, as transcrições e os pedidos de ferramenta
  4. play_audio   -> toca a voz da Magnólia nas caixas de som
  5. watchdog     -> encerra a conversa se ficar em silêncio (ou se mandarem parar)

A sessão avisa o que está acontecendo por "eventos", que o terminal ou a
interface gráfica mostram como quiserem:
  ("texto",  {"quem": "Você" | "Magnólia", "texto": "..."})
  ("estado", {"estado": "ouvindo" | "pensando" | "falando"})
  ("nivel",  {"valor": 0.0 a 1.0})         # volume, para animar o reator
  ("ferramenta", {"nome": "...", "args": {...}})

Dica: use fone de ouvido. Sem fone, o microfone fica mudo enquanto a
Magnólia fala, para ela não ouvir a própria voz e responder a si mesma.
"""

import asyncio
import math
import struct
import threading
import time

from google.genai import types

from magnolia import config
from magnolia.models import make_client, pick_live_model
from magnolia.prompt import build_system_prompt
from magnolia.tools import load_tools, run_tool

MIC_RATE = 16_000      # o Gemini espera áudio de entrada em 16 kHz
SPEAKER_RATE = 24_000  # e devolve áudio em 24 kHz
CHUNK = 1024           # amostras por pedaço (~64 ms de áudio)


class _StopSession(Exception):
    """Usada internamente para encerrar todas as tarefas de uma vez."""


def audio_level(data: bytes) -> float:
    """Volume (0 a 1) de um pedaço de áudio PCM 16 bits. Usado para animar a tela."""
    count = len(data) // 2
    if count == 0:
        return 0.0
    samples = struct.unpack(f"<{count}h", data[: count * 2])
    rms = math.sqrt(sum(s * s for s in samples[::4]) / max(1, len(samples[::4])))
    return min(1.0, rms / 6000)


class VoiceSession:
    def __init__(self, on_event=None, headphones: bool = False, idle_timeout: float | None = None,
                 greet: bool = False):
        if not config.GEMINI_API_KEY:
            raise RuntimeError("Chave do Gemini não configurada.")
        self.client = make_client()
        self.on_event = on_event or (lambda name, data: None)
        self.headphones = headphones
        self.idle_timeout = idle_timeout  # segundos de silêncio até "dormir"
        self.greet = greet                # dizer "Sim?" ao ser chamada
        self.stop_event = threading.Event()
        self.speaking_until = 0.0         # até quando a Magnólia está falando
        self.last_activity = time.monotonic()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session = None
        self._last_level = 0.0

    # ── Controle de fora (a interface roda em outra thread) ─────────────────
    def stop(self):
        self.stop_event.set()

    def send_text(self, text: str):
        """Manda uma mensagem digitada para a conversa de voz em andamento."""
        if self._loop and self._session:
            asyncio.run_coroutine_threadsafe(self._session.send_realtime_input(text=text), self._loop)

    def _emit(self, name: str, **data):
        try:
            self.on_event(name, data)
        except Exception:  # noqa: BLE001 - um erro na tela não pode parar a voz
            pass

    def _emit_level(self, data: bytes):
        # Manda o volume no máximo ~15 vezes por segundo, para não sobrecarregar a tela
        now = time.monotonic()
        if now - self._last_level > 0.066:
            self._last_level = now
            self._emit("nivel", valor=round(audio_level(data), 3))

    # ── Configuração da sessão ──────────────────────────────────────────────
    def _build_config(self) -> types.LiveConnectConfig:
        # Transforma cada função Python numa "declaração" que o Gemini entende
        declarations = [
            types.FunctionDeclaration.from_callable(
                client=self.client._api_client, callable=f, use_json_schema=True
            )
            for f in load_tools()
        ]
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=build_system_prompt(),
            tools=[types.Tool(function_declarations=declarations)],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=config.VOICE_NAME)
                )
            ),
            # Conversas longas não "estouram": o contexto antigo vai sendo resumido
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()
            ),
        )

    # ── 1. Microfone ────────────────────────────────────────────────────────
    async def listen_mic(self, queue: asyncio.Queue):
        import sounddevice as sd

        loop = asyncio.get_running_loop()

        def callback(indata, frames, time_info, status):
            # Sem fone: ignora o microfone enquanto a Magnólia fala (evita eco)
            if not self.headphones and time.monotonic() < self.speaking_until:
                return
            data = bytes(indata)
            loop.call_soon_threadsafe(lambda: queue.full() or queue.put_nowait(data))
            if time.monotonic() >= self.speaking_until:
                self._emit_level(data)

        with sd.RawInputStream(samplerate=MIC_RATE, channels=1, dtype="int16",
                               blocksize=CHUNK, callback=callback):
            await asyncio.Event().wait()  # fica aberto até a sessão terminar

    # ── 2. Envio ────────────────────────────────────────────────────────────
    async def send_audio(self, session, queue: asyncio.Queue):
        while True:
            data = await queue.get()
            await session.send_realtime_input(
                audio=types.Blob(data=data, mime_type=f"audio/pcm;rate={MIC_RATE}")
            )

    # ── 3. Recebimento ──────────────────────────────────────────────────────
    async def receive(self, session, speaker: asyncio.Queue):
        heard, said = [], []
        while True:
            async for msg in session.receive():
                content = msg.server_content
                if content:
                    if content.model_turn:
                        for part in content.model_turn.parts or []:
                            if part.inline_data and part.inline_data.data:
                                speaker.put_nowait(part.inline_data.data)
                    if content.input_transcription and content.input_transcription.text:
                        if not heard:
                            self._emit("estado", estado="pensando")
                        heard.append(content.input_transcription.text)
                        self.last_activity = time.monotonic()
                    if content.output_transcription and content.output_transcription.text:
                        said.append(content.output_transcription.text)
                        self.last_activity = time.monotonic()
                    if content.interrupted:
                        # Você falou por cima: para de tocar o que sobrou
                        while not speaker.empty():
                            speaker.get_nowait()
                    if content.turn_complete:
                        if heard:
                            self._emit("texto", quem="Você", texto="".join(heard).strip())
                        if said:
                            self._emit("texto", quem=config.ASSISTANT_NAME, texto="".join(said).strip())
                        heard, said = [], []
                        self.last_activity = time.monotonic()

                if msg.tool_call:
                    self._emit("estado", estado="pensando")
                    responses = []
                    for call in msg.tool_call.function_calls:
                        self._emit("ferramenta", nome=call.name, args=call.args or {})
                        # Roda a ferramenta numa thread para não travar o áudio
                        result = await asyncio.to_thread(run_tool, call.name, call.args or {})
                        responses.append(types.FunctionResponse(
                            id=call.id, name=call.name, response={"result": result}
                        ))
                    await session.send_tool_response(function_responses=responses)
                    self.last_activity = time.monotonic()

    # ── 4. Caixa de som ─────────────────────────────────────────────────────
    async def play_audio(self, speaker: asyncio.Queue):
        import sounddevice as sd

        stream = sd.RawOutputStream(samplerate=SPEAKER_RATE, channels=1, dtype="int16")
        stream.start()
        speaking = False
        try:
            while True:
                try:
                    data = await asyncio.wait_for(speaker.get(), timeout=0.3)
                except asyncio.TimeoutError:
                    if speaking:  # acabou de falar
                        speaking = False
                        self._emit("estado", estado="ouvindo")
                    continue
                if not speaking:
                    speaking = True
                    self._emit("estado", estado="falando")
                seconds = len(data) / 2 / SPEAKER_RATE  # 2 bytes por amostra
                self.speaking_until = time.monotonic() + seconds + 0.4
                self.last_activity = time.monotonic()
                self._emit_level(data)
                await asyncio.to_thread(stream.write, data)
        finally:
            stream.close()

    # ── 5. Vigia ────────────────────────────────────────────────────────────
    async def watchdog(self):
        while True:
            await asyncio.sleep(0.3)
            if self.stop_event.is_set():
                raise _StopSession
            busy = time.monotonic() < self.speaking_until
            if self.idle_timeout and not busy and time.monotonic() - self.last_activity > self.idle_timeout:
                raise _StopSession

    # ── Tudo junto ──────────────────────────────────────────────────────────
    async def run(self):
        self._loop = asyncio.get_running_loop()
        mic: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
        speaker: asyncio.Queue[bytes] = asyncio.Queue()
        model = await asyncio.to_thread(pick_live_model, self.client)
        print(f"[Magnólia] voz: conectando ao modelo {model}...", flush=True)
        async with self.client.aio.live.connect(model=model, config=self._build_config()) as session:
            self._session = session
            print("[Magnólia] voz: conectada, pode falar.", flush=True)
            self.last_activity = time.monotonic()
            self._emit("estado", estado="ouvindo")
            if self.greet:
                await session.send_realtime_input(
                    text="(O usuário acabou de dizer seu nome para te chamar. Responda só com algo "
                         "curtíssimo, como 'Sim?' ou 'Pois não?', e espere o pedido.)")
            try:
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self.listen_mic(mic))
                    tg.create_task(self.send_audio(session, mic))
                    tg.create_task(self.receive(session, speaker))
                    tg.create_task(self.play_audio(speaker))
                    tg.create_task(self.watchdog())
            except* _StopSession:
                pass  # encerramento normal (silêncio ou botão de parar)
            finally:
                self._session = None
