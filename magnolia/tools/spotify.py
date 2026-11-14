"""Spotify: controla o aplicativo do Spotify instalado no computador.

Não precisa de login nem de conta Premium:
  - Windows: usa as teclas de mídia (as mesmas do teclado) e lê a música atual
    no título da janela do Spotify, que mostra "Artista - Música" enquanto toca.
  - Mac: conversa com o app pelo AppleScript.
  - Linux: usa o "playerctl", se estiver instalado.

Dar play automático numa música específica exigiria a API do Spotify, que só
permite isso para contas Premium. Por isso, para pedidos como "coloca Taylor
Swift", a Magnólia abre o Spotify já na busca.
"""

import platform
import shutil
import subprocess
import webbrowser
from urllib.parse import quote

from magnolia.tools import tool

SYSTEM = platform.system()

# Códigos das teclas de mídia do Windows
MEDIA_KEYS = {"tocar_pausar": 0xB3, "proxima": 0xB0, "anterior": 0xB1,
              "volume_mais": 0xAF, "volume_menos": 0xAE, "mudo": 0xAD}
APPLESCRIPT = {"tocar_pausar": "playpause", "proxima": "next track", "anterior": "previous track"}
PLAYERCTL = {"tocar_pausar": "play-pause", "proxima": "next", "anterior": "previous"}


def _press_media_key(action: str, times: int = 1) -> None:
    import ctypes

    vk = MEDIA_KEYS[action]
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)  # aperta
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # solta


def _control(action: str, times: int = 1) -> bool:
    """Envia um comando ao player. Devolve False se este sistema não suporta."""
    if SYSTEM == "Windows":
        _press_media_key(action, times)
        return True
    if SYSTEM == "Darwin" and action in APPLESCRIPT:
        subprocess.run(["osascript", "-e", f'tell application "Spotify" to {APPLESCRIPT[action]}'], check=False)
        return True
    if shutil.which("playerctl") and action in PLAYERCTL:
        subprocess.run(["playerctl", "-p", "spotify", PLAYERCTL[action]], check=False)
        return True
    return False


def _windows_spotify_titles() -> list[str]:
    """Títulos das janelas do processo Spotify.exe (Windows)."""
    import ctypes
    from ctypes import wintypes

    import psutil

    pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "spotify.exe"}
    if not pids:
        return []
    user32 = ctypes.windll.user32
    titles: list[str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                titles.append(buffer.value)
        return True

    user32.EnumWindows(callback, 0)
    return titles


def describe_title(titles: list[str]) -> str:
    """Interpreta os títulos da janela do Spotify."""
    if not titles:
        return "O Spotify não está aberto."
    for title in titles:
        if " - " in title:  # "Artista - Música" (só aparece enquanto toca)
            artist, song = title.split(" - ", 1)
            return f"Tocando agora: {song} ({artist})."
    return "O Spotify está aberto, mas pausado."


def now_playing() -> str:
    if SYSTEM == "Windows":
        return describe_title(_windows_spotify_titles())
    if SYSTEM == "Darwin":
        script = ('tell application "Spotify" to if player state is playing then '
                  'return (name of current track) & " - " & (artist of current track)')
        out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout.strip()
        if not out:
            return "O Spotify está pausado ou fechado."
        song, artist = out.split(" - ", 1)
        return f"Tocando agora: {song} ({artist})."
    if shutil.which("playerctl"):
        out = subprocess.run(["playerctl", "-p", "spotify", "metadata", "--format", "{{artist}} - {{title}}"],
                             capture_output=True, text=True).stdout.strip()
        return describe_title([out] if out else [])
    return "Não consigo ver o que está tocando neste sistema."


def _open(uri: str, web_url: str) -> str:
    """Abre um endereço spotify: no aplicativo; se não der, abre o Spotify Web."""
    try:
        if SYSTEM == "Windows":
            import os

            os.startfile(uri)  # noqa: S606 - abre o app do Spotify
            return "app"
        if SYSTEM == "Darwin":
            subprocess.run(["open", uri], check=True)
            return "app"
        if shutil.which("xdg-open"):
            subprocess.run(["xdg-open", uri], check=True)
            return "app"
    except (OSError, subprocess.CalledProcessError):
        pass
    webbrowser.open(web_url)
    return "web"


# ── Ferramentas ─────────────────────────────────────────────────────────────
@tool
def spotify_tocar_ou_pausar() -> str:
    """Dá play ou pausa na música do Spotify (ou de outro player de música aberto)."""
    return "Feito." if _control("tocar_pausar") else "Não consigo controlar o Spotify neste sistema."


@tool
def spotify_proxima_musica() -> str:
    """Pula para a próxima música no Spotify."""
    return "Próxima música." if _control("proxima") else "Não consigo controlar o Spotify neste sistema."


@tool
def spotify_musica_anterior() -> str:
    """Volta para a música anterior no Spotify."""
    # No Spotify, "anterior" uma vez volta ao início da música; duas vezes vai para a anterior
    return "Voltei." if _control("anterior", times=2) else "Não consigo controlar o Spotify neste sistema."


@tool
def volume_do_computador(acao: str, passos: int = 5) -> str:
    """Muda o volume do computador.

    Args:
        acao: "aumentar", "diminuir" ou "mudo" (liga/desliga o som).
        passos: quanto mudar (cada passo é cerca de 2%; padrão 5).
    """
    if SYSTEM != "Windows":
        return "Por enquanto só consigo mudar o volume no Windows."
    actions = {"aumentar": "volume_mais", "diminuir": "volume_menos", "mudo": "mudo"}
    if acao not in actions:
        return 'Use "aumentar", "diminuir" ou "mudo".'
    _press_media_key(actions[acao], 1 if acao == "mudo" else max(1, min(passos, 25)))
    return "Volume ajustado."


@tool
def spotify_o_que_esta_tocando() -> str:
    """Diz qual música está tocando agora no Spotify."""
    return now_playing()


@tool
def spotify_buscar(busca: str) -> str:
    """Abre o Spotify já na busca de uma música, artista, álbum ou playlist.

    Use quando o usuário pedir para tocar ou colocar algo específico no Spotify.
    Depois de abrir, avise que é só escolher o resultado para tocar.

    Args:
        busca: o que procurar, por exemplo "Taylor Swift" ou "lofi para estudar".
    """
    where = _open(f"spotify:search:{quote(busca)}", f"https://open.spotify.com/search/{quote(busca)}")
    place = "no aplicativo do Spotify" if where == "app" else "no Spotify Web"
    return f"Abri a busca por '{busca}' {place}. É só escolher o resultado para tocar."
