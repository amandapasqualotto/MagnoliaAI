"""Spotify: tocar músicas e controlar o player.

Dois modos, escolhidos sozinhos:
  1. Spotify conectado (conta Premium, ver spotify_api.py): usa a API oficial e
     toca de verdade qualquer música, álbum, artista ou playlist.
  2. Sem conexão (qualquer conta): controla o player pelas teclas de mídia do
     Windows (AppleScript no Mac, playerctl no Linux), lê a música atual no título
     da janela e abre a música certa no Spotify para você apertar o play.
"""

import platform
import re
import shutil
import subprocess
import webbrowser
from urllib.parse import quote

from magnolia import spotify_api
from magnolia.spotify_api import SpotifyError
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
        return ("Não encontrei o aplicativo do Spotify aberto. Se você estiver ouvindo pelo navegador, "
                "consigo pausar e pular músicas, mas não ver qual está tocando.")
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


def spotify_app_installed() -> bool:
    """No Windows, confere se o aplicativo do Spotify está instalado.

    O app registra o protocolo "spotify:" no Windows. Sem ele, abrir um endereço
    spotify: mostra o aviso "Você precisa de um novo aplicativo".
    """
    if SYSTEM != "Windows":
        return True
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"spotify\shell\open\command"):
            return True
    except OSError:
        return False


def _open(uri: str, web_url: str) -> str:
    """Abre um endereço spotify: no aplicativo; se não der, abre o Spotify Web."""
    try:
        if SYSTEM == "Windows":
            if not spotify_app_installed():
                raise OSError("aplicativo do Spotify não instalado")
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


TRACK_LINK = re.compile(r"open\.spotify\.com/(?:intl-[\w-]+/)?(track|album|playlist|artist)/([A-Za-z0-9]{22})")


def find_on_spotify(query: str) -> tuple[str, str, str] | None:
    """Procura a música (ou álbum/playlist) na web e devolve (tipo, id, título) do Spotify.

    A busca do Spotify pela API exige uma conta de desenvolvedor Premium; então
    procuramos o link público da música no buscador, que funciona para qualquer pessoa.
    """
    from ddgs import DDGS

    for result in DDGS().text(f"{query} site:open.spotify.com", max_results=8) or []:
        match = TRACK_LINK.search(result.get("href", ""))
        if match:
            title = re.sub(r"\s*[|-]\s*Spotify.*$", "", result.get("title", "")).strip()
            return match.group(1), match.group(2), title or query
    return None


# ── Ferramentas ─────────────────────────────────────────────────────────────
NO_DEVICE = ("Não achei nenhum Spotify aberto para tocar. Abra o aplicativo ou o Spotify Web "
             "(open.spotify.com) e peça de novo.")


def _open_spotify_player() -> None:
    _open("spotify:", "https://open.spotify.com")


def _api_player(action: str, method: str, path: str, **kwargs) -> str | None:
    """Tenta uma ação pela API. Devolve a resposta, ou None para usar o modo sem conexão."""
    if not spotify_api.is_connected():
        return None
    try:
        spotify_api.call(method, path, **kwargs)
        return action
    except SpotifyError as e:
        if str(e) == "NO_DEVICE":
            return NO_DEVICE
        return None  # outro problema: tenta pelas teclas de mídia


@tool
def spotify_tocar(musica: str, tipo: str = "musica") -> str:
    """Toca no Spotify uma música, álbum, artista ou playlist.

    Use sempre que o usuário pedir para tocar, colocar ou ouvir algo.

    Args:
        musica: o que tocar, de preferência com o artista, por exemplo "Choosing Texas Ella Langley".
        tipo: "musica" (padrão), "album", "artista" ou "playlist".
    """
    if spotify_api.is_connected():
        try:
            item = spotify_api.search(musica, tipo)
            if not item:
                return f"Não encontrei '{musica}' no Spotify."
            device = spotify_api.ensure_device(_open_spotify_player)
            if not device:
                return NO_DEVICE
            spotify_api.play(item, device)
            return f"Tocando {spotify_api.describe(item)}."
        except SpotifyError as e:
            return NO_DEVICE if str(e) == "NO_DEVICE" else str(e)

    # Sem conexão: abre a música certa para a pessoa apertar o play
    try:
        found = find_on_spotify(musica)
    except Exception:  # noqa: BLE001 - sem internet ou buscador fora do ar
        found = None
    if not found:
        return spotify_buscar.__wrapped__(musica)
    kind, item_id, title = found
    where = _open(f"spotify:{kind}:{item_id}", f"https://open.spotify.com/{kind}/{item_id}")
    app = "no aplicativo do Spotify" if where == "app" else "no Spotify Web, no navegador"
    return (f"Abri '{title}' {app}. É só apertar o play. "
            "(Conectando o Spotify Premium nas configurações, eu consigo dar o play sozinha.)")


@tool
def spotify_tocar_minha_playlist(nome: str) -> str:
    """Toca uma das playlists do próprio usuário pelo nome (precisa do Spotify conectado).

    Args:
        nome: nome ou parte do nome da playlist, por exemplo "treino" ou "estudos".
    """
    if not spotify_api.is_connected():
        return "Para tocar suas playlists, conecte o Spotify Premium nas configurações da Magnólia."
    try:
        playlists = spotify_api.my_playlists()
        match = next((p for p in playlists if nome.lower() in p["name"].lower()), None)
        if not match:
            names = ", ".join(p["name"] for p in playlists[:10])
            return f"Não achei uma playlist sua com '{nome}'. Algumas das suas: {names}."
        device = spotify_api.ensure_device(_open_spotify_player)
        if not device:
            return NO_DEVICE
        spotify_api.play(match, device)
        return f"Tocando a sua playlist {match['name']}."
    except SpotifyError as e:
        return NO_DEVICE if str(e) == "NO_DEVICE" else str(e)


@tool
def spotify_listar_minhas_playlists() -> str:
    """Lista as playlists do usuário no Spotify (precisa do Spotify conectado)."""
    if not spotify_api.is_connected():
        return "Para ver suas playlists, conecte o Spotify Premium nas configurações da Magnólia."
    try:
        playlists = spotify_api.my_playlists()
    except SpotifyError as e:
        return str(e)
    return "\n".join(p["name"] for p in playlists) or "Você não tem playlists."


@tool
def spotify_adicionar_na_fila(musica: str) -> str:
    """Coloca uma música na fila do Spotify, para tocar depois da atual (precisa do Spotify conectado).

    Args:
        musica: música, de preferência com o artista.
    """
    if not spotify_api.is_connected():
        return "Para usar a fila, conecte o Spotify Premium nas configurações da Magnólia."
    try:
        item = spotify_api.search(musica, "musica")
        if not item:
            return f"Não encontrei '{musica}' no Spotify."
        spotify_api.call("POST", "/me/player/queue", params={"uri": item["uri"]})
        return f"{spotify_api.describe(item)} entrou na fila."
    except SpotifyError as e:
        return NO_DEVICE if str(e) == "NO_DEVICE" else str(e)


@tool
def spotify_pausar() -> str:
    """Pausa a música do Spotify."""
    via_api = _api_player("Pausei.", "PUT", "/me/player/pause")
    if via_api:
        return via_api
    return "Feito." if _control("tocar_pausar") else "Não consigo controlar o Spotify neste sistema."


@tool
def spotify_continuar() -> str:
    """Continua tocando a música do Spotify que estava pausada."""
    via_api = _api_player("Continuando.", "PUT", "/me/player/play")
    if via_api:
        return via_api
    return "Feito." if _control("tocar_pausar") else "Não consigo controlar o Spotify neste sistema."


@tool
def spotify_proxima_musica() -> str:
    """Pula para a próxima música no Spotify."""
    via_api = _api_player("Próxima música.", "POST", "/me/player/next")
    if via_api:
        return via_api
    return "Próxima música." if _control("proxima") else "Não consigo controlar o Spotify neste sistema."


@tool
def spotify_musica_anterior() -> str:
    """Volta para a música anterior no Spotify."""
    via_api = _api_player("Voltei.", "POST", "/me/player/previous")
    if via_api:
        return via_api
    # Pelas teclas: "anterior" uma vez volta ao início da música; duas vezes vai para a anterior
    return "Voltei." if _control("anterior", times=2) else "Não consigo controlar o Spotify neste sistema."


@tool
def spotify_volume(porcentagem: int) -> str:
    """Define o volume do Spotify de 0 a 100 (precisa do Spotify conectado).

    Args:
        porcentagem: volume desejado, de 0 a 100.
    """
    value = max(0, min(100, porcentagem))
    via_api = _api_player(f"Volume do Spotify em {value}%.", "PUT", "/me/player/volume",
                          params={"volume_percent": value})
    return via_api or ("Para ajustar o volume do Spotify, conecte o Spotify Premium. "
                       "Posso mudar o volume do computador.")


@tool
def volume_do_computador(acao: str, passos: int = 5) -> str:
    """Muda o volume geral do computador.

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
    if spotify_api.is_connected():
        try:
            data = spotify_api.call("GET", "/me/player/currently-playing")
            if not data or not data.get("item"):
                return "Nada tocando no Spotify agora."
            state = "Tocando agora" if data.get("is_playing") else "Pausado em"
            return f"{state}: {spotify_api.describe(data['item'])}."
        except SpotifyError:
            pass
    return now_playing()


@tool
def spotify_buscar(busca: str) -> str:
    """Abre o Spotify na tela de busca, para o usuário escolher entre vários resultados.

    Use só quando o usuário quiser ver opções (ex.: "me mostra músicas para estudar").
    Para tocar algo, use spotify_tocar.

    Args:
        busca: o que procurar.
    """
    where = _open(f"spotify:search:{quote(busca)}", f"https://open.spotify.com/search/{quote(busca)}")
    if where == "app":
        return f"Abri a busca por '{busca}' no aplicativo do Spotify. É só escolher o resultado para tocar."
    return f"Abri a busca por '{busca}' no Spotify Web, no navegador. É só escolher o resultado para tocar."
