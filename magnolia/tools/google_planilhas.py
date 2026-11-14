"""Google Planilhas: criar, ler e adicionar linhas."""

import webbrowser

from magnolia.google_auth import SHEET_MIME, find_file_id, service
from magnolia.tools import tool


@tool
def planilha_criar(titulo: str, cabecalho: str = "") -> str:
    """Cria uma planilha nova no Google Planilhas.

    Args:
        titulo: nome da planilha.
        cabecalho: nomes das colunas separados por vírgula, por exemplo "Data, Gasto, Valor".
    """
    sheets = service("sheets", "v4").spreadsheets()
    created = sheets.create(body={"properties": {"title": titulo}}, fields="spreadsheetId,spreadsheetUrl").execute()
    if cabecalho:
        sheets.values().update(
            spreadsheetId=created["spreadsheetId"], range="A1",
            valueInputOption="USER_ENTERED", body={"values": [[c.strip() for c in cabecalho.split(",")]]},
        ).execute()
    webbrowser.open(created["spreadsheetUrl"])  # já abre para o usuário ver
    return f"Planilha '{titulo}' criada e aberta no navegador: {created['spreadsheetUrl']}"


@tool
def planilha_ler(planilha: str, intervalo: str = "A1:Z100") -> str:
    """Lê o conteúdo de uma planilha do Google.

    Args:
        planilha: nome, link ou ID da planilha.
        intervalo: células a ler no formato do Excel, por exemplo "A1:D20" ou "Página1!A:C".
    """
    sheet_id = find_file_id(planilha, SHEET_MIME)
    rows = service("sheets", "v4").spreadsheets().values().get(
        spreadsheetId=sheet_id, range=intervalo).execute().get("values", [])
    if not rows:
        return "A planilha está vazia nesse intervalo."
    return "\n".join(" | ".join(row) for row in rows[:100])


@tool
def planilha_adicionar_linha(planilha: str, valores: list[str]) -> str:
    """Adiciona uma linha no fim de uma planilha do Google.

    Args:
        planilha: nome, link ou ID da planilha.
        valores: valores de cada coluna, em ordem, por exemplo ["13/11", "Mercado", "85,90"].
    """
    sheet_id = find_file_id(planilha, SHEET_MIME)
    service("sheets", "v4").spreadsheets().values().append(
        spreadsheetId=sheet_id, range="A1", valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS", body={"values": [valores]},
    ).execute()
    return f"Linha adicionada: {' | '.join(valores)}"
