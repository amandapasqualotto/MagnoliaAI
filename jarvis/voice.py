"""Modo voz: conversa falada em tempo real com a Gemini Live API.

Quatro tarefas rodam ao mesmo tempo (asyncio):
  1. listen_mic   -> captura o microfone em pedacinhos de áudio
  2. send_audio   -> envia esses pedaços para o Gemini
  3. receive      -> recebe a voz do Jarvis, as transcrições e os pedidos de ferramenta
  4. play_audio   -> toca a voz do Jarvis nas caixas de som

Dica: use fone de ouvido. Sem fone, o microfone fica mudo enquanto o Jarvis
fala, para ele não ouvir a própria voz e responder a si mesmo.
"""

import asyncio
import time

import sounddevice as sd
from google import genai
from google.genai import types

from jarvis import config
from jarvis.prompt import build_system_prompt
from jarvis.tools import load_tools, run_tool

MIC_RATE = 16_000      # o Gemini espera áudio de entrada em 16 kHz
SPEAKER_RATE = 24_000  # e devolve áudio em 24 kHz
CHUNK = 1024           # amostras por pedaço (~64 ms de áudio)


class VoiceSession:
    def __init__(self, headphones: bool = False, on_text=print):
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY não configurada. Copie .env.example para .env e preencha.")
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.headphones = headphones
        self.on_text = on_text            # função chamada para mostrar o que foi dito
        self.mic_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
        self.speaker_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.speaking_until = 0.0         # até quando o Jarvis está falando

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
    async def listen_mic(self):
        loop = asyncio.get_running_loop()

        def callback(indata, frames, time_info, status):
            # Sem fone: ignora o microfone enquanto o Jarvis fala (evita eco)
            if not self.headphones and time.monotonic() < self.speaking_until:
                return
            data = bytes(indata)
            loop.call_soon_threadsafe(self._put_mic, data)

        with sd.RawInputStream(samplerate=MIC_RATE, channels=1, dtype="int16",
                               blocksize=CHUNK, callback=callback):
            await asyncio.Event().wait()  # fica aberto até o programa fechar

    def _put_mic(self, data: bytes):
        if not self.mic_queue.full():
            self.mic_queue.put_nowait(data)

    # ── 2. Envio ────────────────────────────────────────────────────────────
    async def send_audio(self, session):
        while True:
            data = await self.mic_queue.get()
            await session.send_realtime_input(
                audio=types.Blob(data=data, mime_type=f"audio/pcm;rate={MIC_RATE}")
            )

    # ── 3. Recebimento ──────────────────────────────────────────────────────
    async def receive(self, session):
        heard, said = [], []
        while True:
            async for msg in session.receive():
                content = msg.server_content
                if content:
                    if content.model_turn:
                        for part in content.model_turn.parts or []:
                            if part.inline_data and part.inline_data.data:
                                self.speaker_queue.put_nowait(part.inline_data.data)
                    if content.input_transcription and content.input_transcription.text:
                        heard.append(content.input_transcription.text)
                    if content.output_transcription and content.output_transcription.text:
                        said.append(content.output_transcription.text)
                    if content.interrupted:
                        # Você falou por cima: para de tocar o que sobrou
                        self._clear_speaker()
                    if content.turn_complete:
                        if heard:
                            self.on_text("Você", "".join(heard).strip())
                        if said:
                            self.on_text(config.ASSISTANT_NAME, "".join(said).strip())
                        heard, said = [], []

                if msg.tool_call:
                    responses = []
                    for call in msg.tool_call.function_calls:
                        self.on_text("⚙", f"{call.name}({call.args or {}})")
                        # Roda a ferramenta numa thread para não travar o áudio
                        result = await asyncio.to_thread(run_tool, call.name, call.args or {})
                        responses.append(types.FunctionResponse(
                            id=call.id, name=call.name, response={"result": result}
                        ))
                    await session.send_tool_response(function_responses=responses)

    def _clear_speaker(self):
        while not self.speaker_queue.empty():
            self.speaker_queue.get_nowait()

    # ── 4. Caixa de som ─────────────────────────────────────────────────────
    async def play_audio(self):
        stream = sd.RawOutputStream(samplerate=SPEAKER_RATE, channels=1, dtype="int16")
        stream.start()
        try:
            while True:
                data = await self.speaker_queue.get()
                seconds = len(data) / 2 / SPEAKER_RATE  # 2 bytes por amostra
                self.speaking_until = time.monotonic() + seconds + 0.4
                await asyncio.to_thread(stream.write, data)
        finally:
            stream.close()

    # ── Tudo junto ──────────────────────────────────────────────────────────
    async def run(self):
        async with self.client.aio.live.connect(model=config.LIVE_MODEL,
                                                config=self._build_config()) as session:
            self.on_text("⚡", f"{config.ASSISTANT_NAME} online. Pode falar. (Ctrl+C para sair)")
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.listen_mic())
                tg.create_task(self.send_audio(session))
                tg.create_task(self.receive(session))
                tg.create_task(self.play_audio())
