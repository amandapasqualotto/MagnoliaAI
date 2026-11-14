"""Contas locais: cada pessoa que usa a Magnólia no computador tem login e senha.

Cada conta tem uma pasta própria em data/usuarios/<usuario>/ com a memória,
o acesso ao Google e as configurações. Ninguém vê os dados de ninguém.

Segurança (explicada de forma simples):
  - A senha NUNCA é guardada. Guardamos só um "hash" (uma impressão digital
    da senha, feita com PBKDF2 e 600 mil repetições). Para conferir o login,
    calculamos o hash da senha digitada e comparamos.
  - A chave da API do Gemini e o acesso ao Google ficam CRIPTOGRAFADOS com
    uma chave que nasce da sua senha. Sem a senha, os arquivos são ilegíveis.
"""

import base64
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from magnolia import config

USERS_DIR = config.DATA_DIR / "usuarios"
ITERATIONS = 600_000


class AccountError(Exception):
    """Erro com mensagem amigável para mostrar na tela."""


@dataclass
class Account:
    username: str
    folder: Path
    data: dict          # conteúdo do account.json
    cipher: Fernet      # criptografia desta conta (existe só enquanto logada)

    @property
    def name(self) -> str:
        return self.data["nome"]

    @property
    def settings(self) -> dict:
        return self.data.setdefault("config", {})

    def api_key(self) -> str:
        return self.get_secret("chave_api")

    def set_api_key(self, key: str) -> None:
        self.set_secret("chave_api", key)

    def get_secret(self, field: str) -> str:
        """Lê um dado criptografado da conta (chaves de API)."""
        value = self.data.get(field)
        return self.cipher.decrypt(value.encode()).decode() if value else ""

    def set_secret(self, field: str, value: str) -> None:
        """Guarda um dado criptografado (vazio apaga)."""
        value = value.strip()
        self.data[field] = self.cipher.encrypt(value.encode()).decode() if value else ""
        self.save()

    def save(self) -> None:
        (self.folder / "account.json").write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")

    def activate(self) -> None:
        """Faz a Magnólia passar a usar os dados desta conta."""
        config.use_user(self.folder, self.api_key(), self.name, self.settings.get("cidade", ""),
                        self.settings.get("voz", "Kore"), self.cipher, self.settings.get("spotify_client_id", ""),
                        self.settings.get("estilo_voz", "natural"))


# ── Funções de apoio ────────────────────────────────────────────────────────
def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)


def _cipher(password: str, salt: bytes) -> Fernet:
    # Uma chave de criptografia diferente do hash, derivada da mesma senha
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt + b"cripto", ITERATIONS)
    return Fernet(base64.urlsafe_b64encode(key))


def _clean_username(username: str) -> str:
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,30}", username):
        raise AccountError("O usuário deve ter de 3 a 30 letras, números, ponto, hífen ou _ (sem espaços).")
    return username


# ── O que a interface usa ───────────────────────────────────────────────────
def list_accounts() -> list[str]:
    if not USERS_DIR.exists():
        return []
    return sorted(p.name for p in USERS_DIR.iterdir() if (p / "account.json").exists())


def create_account(username: str, password: str, name: str, api_key: str, city: str = "") -> Account:
    username = _clean_username(username)
    if len(password) < 6:
        raise AccountError("A senha precisa ter pelo menos 6 caracteres.")
    if not name.strip():
        raise AccountError("Diga como a Magnólia deve te chamar.")
    if not api_key.strip():
        raise AccountError("Cole sua chave da API do Gemini.")
    folder = USERS_DIR / username
    if (folder / "account.json").exists():
        raise AccountError("Esse usuário já existe.")
    folder.mkdir(parents=True, exist_ok=True)

    salt = os.urandom(16)
    account = Account(
        username=username,
        folder=folder,
        data={
            "usuario": username,
            "nome": name.strip(),
            "sal": salt.hex(),
            "senha_hash": _hash(password, salt).hex(),
            "chave_api": "",
            "config": {"cidade": city.strip() or "Campo Grande", "voz": "Kore", "ei_magnolia": True},
        },
        cipher=_cipher(password, salt),
    )
    account.set_api_key(api_key)  # criptografa e salva
    return account


def login(username: str, password: str) -> Account:
    username = username.strip().lower()
    file = USERS_DIR / username / "account.json"
    if not file.exists():
        raise AccountError("Usuário ou senha incorretos.")
    data = json.loads(file.read_text(encoding="utf-8"))
    salt = bytes.fromhex(data["sal"])
    # compare_digest evita que alguém descubra a senha medindo o tempo da comparação
    if not hmac.compare_digest(_hash(password, salt).hex(), data["senha_hash"]):
        raise AccountError("Usuário ou senha incorretos.")
    account = Account(username, file.parent, data, _cipher(password, salt))
    try:
        account.api_key()
    except InvalidToken as e:
        raise AccountError("Não consegui abrir os dados desta conta.") from e
    return account
