"""Conexão com a API oficial do Spotify (para contas Premium).

Com a conta conectada, a Magnólia toca músicas, álbuns e playlists de verdade,
pausa, pula, muda o volume e põe músicas na fila.

Como funciona o login (OAuth com PKCE, sem senha nem "segredo" guardado):
  1. Você cria um app em developer.spotify.com e cola o "Client ID" nas configurações.
  2. A Magnólia abre o navegador; você autoriza na sua conta Spotify.
  3. O Spotify devolve um "token" (crachá de acesso), guardado CRIPTOGRAFADO
     na sua pasta de usuário. Ele se renova sozinho.
"""

import base64
import hashlib
import json
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from magnolia import config

REDIRECT_PORT = 8888
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"  # o mesmo cadastrado no app do Spotify
API = "https://api.spotify.com/v1"
SCOPES = " ".join([
    "user-read-playback-state", "user-modify-playback-state", "user-read-currently-playing",
    "playlist-read-private", "playlist-read-collaborative", "user-library-read",
])
KINDS = {"musica": "track", "album": "album", "artista": "artist", "playlist": "playlist"}


class SpotifyError(Exception):
    """Erro com mensagem amigável."""


# ── Token (guardado criptografado) ──────────────────────────────────────────
def _token_file():
    return config.USER_DIR / "spotify_token.bin"


def _save_token(token: dict) -> None:
    raw = json.dumps(token).encode()
    if config.CIPHER:
        raw = config.CIPHER.encrypt(raw)
    _token_file().parent.mkdir(parents=True, exist_ok=True)
    _token_file().write_bytes(raw)


def _load_token() -> dict | None:
    if not _token_file().exists():
        return None
    raw = _token_file().read_bytes()
    try:
        return json.loads(config.CIPHER.decrypt(raw) if config.CIPHER else raw)
    except Exception:  # noqa: BLE001
        return None


def is_connected() -> bool:
    return bool(config.SPOTIFY_CLIENT_ID) and _load_token() is not None


def disconnect() -> None:
    _token_file().unlink(missing_ok=True)


def _store_token_response(data: dict, old_refresh: str | None = None) -> dict:
    token = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token") or old_refresh,
        "expires_at": time.time() + int(data.get("expires_in", 3600)) - 60,
    }
    _save_token(token)
    return token


def _access_token() -> str:
    token = _load_token()
    if not token or not config.SPOTIFY_CLIENT_ID:
        raise SpotifyError("O Spotify não está conectado. Conecte nas configurações da Magnólia.")
    if time.time() >= token["expires_at"]:  # venceu: renova sem pedir login de novo
        r = requests.post("https://accounts.spotify.com/api/token", timeout=15, data={
            "grant_type": "refresh_token", "refresh_token": token["refresh_token"],
            "client_id": config.SPOTIFY_CLIENT_ID,
        })
        if not r.ok:
            raise SpotifyError("A conexão com o Spotify venceu. Conecte de novo nas configurações.")
        token = _store_token_response(r.json(), token["refresh_token"])
    return token["access_token"]


# ── Login ───────────────────────────────────────────────────────────────────
def connect(timeout: int = 180) -> str:
    """Abre o navegador para a pessoa autorizar e espera a resposta do Spotify."""
    if not config.SPOTIFY_CLIENT_ID:
        return "Cole o Client ID do seu app do Spotify nas configurações antes de conectar."
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    result: dict = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            if urlparse(self.path).path == "/callback" and query.get("state", [""])[0] == state:
                result.update({k: v[0] for k, v in query.items()})
            ok = "code" in result
            body = ("Pronto! Pode fechar esta aba e voltar para a Magnólia." if ok
                    else "Não deu certo. Volte para a Magnólia e tente de novo.").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    try:
        server = HTTPServer(("127.0.0.1", REDIRECT_PORT), Callback)
    except OSError:
        return f"A porta {REDIRECT_PORT} está ocupada. Feche outros programas e tente de novo."
    server.timeout = 1
    webbrowser.open("https://accounts.spotify.com/authorize?" + urlencode({
        "client_id": config.SPOTIFY_CLIENT_ID, "response_type": "code", "redirect_uri": REDIRECT_URI,
        "code_challenge_method": "S256", "code_challenge": challenge, "scope": SCOPES, "state": state,
    }))
    deadline = time.time() + timeout
    while not result and time.time() < deadline:
        server.handle_request()
    server.server_close()

    if "code" not in result:
        return "Não recebi a autorização do Spotify." + (f" ({result['error']})" if "error" in result else "")
    r = requests.post("https://accounts.spotify.com/api/token", timeout=15, data={
        "grant_type": "authorization_code", "code": result["code"], "redirect_uri": REDIRECT_URI,
        "client_id": config.SPOTIFY_CLIENT_ID, "code_verifier": verifier,
    })
    if not r.ok:
        return f"O Spotify recusou a conexão: {r.text[:200]}"
    _store_token_response(r.json())
    return "Spotify conectado."


# ── Chamadas à API ──────────────────────────────────────────────────────────
def call(method: str, path: str, **kwargs) -> dict | None:
    r = requests.request(method, API + path, timeout=15,
                         headers={"Authorization": f"Bearer {_access_token()}"}, **kwargs)
    if r.status_code == 204:  # deu certo, sem conteúdo
        return None
    if r.status_code == 404 and "/me/player" in path:
        raise SpotifyError("NO_DEVICE")
    if r.status_code == 403:
        reason = r.json().get("error", {}).get("reason", "") if r.content else ""
        if reason == "PREMIUM_REQUIRED":
            raise SpotifyError("Essa função do Spotify exige uma conta Premium.")
        raise SpotifyError("O Spotify não permitiu essa ação.")
    if not r.ok:
        raise SpotifyError(f"O Spotify respondeu com erro {r.status_code}.")
    return r.json() if r.content else None


def devices() -> list[dict]:
    return (call("GET", "/me/player/devices") or {}).get("devices", [])


def ensure_device(open_spotify) -> str | None:
    """Garante um aparelho para tocar. Se nenhum estiver aberto, abre o Spotify e espera."""
    found = devices()
    if not found:
        open_spotify()
        for _ in range(15):  # espera até ~15 s o Spotify aparecer
            time.sleep(1)
            found = devices()
            if found:
                break
    if not found:
        return None
    active = next((d for d in found if d.get("is_active")), found[0])
    return active["id"]


def search(query: str, kind: str = "musica") -> dict | None:
    spotify_type = KINDS.get(kind, "track")
    data = call("GET", "/search", params={"q": query, "type": spotify_type, "limit": 5})
    items = [i for i in (data or {}).get(spotify_type + "s", {}).get("items", []) if i]
    return items[0] if items else None


def describe(item: dict) -> str:
    artists = ", ".join(a["name"] for a in item.get("artists", []))
    if item.get("type") == "playlist":
        return f"a playlist {item['name']}"
    if item.get("type") == "artist":
        return item["name"]
    return f"{item['name']}" + (f" ({artists})" if artists else "")


def play(item: dict, device_id: str) -> None:
    body = {"uris": [item["uri"]]} if item["type"] == "track" else {"context_uri": item["uri"]}
    call("PUT", "/me/player/play", params={"device_id": device_id}, json=body)


def my_playlists() -> list[dict]:
    return [p for p in (call("GET", "/me/playlists", params={"limit": 50}) or {}).get("items", []) if p]
