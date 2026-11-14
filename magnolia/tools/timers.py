"""Timer, cronômetro e alarme, com contagem na tela e som ao terminar."""

import threading
import time
from datetime import datetime, timedelta

from magnolia import alerts
from magnolia.tools import tool

_timers: dict[int, dict] = {}   # {id: {"id", "nome", "tipo", "fim", "duracao", "_thread"}}
_stopwatch: dict = {}           # {"inicio": epoch} enquanto estiver rodando
_next_id = 1
_lock = threading.Lock()


def state() -> dict:
    """Timers e cronômetro atuais, para a tela mostrar a contagem."""
    with _lock:
        timers = [{k: v for k, v in t.items() if not k.startswith("_")}
                  for t in sorted(_timers.values(), key=lambda t: t["fim"])]
    return {"timers": timers, "cronometro": dict(_stopwatch) or None}


def _format(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h}h{m:02d}min"
    if m:
        return f"{m} min" + (f" e {s} s" if s else "")
    return f"{s} s"


def _start(name: str, kind: str, seconds: float) -> dict:
    global _next_id
    with _lock:
        tid = _next_id
        _next_id += 1

    def fire():
        with _lock:
            item = _timers.pop(tid, None)
        if item:
            alerts.ring(kind, f"{item['nome']} terminou!" if kind == "timer" else item["nome"])
            alerts.changed(state())

    thread = threading.Timer(seconds, fire)
    thread.daemon = True
    item = {"id": tid, "nome": name, "tipo": kind, "fim": time.time() + seconds, "duracao": seconds,
            "_thread": thread}
    with _lock:
        _timers[tid] = item
    thread.start()
    alerts.changed(state())
    return item


def cancel(tid: int) -> bool:
    with _lock:
        item = _timers.pop(int(tid), None)
    if item:
        item["_thread"].cancel()
        alerts.changed(state())
    return item is not None


def stop_stopwatch() -> float | None:
    if not _stopwatch:
        return None
    elapsed = time.time() - _stopwatch.pop("inicio")
    alerts.changed(state())
    return elapsed


# ── Ferramentas ─────────────────────────────────────────────────────────────
@tool
def criar_timer(minutos: int = 0, segundos: int = 0, nome: str = "") -> str:
    """Cria um timer (contagem regressiva) que aparece na tela e toca um som ao terminar.

    Args:
        minutos: duração em minutos.
        segundos: segundos a mais (ou só segundos).
        nome: para que é o timer, por exemplo "macarrão" (opcional).
    """
    total = max(0, minutos) * 60 + max(0, segundos)
    if total <= 0:
        return "Preciso saber quanto tempo: em minutos ou segundos."
    item = _start(nome.strip() or "Timer", "timer", total)
    return f"Timer '{item['nome']}' de {_format(total)} iniciado."


@tool
def criar_alarme(horario: str, nome: str = "Alarme") -> str:
    """Cria um alarme com som para uma hora do dia. Ele aparece na tela com a contagem.

    Args:
        horario: hora no formato HH:MM, por exemplo "06:30".
        nome: nome do alarme, por exemplo "Acordar" (opcional).
    """
    h, m = map(int, horario.split(":"))
    now = datetime.now()
    when = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if when <= now:
        when += timedelta(days=1)  # já passou hoje: fica para amanhã
    _start(nome.strip() or "Alarme", "alarme", (when - now).total_seconds())
    day = "hoje" if when.date() == now.date() else "amanhã"
    return f"Alarme '{nome}' marcado para {day} às {when:%H:%M}."


@tool
def ver_timers() -> str:
    """Mostra os timers e alarmes ativos e quanto falta para cada um."""
    current = state()
    lines = [f"#{t['id']} {t['nome']}: faltam {_format(t['fim'] - time.time())}" for t in current["timers"]]
    if current["cronometro"]:
        lines.append(f"Cronômetro rodando há {_format(time.time() - current['cronometro']['inicio'])}.")
    return "\n".join(lines) or "Nenhum timer, alarme ou cronômetro ativo."


@tool
def cancelar_timer(qual: str = "") -> str:
    """Cancela um timer ou alarme pelo nome ou número. Vazio = cancela o que termina primeiro.

    Args:
        qual: nome ou número do timer, por exemplo "macarrão" ou "2" (opcional).
    """
    timers = state()["timers"]
    if not timers:
        return "Não há timers nem alarmes ativos."
    target = timers[0]
    if qual:
        target = next((t for t in timers if str(t["id"]) == qual.strip("# ")
                       or qual.lower() in t["nome"].lower()), None)
        if not target:
            return f"Não achei um timer com '{qual}'."
    cancel(target["id"])
    return f"'{target['nome']}' cancelado."


@tool
def iniciar_cronometro() -> str:
    """Inicia um cronômetro (contagem para cima), que aparece na tela."""
    if _stopwatch:
        return f"O cronômetro já está rodando há {_format(time.time() - _stopwatch['inicio'])}."
    _stopwatch["inicio"] = time.time()
    alerts.changed(state())
    return "Cronômetro iniciado."


@tool
def parar_cronometro() -> str:
    """Para o cronômetro e diz quanto tempo passou."""
    elapsed = stop_stopwatch()
    return f"Cronômetro parado em {_format(elapsed)}." if elapsed is not None else "O cronômetro não está rodando."
