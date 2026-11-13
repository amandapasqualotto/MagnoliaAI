"""Google Agenda: ver e criar compromissos."""

from datetime import datetime, timedelta

from magnolia.google_auth import service
from magnolia.prompt import WEEKDAYS
from magnolia.tools import tool


def _local_now() -> datetime:
    return datetime.now().astimezone()  # com fuso horário


def _describe(event: dict) -> str:
    start = event["start"].get("dateTime") or event["start"].get("date")
    if "T" in start:
        dt = datetime.fromisoformat(start)
        when = f"{WEEKDAYS[dt.weekday()]} {dt:%d/%m às %H:%M}"
    else:
        dt = datetime.fromisoformat(start)
        when = f"{WEEKDAYS[dt.weekday()]} {dt:%d/%m} (dia todo)"
    place = f" em {event['location']}" if event.get("location") else ""
    return f"{when}: {event.get('summary', '(sem título)')}{place}"


@tool
def agenda_proximos_compromissos(dias: int = 7) -> str:
    """Lista os compromissos do Google Agenda nos próximos dias.

    Args:
        dias: quantos dias à frente olhar (1 = próximas 24 horas; padrão 7).
    """
    now = _local_now()
    events = service("calendar", "v3").events().list(
        calendarId="primary", timeMin=now.isoformat(), timeMax=(now + timedelta(days=dias)).isoformat(),
        singleEvents=True, orderBy="startTime", maxResults=20,
    ).execute().get("items", [])
    if not events:
        return f"Nenhum compromisso nos próximos {dias} dias."
    return "\n".join(_describe(e) for e in events)


@tool
def agenda_criar_compromisso(titulo: str, data: str, hora: str = "", duracao_minutos: int = 60,
                             local: str = "", descricao: str = "") -> str:
    """Cria um compromisso no Google Agenda.

    Args:
        titulo: nome do compromisso.
        data: dia no formato DD/MM/AAAA.
        hora: horário de início HH:MM. Se vazio, o compromisso é de dia inteiro.
        duracao_minutos: duração em minutos (padrão 60).
        local: endereço ou link da reunião (opcional).
        descricao: observações (opcional).
    """
    day = datetime.strptime(data, "%d/%m/%Y")
    event = {"summary": titulo, "location": local, "description": descricao}
    if hora:
        h, m = map(int, hora.split(":"))
        start = day.replace(hour=h, minute=m).astimezone()
        end = start + timedelta(minutes=duracao_minutos)
        event["start"] = {"dateTime": start.isoformat()}
        event["end"] = {"dateTime": end.isoformat()}
    else:
        event["start"] = {"date": day.date().isoformat()}
        event["end"] = {"date": (day + timedelta(days=1)).date().isoformat()}

    created = service("calendar", "v3").events().insert(calendarId="primary", body=event).execute()
    return f"Compromisso criado: {_describe(created)}"


@tool
def agenda_buscar(termo: str) -> str:
    """Procura compromissos futuros no Google Agenda pelo nome.

    Args:
        termo: palavra para procurar, por exemplo "dentista".
    """
    events = service("calendar", "v3").events().list(
        calendarId="primary", q=termo, timeMin=_local_now().isoformat(),
        singleEvents=True, orderBy="startTime", maxResults=10,
    ).execute().get("items", [])
    if not events:
        return f"Nenhum compromisso futuro com '{termo}'."
    return "\n".join(_describe(e) for e in events)
