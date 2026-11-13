"""Informações e controle básico do computador."""

import platform
import shutil
import subprocess
import sys

import psutil

from jarvis.tools import tool


@tool
def status_do_computador() -> str:
    """Mostra uso de CPU, memória RAM, disco e bateria do computador."""
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    info = (
        f"CPU em {cpu}%. RAM: {ram.percent}% usada de {ram.total / 1e9:.1f} GB. "
        f"Disco: {disk.percent}% usado, {disk.free / 1e9:.0f} GB livres."
    )
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if battery:
        plug = "carregando" if battery.power_plugged else "na bateria"
        info += f" Bateria em {battery.percent:.0f}%, {plug}."
    return info


@tool
def abrir_programa(nome: str) -> str:
    """Abre um programa instalado no computador.

    Args:
        nome: nome do programa, por exemplo "notepad", "calc", "spotify", "code".
    """
    system = platform.system()
    nome = nome.replace('"', "").replace("&", "").replace("|", "").strip()
    try:
        if system == "Windows":
            # "start" usa o mesmo mecanismo do menu Executar (Win+R)
            subprocess.Popen(f'start "" "{nome}"', shell=True)
        elif system == "Darwin":  # macOS
            subprocess.Popen(["open", "-a", nome])
        else:  # Linux
            if not shutil.which(nome):
                return f"Não encontrei o programa '{nome}' neste computador."
            subprocess.Popen([nome], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        return f"Não consegui abrir '{nome}': {e}"
    return f"Pedi para o sistema abrir '{nome}'."


@tool
def programas_pesados() -> str:
    """Lista os 5 programas que mais estão usando memória RAM agora."""
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            procs.append((p.info["memory_info"].rss, p.info["name"]))
        except (psutil.Error, TypeError, AttributeError):
            continue
    top = sorted(procs, reverse=True)[:5]
    return "\n".join(f"{name}: {rss / 1e6:.0f} MB" for rss, name in top)


@tool
def sobre_o_sistema() -> str:
    """Diz qual sistema operacional e versão do Python o Jarvis está usando."""
    return f"{platform.system()} {platform.release()}, Python {sys.version.split()[0]}"
