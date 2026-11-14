"""Cria atalhos da Magnólia na Área de Trabalho e no Menu Iniciar (Windows).

O atalho abre a Magnólia com o "pythonw", a versão do Python que roda sem a
tela preta do terminal. As mensagens que apareceriam no terminal vão para o
arquivo data/magnolia.log (útil para descobrir problemas).

Uso (uma vez só):  python main.py --atalho
"""

import base64
import platform
import subprocess
import sys
from pathlib import Path

from magnolia import config

ICON = Path(__file__).parent / "gui" / "web" / "favicon.ico"


def _ps_quote(value) -> str:
    """Texto entre aspas simples para o PowerShell (aspas internas são dobradas)."""
    return "'" + str(value).replace("'", "''") + "'"


def build_script(pythonw: Path, main: Path, root: Path, icon: Path) -> str:
    """Script do PowerShell que cria os dois atalhos."""
    return f"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$folders = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
foreach ($folder in $folders) {{
    $path = Join-Path $folder 'Magnolia.lnk'
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = {_ps_quote(pythonw)}
    $link.Arguments = {_ps_quote(f'"{main}"')}
    $link.WorkingDirectory = {_ps_quote(root)}
    $link.IconLocation = {_ps_quote(icon)}
    $link.Description = 'Magnolia, sua assistente pessoal'
    $link.Save()
    if (-not (Test-Path $path)) {{ throw "O atalho nao foi criado em $folder" }}
    Write-Output $path
}}
"""


def create_shortcuts() -> str:
    if platform.system() != "Windows":
        return "Os atalhos automáticos são só para Windows. Use: python main.py"
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = python
    script = build_script(pythonw, config.ROOT_DIR / "main.py", config.ROOT_DIR, ICON)
    # -EncodedCommand evita qualquer problema com acentos, espaços e parênteses nos caminhos
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-EncodedCommand", encoded], capture_output=True)
    created = [line for line in result.stdout.decode(errors="ignore").splitlines() if line.endswith(".lnk")]
    # Só diz que deu certo se o próprio Windows confirmou que os arquivos existem
    if result.returncode != 0 or not created or not all(Path(c).exists() for c in created):
        error = result.stderr.decode(errors="ignore").strip()[:400] or "o PowerShell não confirmou a criação."
        return f"Não consegui criar o atalho: {error}"
    return "Pronto! Atalho criado em:\n" + "\n".join(created)
