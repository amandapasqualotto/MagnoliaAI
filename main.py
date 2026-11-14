"""Ponto de entrada da Magnólia.

    python main.py                 -> abre a janela (com login)
    python main.py --texto         -> conversa por texto no terminal
    python main.py --voz           -> conversa por voz no terminal
    python main.py --voz --ei      -> voz esperando você dizer "Ei, Magnólia"
    python main.py --atalho        -> cria o atalho na Área de Trabalho (Windows)

No terminal, use --usuario NOME para entrar numa conta. Sem isso, a
Magnólia usa a chave do arquivo .env (modo desenvolvedor).
"""

import argparse
import getpass
import sys
import time
import warnings

from magnolia import config

# Aberta pelo atalho (pythonw), não há terminal: as mensagens vão para um arquivo de log
if sys.stdout is None or sys.stderr is None:
    log = open(config.DATA_DIR / "magnolia.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log

from rich.console import Console  # noqa: E402

warnings.filterwarnings("ignore")  # esconde avisos internos das bibliotecas
console = Console()

STYLES = {"Você": "bold white", "erro": "bold red"}


def on_event(name: str, data: dict):
    """Mostra no terminal o que a Magnólia está fazendo."""
    if name == "texto":
        style = STYLES.get(data["quem"], "bold magenta")
        console.print(f"[{style}]{data['quem']}:[/] {data['texto']}")
    elif name == "ferramenta":
        console.print(f"[dim yellow]  usando {data['nome']}[/]")
    elif name == "estado" and data["estado"] == "dormindo":
        console.print("[magenta]💤 Diga \"Ei, Magnólia\"...[/]")
    elif name in ("aviso", "erro"):
        console.print(f"[{'red' if name == 'erro' else 'yellow'}]{data['texto']}[/]")


def login_terminal(username: str) -> bool:
    from magnolia import accounts

    try:
        account = accounts.login(username, getpass.getpass("Senha: "))
    except accounts.AccountError as e:
        console.print(f"[red]{e}[/]")
        return False
    account.activate()
    return True


def text_mode(assistant):
    console.print("[dim]Digite 'sair' para encerrar.[/]\n")
    while True:
        try:
            message = console.input("[bold white]Você:[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message.lower() in {"sair", "exit", "quit"}:
            break
        if message:
            with console.status("[magenta]Pensando...[/]", spinner="dots"):
                answer = assistant.ask(message)
            console.print(f"[bold magenta]{config.ASSISTANT_NAME}:[/] {answer}\n")


def voice_mode(assistant, wake_word: bool, headphones: bool):
    console.print("[magenta]Modo voz ligado. Ctrl+C para sair.[/]")
    assistant.start_voice(wake_word=wake_word, headphones=headphones)
    try:
        while assistant.voice_active:
            time.sleep(0.3)
    except KeyboardInterrupt:
        assistant.stop_voice()


def main():
    parser = argparse.ArgumentParser(description="Magnólia: sua assistente pessoal com Gemini")
    parser.add_argument("--texto", action="store_true", help="conversar por texto no terminal")
    parser.add_argument("--voz", action="store_true", help="conversar por voz no terminal")
    parser.add_argument("--ei", action="store_true", help='esperar "Ei, Magnólia" (modo voz)')
    parser.add_argument("--fone", action="store_true", help="estou de fone (permite interromper)")
    parser.add_argument("--usuario", help="entrar com uma conta da Magnólia")
    parser.add_argument("--atalho", action="store_true", help="criar atalho na Área de Trabalho (Windows)")
    args = parser.parse_args()

    if args.atalho:
        from magnolia.shortcut import create_shortcuts

        console.print(create_shortcuts())
        return

    if not (args.texto or args.voz):
        from magnolia.gui.app import run

        run()
        return

    console.print("[bold magenta]✿ Magnólia[/]")
    if args.usuario and not login_terminal(args.usuario):
        return
    if not config.GEMINI_API_KEY:
        console.print("[red]Falta a chave do Gemini.[/] Use --usuario, ou copie .env.example para .env "
                      "e cole sua chave de https://aistudio.google.com/apikey")
        return

    from magnolia.assistant import Assistant

    assistant = Assistant(on_event=on_event)
    if args.voz:
        voice_mode(assistant, args.ei, args.fone)
    else:
        text_mode(assistant)
    console.print("[magenta]Até logo.[/]")


if __name__ == "__main__":
    main()
