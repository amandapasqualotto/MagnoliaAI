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
    """Som de alarme tocado pelo próprio computador (quando a janela não consegue tocar)."""
    if platform.system() == "Windows":
        import winsound

        for _ in range(3):
            winsound.Beep(880, 220)
            winsound.Beep(1175, 220)
    else:
        print("\a", end="", flush=True)


def beep_async() -> None:
    threading.Thread(target=beep, daemon=True).start()


def ring(kind: str, text: str) -> None:
    """Avisa que algo tocou: primeiro o som e a tela, depois a notificação do sistema.

    A notificação do Windows pode demorar alguns segundos; por isso ela vem por
    último e numa thread separada, para não atrasar o som.
    """
    from magnolia.tools.lembretes import notify

    if listener:
        listener(kind, text)   # a janela toca o sino e anima a flor
    else:
        beep_async()           # sem janela: bipe do computador
    threading.Thread(target=notify, args=(f"{kind.capitalize()} da Magnólia", text), daemon=True).start()


def changed(state: dict) -> None:
    if on_change:
        on_change(state)
