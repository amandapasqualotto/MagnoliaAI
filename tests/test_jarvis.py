"""Testes do Jarvis. Rode com:  python -m pytest

Nenhum teste usa a internet nem gasta cota da API: as chamadas externas são
substituídas por "dublês" (mocks).
"""

from datetime import datetime, timedelta

import pytest

from jarvis import config, memory
from jarvis.tools import load_tools, run_tool


@pytest.fixture(autouse=True)
def temp_memory(tmp_path, monkeypatch):
    """Cada teste usa um arquivo de memória temporário."""
    monkeypatch.setattr(config, "MEMORY_FILE", tmp_path / "memory.json")


def test_tools_are_discovered():
    names = {f.__name__ for f in load_tools()}
    assert {"pesquisar_na_web", "previsao_do_tempo", "criar_lembrete", "lembrar_fato"} <= names


def test_every_tool_has_a_description():
    for f in load_tools():
        assert f.__doc__ and len(f.__doc__.strip()) > 10, f"{f.__name__} precisa de docstring"


def test_run_tool_never_crashes():
    assert "não existe" in run_tool("ferramenta_inventada", {})
    assert "Erro" in run_tool("contar_dias_ate", {"data": "data-invalida"})


def test_memory_roundtrip():
    run_tool("lembrar_fato", {"fato": "Gosta de café sem açúcar"})
    assert "café" in run_tool("listar_memoria", {})
    assert "café" in memory.facts_for_prompt()
    assert "1 fato" in run_tool("esquecer_fato", {"termo": "CAFÉ"})
    assert memory.load_facts() == []


def test_count_days():
    future = (datetime.now() + timedelta(days=10)).strftime("%d/%m/%Y")
    assert "Faltam 10 dias" in run_tool("contar_dias_ate", {"data": future})


def test_reminders():
    out = run_tool("criar_lembrete", {"mensagem": "beber água", "minutos": 30})
    assert "criado" in out
    number = int(out.split("#")[1].split()[0])
    assert "beber água" in run_tool("listar_lembretes", {})
    assert "cancelado" in run_tool("cancelar_lembrete", {"numero": number})
    assert "Preciso saber quando" in run_tool("criar_lembrete", {"mensagem": "x"})


def test_weather_parses_api(monkeypatch):
    from jarvis.tools import clima

    class FakeResponse:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    def fake_get(url, params, timeout):
        if "geocoding" in url:
            return FakeResponse({"results": [{"name": "Campo Grande", "admin1": "MS",
                                              "latitude": -20.4, "longitude": -54.6}]})
        return FakeResponse({
            "current": {"temperature_2m": 31, "apparent_temperature": 33,
                        "relative_humidity_2m": 40, "weather_code": 0},
            "daily": {"time": ["2026-11-13"], "temperature_2m_min": [22], "temperature_2m_max": [34],
                      "precipitation_probability_max": [10], "weather_code": [1]},
        })

    monkeypatch.setattr(clima.requests, "get", fake_get)
    out = clima.previsao_do_tempo("Campo Grande")
    assert "31°C" in out and "céu limpo" in out and "máx 34°C" in out


def test_brain_falls_back_to_next_model(monkeypatch):
    """Se o primeiro modelo estourar a cota (429), o Jarvis tenta o próximo."""
    from google.genai import errors

    from jarvis.brain import Brain

    monkeypatch.setattr(config, "TEXT_MODELS", ["modelo-a", "modelo-b"])

    class FakeChat:
        def __init__(self, model):
            self.model = model

        def send_message(self, msg):
            if self.model == "modelo-a":
                raise errors.APIError(429, {"error": {"message": "quota"}})
            return type("R", (), {"text": f"resposta do {self.model}"})()

        def get_history(self):
            return []

    class FakeClient:
        class chats:
            @staticmethod
            def create(model, history, config):
                return FakeChat(model)

    brain = Brain(client=FakeClient())
    assert brain.ask("oi") == "resposta do modelo-b"
    assert brain.model == "modelo-b"


def test_voice_config_builds(monkeypatch):
    """A configuração do modo voz monta as ferramentas sem precisar de microfone."""
    try:
        import sounddevice  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("sounddevice/PortAudio indisponível nesta máquina")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "chave-falsa")
    from jarvis.voice import VoiceSession

    cfg = VoiceSession()._build_config()
    names = {d.name for d in cfg.tools[0].function_declarations}
    assert "previsao_do_tempo" in names
