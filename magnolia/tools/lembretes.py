"""Notificações na área de trabalho e lembretes com hora marcada."""

import threading
from datetime import datetime, timedelta

from magnolia import config
from magnolia.tools import tool

# Lembretes ativos nesta sessão: {id: (horário, texto, timer)}
_reminders: dict[int, tuple[datetime, str, threading.Timer]] = {}
_next_id = 1


def pending() -> list[dict]:
    """Lembretes pendentes, para mostrar na tela."""
    return [{"id": rid, "quando": f"{w:%d/%m %H:%M}", "texto": msg}
            for rid, (w, msg, _) in sorted(_reminders.items())]


def notify(title: str, message: str) -> bool:
    """Mostra uma notificação do sistema. Devolve False se não for possível."""
    print(f"\n🔔 {title}: {message}")
    try:
        from plyer import notification

        notification.notify(title=title, message=message, app_name=config.ASSISTANT_NAME, timeout=10)
        return True
    except Exception:  # noqa: BLE001 - sem suporte a notificações neste sistema
        return False


@tool
def enviar_notificacao(mensagem: str) -> str:
    """Mostra uma notificação na área de trabalho agora.

    Args:
        mensagem: texto da notificação.
    """
    ok = notify(config.ASSISTANT_NAME, mensagem)
    return "Notificação enviada." if ok else "Mostrei a mensagem no terminal (notificações do sistema indisponíveis)."


@tool
def criar_lembrete(mensagem: str, minutos: int = 0, horario: str = "") -> str:
    """Cria um lembrete que dispara uma notificação no momento certo.

    Informe OU `minutos` (daqui a quanto tempo) OU `horario` (hora do dia, HH:MM).

    Args:
        mensagem: do que lembrar.
        minutos: daqui a quantos minutos lembrar.
        horario: hora do dia no formato HH:MM, por exemplo "14:30".
    """
    global _next_id
    now = datetime.now()
    if horario:
        h, m = map(int, horario.split(":"))
        when = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if when <= now:
            when += timedelta(days=1)  # já passou hoje: fica para amanhã
    elif minutos > 0:
        when = now + timedelta(minutes=minutos)
    else:
        return "Preciso saber quando: em quantos minutos ou em qual horário."

    rid = _next_id
    _next_id += 1

    def fire():
        _reminders.pop(rid, None)
        from magnolia import alerts

        alerts.ring("lembrete", mensagem)  # notificação + som

    timer = threading.Timer((when - now).total_seconds(), fire)
    timer.daemon = True  # não impede o programa de fechar
    timer.start()
    _reminders[rid] = (when, mensagem, timer)
    return f"Lembrete #{rid} criado para {when:%d/%m às %H:%M}: {mensagem}"


@tool
def listar_lembretes() -> str:
    """Lista os lembretes pendentes."""
    if not _reminders:
        return "Nenhum lembrete pendente."
    return "\n".join(f"#{rid} às {w:%d/%m %H:%M}: {msg}" for rid, (w, msg, _) in sorted(_reminders.items()))


@tool
def cancelar_lembrete(numero: int) -> str:
    """Cancela um lembrete pelo número.

    Args:
        numero: número do lembrete (veja em listar_lembretes).
    """
    item = _reminders.pop(numero, None)
    if not item:
        return f"Não existe lembrete #{numero}."
    item[2].cancel()
    return f"Lembrete #{numero} cancelado."
