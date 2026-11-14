"""Configurações da Magnólia.

Duas partes:
  1. Configurações fixas do programa (modelos, pastas).
  2. Configurações da pessoa logada (chave da API, nome, cidade, voz...).
     Elas são preenchidas por use_user() depois do login. No modo
     desenvolvedor (terminal), vêm do arquivo .env.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ── Pastas ──────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

load_dotenv(ROOT_DIR / ".env")

# ── Programa ────────────────────────────────────────────────────────────────
ASSISTANT_NAME = "Magnólia"

# Modelos de texto, em ordem de preferência. Se um falhar (cota, fora do ar,
# modelo aposentado), a Magnólia tenta o próximo da lista.
TEXT_MODELS = [
    m.strip()
    for m in os.getenv("TEXT_MODELS", "gemini-flash-latest,gemini-flash-lite-latest").split(",")
    if m.strip()
]

# Modelo de voz em tempo real (Gemini Live API)
LIVE_MODEL = os.getenv("LIVE_MODEL", "gemini-3.1-flash-live-preview")

# Vozes femininas do Gemini (a primeira é a padrão)
FEMALE_VOICES = {
    "Kore": "firme e confiante",
    "Aoede": "leve e tranquila",
    "Leda": "jovem",
    "Zephyr": "animada",
    "Sulafat": "acolhedora",
    "Despina": "suave",
}

# ── Pessoa logada (preenchido no login ou pelo .env) ────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
USER_NAME = os.getenv("USER_NAME", "")
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Campo Grande")
VOICE_NAME = os.getenv("VOICE_NAME", "Kore")
USER_DIR = DATA_DIR / "dev"          # pasta com os dados da pessoa
MEMORY_FILE = USER_DIR / "memory.json"
CIPHER = None                        # criptografia da conta (None = modo dev)
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")  # app do Spotify da pessoa (opcional)


def use_user(user_dir: Path, api_key: str, name: str, city: str, voice: str, cipher=None,
             spotify_client_id: str = "") -> None:
    """Passa a usar os dados de uma pessoa (chamado depois do login)."""
    global GEMINI_API_KEY, USER_NAME, DEFAULT_CITY, VOICE_NAME, USER_DIR, MEMORY_FILE, CIPHER, SPOTIFY_CLIENT_ID
    GEMINI_API_KEY = api_key
    USER_NAME = name
    DEFAULT_CITY = city or "Campo Grande"
    VOICE_NAME = voice if voice in FEMALE_VOICES else "Kore"
    USER_DIR = Path(user_dir)
    USER_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE = USER_DIR / "memory.json"
    CIPHER = cipher
    SPOTIFY_CLIENT_ID = spotify_client_id.strip()
