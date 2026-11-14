"""Avisos sonoros e visuais: quando um timer, alarme ou lembrete toca.

A interface gráfica se inscreve aqui para tocar o som e mostrar a contagem.
Sem interface (modo terminal), tocamos um bipe no próprio computador.
"""

import platform
import threading

# A interface coloca aqui funções para ser avisada:
listener = None   # listener(tipo, texto): algo tocou (timer, alarme, lembrete)
on_change = None  # on_change(estado): a lista de timers mudou


def beep() -> None:
    """Bipe simples, para quando não há interface aberta."""
    if platform.system() == "Windows":
        import winsound

        for _ in range(3):
            winsound.Beep(880, 220)
            winsound.Beep(1175, 220)
    else:
        print("\a", end="", flush=True)


def ring(kind: str, text: str) -> None:
    """Avisa que algo tocou: som + notificação."""
    from magnolia.tools.lembretes import notify

    notify(f"{kind.capitalize()} da Magnólia", text)
    if listener:
        listener(kind, text)
    else:
        threading.Thread(target=beep, daemon=True).start()


def changed(state: dict) -> None:
    if on_change:
        on_change(state)
