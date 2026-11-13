"""Configurações do Jarvis, lidas do arquivo .env.

Tudo que você pode querer mudar sem mexer no código fica aqui.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Pasta raiz do projeto (onde fica o main.py)
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

load_dotenv(ROOT_DIR / ".env")

# Chave da API do Google AI Studio: https://aistudio.google.com/apikey
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Nome do assistente e de quem ele atende
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "JARVIS")
USER_NAME = os.getenv("USER_NAME", "")

# Modelos de texto, em ordem de preferência. Se um falhar (cota, fora do ar,
# modelo aposentado), o Jarvis tenta o próximo da lista.
TEXT_MODELS = [
    m.strip()
    for m in os.getenv("TEXT_MODELS", "gemini-flash-latest,gemini-flash-lite-latest").split(",")
    if m.strip()
]

# Modelo de voz em tempo real (Gemini Live API)
LIVE_MODEL = os.getenv("LIVE_MODEL", "gemini-3.1-flash-live-preview")

# Voz do Jarvis no modo voz. Opções: Puck, Charon, Kore, Fenrir, Aoede...
VOICE_NAME = os.getenv("VOICE_NAME", "Charon")

# Cidade padrão para a previsão do tempo
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Campo Grande")

MEMORY_FILE = DATA_DIR / "memory.json"
