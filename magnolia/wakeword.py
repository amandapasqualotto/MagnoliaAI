"""Palavra de ativação: "Ei, Magnólia".

Enquanto espera ser chamada, a Magnólia escuta o microfone com o Vosk, um
reconhecedor de voz que roda 100% no seu computador. Nada é enviado para a
internet (e nada gasta cota do Gemini) até você dizer o nome dela.

O modelo de português do Vosk (~31 MB) é baixado sozinho na primeira vez.
"""

import json
import unicodedata
import urllib.request
import zipfile
from difflib import SequenceMatcher

from magnolia import config

MODEL_NAME = "vosk-model-small-pt-0.3"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
MODEL_DIR = config.DATA_DIR / MODEL_NAME
WAKE_WORD = "magnolia"
SAMPLE_RATE = 16_000


def _normalize(text: str) -> str:
    """'Ei, Magnólia!' -> 'ei magnolia' (sem acentos e pontuação)."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return "".join(c if c.isalnum() or c == " " else " " for c in text)


def heard_wake_word(text: str) -> bool:
    """Confere se o texto reconhecido contém algo parecido com "Magnólia".

    O reconhecedor nem sempre escreve o nome certinho ("magnolha",
    "mangólia"...), então comparamos por semelhança em vez de igualdade.
    """
    for word in _normalize(text).split():
        if SequenceMatcher(None, word, WAKE_WORD).ratio() >= 0.75:
            return True
    return False


def ensure_model(on_status=print) -> None:
    if MODEL_DIR.exists():
        return
    on_status("Baixando o reconhecedor de voz offline (uma vez só, ~31 MB)...")
    zip_path = config.DATA_DIR / f"{MODEL_NAME}.zip"
    urllib.request.urlretrieve(MODEL_URL, zip_path)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(config.DATA_DIR)
    zip_path.unlink()


def wait_for_wake_word(stop_event, on_status=print) -> bool:
    """Fica escutando até ouvir "Magnólia". Devolve False se mandaram parar."""
    import queue

    import sounddevice as sd
    from vosk import KaldiRecognizer, Model, SetLogLevel

    SetLogLevel(-1)  # silencia as mensagens internas do Vosk
    ensure_model(on_status)
    recognizer = KaldiRecognizer(Model(str(MODEL_DIR)), SAMPLE_RATE)
    audio: queue.Queue[bytes] = queue.Queue()

    print('[Magnólia] esperando "Ei, Magnólia"...', flush=True)
    with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=4000,
                           callback=lambda data, *_: audio.put(bytes(data))):
        while not stop_event.is_set():
            try:
                chunk = audio.get(timeout=0.5)
            except queue.Empty:
                continue
            if recognizer.AcceptWaveform(chunk):
                text = json.loads(recognizer.Result()).get("text", "")
            else:
                text = json.loads(recognizer.PartialResult()).get("partial", "")
            if text and heard_wake_word(text):
                print(f'[Magnólia] ouvi o nome ("{text}")', flush=True)
                return True
    return False
