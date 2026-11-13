"""Login com a conta Google (OAuth) para Agenda, Planilhas, Docs, Drive e Gmail.

Como funciona o OAuth, em uma frase: a Magnólia abre o navegador, você
entra na sua conta Google e autoriza; o Google devolve um "token" (um
crachá de acesso) que fica guardado CRIPTOGRAFADO na sua pasta de usuário.
Sua senha do Google nunca passa pela Magnólia.

Preparação (uma vez só): veja o passo a passo "Conectar o Google" no README
para baixar o arquivo data/google_credentials.json.
"""

import json

from magnolia import config

CREDENTIALS_FILE = config.DATA_DIR / "google_credentials.json"

# O que a Magnólia pode acessar. Gmail: só ler e criar rascunhos (nunca envia sozinha).
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


class NotConnected(Exception):
    pass


def _token_file():
    return config.USER_DIR / "google_token.bin"


def _save_token(creds) -> None:
    raw = creds.to_json().encode()
    if config.CIPHER:
        raw = config.CIPHER.encrypt(raw)
    _token_file().parent.mkdir(parents=True, exist_ok=True)
    _token_file().write_bytes(raw)


def _load_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    file = _token_file()
    if not file.exists():
        return None
    raw = file.read_bytes()
    if config.CIPHER:
        raw = config.CIPHER.decrypt(raw)
    creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())  # renova o crachá vencido sem pedir login de novo
        _save_token(creds)
    return creds if creds.valid else None


def is_connected() -> bool:
    try:
        return _load_credentials() is not None
    except Exception:  # noqa: BLE001
        return False


def connect() -> str:
    """Abre o navegador para a pessoa autorizar o acesso à conta Google."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CREDENTIALS_FILE.exists():
        return ("Falta o arquivo data/google_credentials.json. "
                "Siga o passo a passo 'Conectar o Google' no README.")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent",
                                  success_message="Pronto! Pode fechar esta aba e voltar para a Magnólia.")
    _save_token(creds)
    return "Conta Google conectada."


def disconnect() -> None:
    _token_file().unlink(missing_ok=True)


def service(name: str, version: str):
    """Devolve um cliente pronto de uma API do Google (calendar, sheets, docs...)."""
    from googleapiclient.discovery import build

    creds = _load_credentials()
    if creds is None:
        raise NotConnected("A conta Google não está conectada. Peça para conectar nas configurações.")
    return build(name, version, credentials=creds, cache_discovery=False)


def find_file_id(text: str, mime: str) -> str:
    """Aceita um link, um ID ou o NOME de um arquivo e devolve o ID dele.

    Assim dá para dizer "lê a planilha Gastos de novembro" sem saber o link.
    """
    text = text.strip()
    if "/d/" in text:  # é um link do Google
        return text.split("/d/")[1].split("/")[0]
    if len(text) > 30 and " " not in text:  # parece um ID
        return text
    safe = text.replace("'", "\\'")
    files = service("drive", "v3").files().list(
        q=f"name contains '{safe}' and mimeType='{mime}' and trashed=false",
        orderBy="modifiedTime desc", pageSize=1, fields="files(id,name)",
    ).execute().get("files", [])
    if not files:
        raise FileNotFoundError(f"Não encontrei nenhum arquivo chamado '{text}'.")
    return files[0]["id"]


SHEET_MIME = "application/vnd.google-apps.spreadsheet"
DOC_MIME = "application/vnd.google-apps.document"
