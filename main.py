"""Ponto de entrada do Jarvis.

    python main.py            -> conversa por texto (digitando)
    python main.py --voz      -> conversa por voz (microfone e caixa de som)
    python main.py --voz --fone   -> modo voz usando fone (permite interromper o Jarvis)
"""

import argparse
import asyncio
import warnings

from rich.console import Console
from rich.panel import Panel

from jarvis import config

warnings.filterwarnings("ignore")  # esconde avisos internos das bibliotecas
console = Console()

BANNER = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
   Just A Rather Very Intelligent System
"""

COLORS = {"Você": "bold white", "⚙": "dim yellow", "⚡": "bold cyan"}


def show(speaker: str, text: str):
    style = COLORS.get(speaker, "bold cyan")
    console.print(f"[{style}]{speaker}:[/] {text}")


def text_mode():
    from jarvis.brain import Brain

    brain = Brain()
    console.print(f"[dim]Modelo: {brain.model} · {len(brain.tools)} habilidades · digite 'sair' para encerrar[/]\n")
    while True:
        try:
            message = console.input("[bold white]Você:[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message.lower() in {"sair", "exit", "quit"}:
            break
        if not message:
            continue
        with console.status("[cyan]Processando...[/]", spinner="dots"):
            answer = brain.ask(message)
        show(config.ASSISTANT_NAME, answer + "\n")
    console.print("[cyan]Até logo.[/]")


def voice_mode(headphones: bool):
    from jarvis.voice import VoiceSession

    try:
        asyncio.run(VoiceSession(headphones=headphones, on_text=show).run())
    except KeyboardInterrupt:
        console.print("\n[cyan]Desligando. Até logo.[/]")


def main():
    parser = argparse.ArgumentParser(description="JARVIS: seu assistente pessoal com Gemini")
    parser.add_argument("--voz", action="store_true", help="conversar por voz")
    parser.add_argument("--fone", action="store_true", help="estou de fone (permite interromper)")
    args = parser.parse_args()

    console.print(Panel.fit(BANNER, border_style="cyan"))
    if not config.GEMINI_API_KEY:
        console.print("[red]Falta a chave do Gemini.[/] Copie [bold].env.example[/] para [bold].env[/] "
                      "e cole sua chave de https://aistudio.google.com/apikey")
        return
    if args.voz:
        voice_mode(args.fone)
    else:
        text_mode()


if __name__ == "__main__":
    main()
