"""Data, hora e cálculos com datas."""

from datetime import datetime, timedelta

from jarvis.prompt import WEEKDAYS
from jarvis.tools import tool


@tool
def data_e_hora_atual() -> str:
    """Devolve a data, o dia da semana e a hora exata de agora."""
    now = datetime.now()
    return f"{WEEKDAYS[now.weekday()]}, {now:%d/%m/%Y}, {now:%H:%M}"


@tool
def contar_dias_ate(data: str) -> str:
    """Conta quantos dias faltam até uma data.

    Args:
        data: data no formato DD/MM/AAAA, por exemplo 25/12/2026.
    """
    target = datetime.strptime(data, "%d/%m/%Y").date()
    days = (target - datetime.now().date()).days
    if days < 0:
        return f"Essa data já passou há {-days} dias."
    return f"Faltam {days} dias para {data}."


@tool
def somar_dias(dias: int) -> str:
    """Diz qual será a data daqui a N dias (use número negativo para o passado).

    Args:
        dias: quantidade de dias a somar à data de hoje.
    """
    d = datetime.now() + timedelta(days=dias)
    return f"{WEEKDAYS[d.weekday()]}, {d:%d/%m/%Y}"
