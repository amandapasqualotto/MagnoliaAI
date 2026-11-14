"""Escolhe os modelos do Gemini que a SUA chave pode usar.

Os nomes dos modelos mudam com frequência (saem versões novas, as antigas são
aposentadas) e nem toda chave tem acesso a todos. Em vez de confiar num nome
fixo, perguntamos ao Google a lista de modelos disponíveis e escolhemos:
  - texto: o "flash" estável mais novo (rápido e barato), depois os outros;
  - voz:   um modelo que aceite conversa em tempo real (bidiGenerateContent).
"""

import re

from magnolia import config

# A versão "v1beta" da API tem tudo o que a Magnólia usa, incluindo a conversa por voz
# em tempo real (Live API). A biblioteca do Google usa "v1" por padrão, que não tem.
API_VERSION = "v1beta"


def make_client(timeout_seconds: float | None = None):
    """Cria o cliente do Gemini já com a versão certa da API (e um tempo limite, se pedido)."""
    from google import genai
    from google.genai import types

    options = {"api_version": API_VERSION}
    if timeout_seconds:
        options["timeout"] = int(timeout_seconds * 1000)  # em milissegundos
    return genai.Client(api_key=config.GEMINI_API_KEY, http_options=types.HttpOptions(**options))

# Modelos que não servem para conversar por texto
SKIP_FOR_TEXT = ("live", "tts", "image", "audio", "embedding", "aqa", "veo", "imagen", "robotics", "computer-use")


def _version(name: str) -> tuple:
    """'gemini-3.5-flash' -> (3, 5). Usado para preferir os mais novos."""
    match = re.search(r"gemini-(\d+)(?:\.(\d+))?", name)
    return (int(match.group(1)), int(match.group(2) or 0)) if match else (0, 0)


_cache: dict[str, list] = {}


def _available(client) -> list[tuple[str, list[str]]]:
    """Lista (nome, ações suportadas) de todos os modelos que a chave enxerga.

    A lista fica guardada enquanto o programa está aberto (uma consulta por chave).
    """
    key = config.GEMINI_API_KEY
    if key not in _cache:
        found = []
        for model in client.models.list():
            name = (model.name or "").removeprefix("models/")
            found.append((name, list(model.supported_actions or [])))
        _cache[key] = found
    return _cache[key]


def text_rank(name: str) -> tuple:
    """Quanto menor, melhor: estável antes de preview; flash antes de flash-lite; mais novo primeiro."""
    unstable = any(word in name for word in ("preview", "exp", "experimental"))
    lite = "lite" in name
    major, minor = _version(name)
    return (unstable, lite, -major, -minor, name)


def pick_text_models(client) -> list[str]:
    """Lista de modelos de texto para tentar, do melhor para o pior."""
    try:
        models = _available(client)
    except Exception:  # noqa: BLE001 - sem lista (ex.: sem internet): usa os nomes da configuração
        return list(config.TEXT_MODELS)
    usable = [
        name for name, actions in models
        if "generateContent" in actions and name.startswith("gemini")
        and "flash" in name and not any(word in name for word in SKIP_FOR_TEXT)
    ]
    preferred = [m for m in config.TEXT_MODELS if m in usable]
    others = sorted((m for m in usable if m not in preferred), key=text_rank)
    return preferred + others or list(config.TEXT_MODELS)


def pick_live_model(client) -> str:
    """Modelo para a conversa por voz em tempo real."""
    try:
        models = _available(client)
    except Exception:  # noqa: BLE001
        return config.LIVE_MODEL
    live = [name for name, actions in models if "bidiGenerateContent" in actions]
    if not live or config.LIVE_MODEL in live:
        return config.LIVE_MODEL
    # Prefere "flash-live" estável e mais novo
    return sorted(live, key=lambda n: ("flash" not in n, *text_rank(n)))[0]
