"""Previsão do tempo usando a API gratuita Open-Meteo (não precisa de chave)."""

import requests

from magnolia import config
from magnolia.tools import tool

# Tradução dos códigos de tempo da Open-Meteo (WMO)
WEATHER_CODES = {
    0: "céu limpo", 1: "predomínio de sol", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina com geada", 51: "garoa fraca", 53: "garoa",
    55: "garoa forte", 61: "chuva fraca", 63: "chuva", 65: "chuva forte",
    80: "pancadas de chuva fracas", 81: "pancadas de chuva", 82: "pancadas de chuva fortes",
    95: "trovoadas", 96: "trovoadas com granizo", 99: "trovoadas fortes com granizo",
}


def _find_city(name: str) -> dict | None:
    r = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": name, "count": 1, "language": "pt"},
        timeout=10,
    )
    r.raise_for_status()
    results = r.json().get("results")
    return results[0] if results else None


@tool
def previsao_do_tempo(cidade: str = "") -> str:
    """Mostra o tempo agora e a previsão dos próximos 3 dias para uma cidade.

    Args:
        cidade: nome da cidade. Se vazio, usa a cidade padrão do usuário.
    """
    place = _find_city(cidade or config.DEFAULT_CITY)
    if not place:
        return f"Não encontrei a cidade '{cidade}'."

    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "timezone": "auto",
            "forecast_days": 3,
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    now, daily = data["current"], data["daily"]

    lines = [
        f"{place['name']} ({place.get('admin1', '')}): agora {now['temperature_2m']}°C, "
        f"sensação de {now['apparent_temperature']}°C, umidade {now['relative_humidity_2m']}%, "
        f"{WEATHER_CODES.get(now['weather_code'], 'tempo indefinido')}."
    ]
    for i, day in enumerate(daily["time"]):
        lines.append(
            f"{day}: mín {daily['temperature_2m_min'][i]}°C, máx {daily['temperature_2m_max'][i]}°C, "
            f"{daily['precipitation_probability_max'][i]}% de chance de chuva, "
            f"{WEATHER_CODES.get(daily['weather_code'][i], '')}."
        )
    return "\n".join(lines)
