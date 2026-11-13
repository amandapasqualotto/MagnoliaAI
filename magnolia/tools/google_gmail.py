"""Gmail: ler e-mails e criar rascunhos.

A Magnólia NÃO envia e-mails sozinha: ela cria o rascunho e você revisa e
envia pelo Gmail. Uma assistente de voz pode entender errado um nome ou um
endereço, e e-mail enviado não volta.
"""

import base64
from email.message import EmailMessage

from magnolia.google_auth import service
from magnolia.tools import tool


def _summaries(query: str, limit: int) -> str:
    gmail = service("gmail", "v1").users()
    messages = gmail.messages().list(userId="me", q=query, maxResults=limit).execute().get("messages", [])
    if not messages:
        return "Nenhum e-mail encontrado."
    lines = []
    for m in messages:
        msg = gmail.messages().get(userId="me", id=m["id"], format="metadata",
                                   metadataHeaders=["From", "Subject"]).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        lines.append(f"De {headers.get('From', '?')}: {headers.get('Subject', '(sem assunto)')}\n"
                     f"   {msg.get('snippet', '')[:150]}")
    return "\n".join(lines)


@tool
def gmail_nao_lidos(quantidade: int = 5) -> str:
    """Mostra os e-mails não lidos mais recentes da caixa de entrada.

    Args:
        quantidade: quantos e-mails mostrar (padrão 5).
    """
    return _summaries("is:unread in:inbox", quantidade)


@tool
def gmail_buscar(busca: str, quantidade: int = 5) -> str:
    """Procura e-mails no Gmail (aceita a busca do Gmail, como "from:banco" ou "fatura").

    Args:
        busca: o que procurar.
        quantidade: quantos e-mails mostrar (padrão 5).
    """
    return _summaries(busca, quantidade)


@tool
def gmail_criar_rascunho(para: str, assunto: str, texto: str) -> str:
    """Cria um RASCUNHO de e-mail no Gmail para o usuário revisar e enviar.

    Args:
        para: endereço de e-mail do destinatário.
        assunto: assunto do e-mail.
        texto: corpo do e-mail.
    """
    msg = EmailMessage()
    msg["To"], msg["Subject"] = para, assunto
    msg.set_content(texto)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service("gmail", "v1").users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return f"Rascunho para {para} criado no Gmail. É só revisar e enviar."
