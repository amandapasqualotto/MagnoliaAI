"""Google Docs e Google Drive: criar e ler documentos, procurar arquivos."""

import webbrowser

from magnolia.google_auth import DOC_MIME, find_file_id, service
from magnolia.tools import tool


def _doc_text(doc: dict) -> str:
    """Junta todo o texto de um documento do Google Docs."""
    parts = []
    for block in doc.get("body", {}).get("content", []):
        for element in block.get("paragraph", {}).get("elements", []):
            parts.append(element.get("textRun", {}).get("content", ""))
    return "".join(parts)


@tool
def documento_criar(titulo: str, conteudo: str = "") -> str:
    """Cria um documento novo no Google Docs, opcionalmente já com texto.

    Args:
        titulo: nome do documento.
        conteudo: texto inicial do documento.
    """
    docs = service("docs", "v1").documents()
    doc = docs.create(body={"title": titulo}).execute()
    if conteudo:
        docs.batchUpdate(documentId=doc["documentId"], body={
            "requests": [{"insertText": {"location": {"index": 1}, "text": conteudo}}]
        }).execute()
    url = f"https://docs.google.com/document/d/{doc['documentId']}/edit"
    webbrowser.open(url)  # já abre para o usuário ver
    return f"Documento '{titulo}' criado e aberto no navegador: {url}"


@tool
def documento_ler(documento: str) -> str:
    """Lê o texto de um documento do Google Docs.

    Args:
        documento: nome, link ou ID do documento.
    """
    doc = service("docs", "v1").documents().get(documentId=find_file_id(documento, DOC_MIME)).execute()
    text = _doc_text(doc).strip()
    return text[:8000] if text else "O documento está vazio."


@tool
def documento_adicionar_texto(documento: str, texto: str) -> str:
    """Escreve um texto no final de um documento do Google Docs.

    Args:
        documento: nome, link ou ID do documento.
        texto: o que escrever.
    """
    docs = service("docs", "v1").documents()
    doc_id = find_file_id(documento, DOC_MIME)
    end = docs.get(documentId=doc_id).execute()["body"]["content"][-1]["endIndex"] - 1
    docs.batchUpdate(documentId=doc_id, body={
        "requests": [{"insertText": {"location": {"index": end}, "text": "\n" + texto}}]
    }).execute()
    return "Texto adicionado ao documento."


@tool
def drive_procurar_arquivos(termo: str) -> str:
    """Procura arquivos no Google Drive pelo nome.

    Args:
        termo: parte do nome do arquivo.
    """
    safe = termo.replace("'", "\\'")
    files = service("drive", "v3").files().list(
        q=f"name contains '{safe}' and trashed=false", orderBy="modifiedTime desc",
        pageSize=10, fields="files(name,webViewLink,modifiedTime)",
    ).execute().get("files", [])
    if not files:
        return f"Nenhum arquivo com '{termo}' no Drive."
    return "\n".join(f"{f['name']} (alterado em {f['modifiedTime'][:10]}): {f['webViewLink']}" for f in files)


@tool
def abrir_arquivo_do_google(nome: str) -> str:
    """Abre no navegador um arquivo do Google Drive (documento, planilha, apresentação, PDF...).

    Use quando o usuário pedir para abrir, mostrar ou ir até um arquivo do Google.

    Args:
        nome: nome ou parte do nome do arquivo, por exemplo "Gastos de novembro".
    """
    safe = nome.replace("'", "\\'")
    files = service("drive", "v3").files().list(
        q=f"name contains '{safe}' and trashed=false", orderBy="modifiedTime desc",
        pageSize=1, fields="files(name,webViewLink)",
    ).execute().get("files", [])
    if not files:
        return f"Não encontrei nenhum arquivo com '{nome}' no seu Google Drive."
    webbrowser.open(files[0]["webViewLink"])
    return f"Abri '{files[0]['name']}' no navegador."
