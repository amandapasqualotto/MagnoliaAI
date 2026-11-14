"""Testes da Magnólia. Rode com:  python -m pytest

Nenhum teste usa a internet nem gasta cota da API: as chamadas externas são
substituídas por "dublês" (mocks).
"""

from datetime import datetime, timedelta

import pytest

from magnolia import accounts, config, memory
from magnolia.tools import load_tools, run_tool


@pytest.fixture(autouse=True)
def temp_data(tmp_path, monkeypatch):
    """Cada teste usa pastas temporárias, sem tocar nos seus dados reais."""
    monkeypatch.setattr(config, "USER_DIR", tmp_path / "dev")
    monkeypatch.setattr(config, "MEMORY_FILE", tmp_path / "dev" / "memory.json")
    monkeypatch.setattr(config, "CIPHER", None)
    monkeypatch.setattr(accounts, "USERS_DIR", tmp_path / "usuarios")


def test_tools_are_discovered():
    names = {f.__name__ for f in load_tools()}
    assert {"pesquisar_na_web", "previsao_do_tempo", "criar_lembrete", "lembrar_fato",
            "agenda_criar_compromisso", "planilha_adicionar_linha", "gmail_criar_rascunho"} <= names


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
    from magnolia.tools import clima

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
    """Se o primeiro modelo estourar a cota (429), a Magnólia tenta o próximo."""
    from google.genai import errors

    from magnolia.brain import Brain

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
    from magnolia.voice import VoiceSession

    cfg = VoiceSession()._build_config()
    names = {d.name for d in cfg.tools[0].function_declarations}
    assert "previsao_do_tempo" in names


# ── Contas ──────────────────────────────────────────────────────────────────
def test_account_create_and_login(monkeypatch):
    monkeypatch.setattr(accounts, "ITERATIONS", 1000)  # mais rápido nos testes
    accounts.create_account("Amanda", "segredo123", "Amanda", "minha-chave-secreta", "Campo Grande")
    assert accounts.list_accounts() == ["amanda"]

    # A chave e a senha nunca ficam legíveis no arquivo
    raw = (accounts.USERS_DIR / "amanda" / "account.json").read_text()
    assert "minha-chave-secreta" not in raw and "segredo123" not in raw

    with pytest.raises(accounts.AccountError):
        accounts.login("amanda", "senha-errada")

    account = accounts.login("amanda", "segredo123")
    account.activate()
    assert config.GEMINI_API_KEY == "minha-chave-secreta"
    assert config.MEMORY_FILE == accounts.USERS_DIR / "amanda" / "memory.json"


def test_account_validation(monkeypatch):
    monkeypatch.setattr(accounts, "ITERATIONS", 1000)
    with pytest.raises(accounts.AccountError, match="6 caracteres"):
        accounts.create_account("amanda", "123", "Amanda", "chave")
    with pytest.raises(accounts.AccountError, match="usuário"):
        accounts.create_account("a b", "123456", "Amanda", "chave")
    accounts.create_account("amanda", "123456", "Amanda", "chave")
    with pytest.raises(accounts.AccountError, match="já existe"):
        accounts.create_account("amanda", "123456", "Amanda", "chave")


def test_memory_is_separate_per_account(monkeypatch):
    monkeypatch.setattr(accounts, "ITERATIONS", 1000)
    accounts.create_account("ana", "123456", "Ana", "k1").activate()
    run_tool("lembrar_fato", {"fato": "Ana gosta de chá"})
    accounts.create_account("bia", "123456", "Bia", "k2").activate()
    assert "chá" not in run_tool("listar_memoria", {})


# ── "Ei, Magnólia" ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("heard, expected", [
    ("ei magnólia", True), ("magnolia", True), ("ei magnolha", True), ("mangólia que horas são", True),
    ("bom dia", False), ("magnífico", False), ("", False),
])
def test_wake_word(heard, expected):
    from magnolia.wakeword import heard_wake_word

    assert heard_wake_word(heard) is expected


# ── Google ──────────────────────────────────────────────────────────────────
def test_google_tools_explain_when_not_connected():
    out = run_tool("agenda_proximos_compromissos", {"dias": 3})
    assert "não está conectada" in out


def test_google_finds_id_from_link():
    from magnolia.google_auth import SHEET_MIME, find_file_id

    link = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit#gid=0"
    assert find_file_id(link, SHEET_MIME) == "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"


# ── Interface (sem abrir janela) ────────────────────────────────────────────
def test_gui_api_flow(monkeypatch):
    monkeypatch.setattr(accounts, "ITERATIONS", 1000)
    from magnolia.gui.app import Api

    api = Api()
    assert api.create_account({"usuario": "x", "senha": "123456", "nome": "X", "chave": "k"})["ok"] is False
    info = api.create_account({"usuario": "amanda", "senha": "123456", "nome": "Amanda", "chave": "k"})
    assert info["ok"] and info["nome"] == "Amanda" and "Kore" in info["vozes"]
    assert api.save_settings({"voz": "Aoede", "cidade": "São Paulo"})["config"]["voz"] == "Aoede"
    assert config.VOICE_NAME == "Aoede" and config.DEFAULT_CITY == "São Paulo"
    assert "cpu" in api.status()
    api.logout()
    assert api.login("amanda", "errada")["ok"] is False
    assert api.login("amanda", "123456")["config"]["cidade"] == "São Paulo"


# ── Favoritos do navegador ──────────────────────────────────────────────────
def test_bookmarks(tmp_path):
    import json

    from magnolia.tools import favoritos

    profile = tmp_path / "Chrome" / "Default"
    profile.mkdir(parents=True)
    (profile / "Bookmarks").write_text(json.dumps({"roots": {
        "bookmark_bar": {"type": "folder", "name": "Barra de favoritos", "children": [
            {"type": "url", "name": "AVA UFMS", "url": "https://ava.ufms.br"},
            {"type": "folder", "name": "Estágio", "children": [
                {"type": "url", "name": "Gupy - vagas", "url": "https://portal.gupy.io"}]},
        ]},
        "other": {"type": "folder", "name": "Outros", "children": []},
    }}), encoding="utf-8")

    marks = favoritos.load_bookmarks([tmp_path / "Chrome"])
    assert len(marks) == 2
    assert favoritos.search_bookmarks("ava ufms", marks)[0]["url"] == "https://ava.ufms.br"
    assert favoritos.search_bookmarks("estagio", marks)[0]["nome"] == "Gupy - vagas"  # pela pasta, sem acento
    assert favoritos.search_bookmarks("receita de bolo", marks) == []


# ── Documentos anexados ─────────────────────────────────────────────────────
def _make_pdf(path, lines):
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    for i, line in enumerate(lines):
        c.drawString(72, 800 - 20 * i, line)
    c.save()


# ── Servidor da interface ───────────────────────────────────────────────────
def test_server_security_and_api(monkeypatch, tmp_path):
    import json
    import urllib.error
    import urllib.request

    monkeypatch.setattr(accounts, "ITERATIONS", 1000)
    from magnolia.gui.app import Api
    from magnolia.gui.server import start_server

    server, url = start_server(Api())
    base, token = url.split("/?t=")

    def post(path, body=b"[]", with_token=True):
        headers = {"X-Token": token} if with_token else {}
        req = urllib.request.Request(base + path, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None

    try:
        assert post("/api/list_accounts", with_token=False)[0] == 403   # sem código secreto
        assert post("/api/__init__")[0] == 404                           # fora da lista permitida
        assert post("/api/list_accounts") == (200, [])
        form = json.dumps([{"usuario": "amanda", "senha": "123456", "nome": "Amanda", "chave": "k"}]).encode()
        assert post("/api/create_account", form)[1]["ok"] is True
        status, result = post("/anexar?nome=notas.txt&colecoes=liga", "Reunião na quinta".encode())
        assert status == 200 and result["adicionados"] == ["notas"]
        assert result["biblioteca"]["colecoes"] == ["liga"]
        with urllib.request.urlopen(base + "/") as r:                    # a página abre
            assert b"Magn" in r.read()
    finally:
        server.shutdown()


# ── Escolha automática de modelos ───────────────────────────────────────────
def test_pick_models_from_what_the_key_can_use(monkeypatch):
    import types as pytypes

    from magnolia import models

    models._cache.clear()
    monkeypatch.setattr(config, "TEXT_MODELS", ["gemini-flash-latest", "gemini-flash-lite-latest"])
    monkeypatch.setattr(config, "LIVE_MODEL", "gemini-3.1-flash-live-preview")
    available = [
        ("gemini-2.5-flash", ["generateContent"]), ("gemini-3.5-flash", ["generateContent"]),
        ("gemini-3.5-flash-lite", ["generateContent"]), ("gemini-3.6-flash-preview", ["generateContent"]),
        ("gemini-3.5-flash-image", ["generateContent"]), ("gemini-3.5-pro", ["generateContent"]),
        ("gemini-2.5-flash-native-audio", ["bidiGenerateContent"]),
        ("gemini-3.2-flash-live", ["bidiGenerateContent"]), ("text-embedding-004", ["embedContent"]),
    ]
    fake = pytypes.SimpleNamespace(models=pytypes.SimpleNamespace(list=lambda: [
        pytypes.SimpleNamespace(name=f"models/{n}", supported_actions=a) for n, a in available]))

    # Os nomes da configuração não existem para esta chave: escolhe pelo que existe
    assert models.pick_text_models(fake) == [
        "gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash-preview"]
    assert models.pick_live_model(fake) == "gemini-3.2-flash-live"


def test_pick_models_without_internet_uses_config():
    import types as pytypes

    from magnolia import models

    models._cache.clear()

    def boom():
        raise OSError("sem internet")

    fake = pytypes.SimpleNamespace(models=pytypes.SimpleNamespace(list=boom))
    assert models.pick_text_models(fake) == config.TEXT_MODELS
    assert models.pick_live_model(fake) == config.LIVE_MODEL


# ── Biblioteca ──────────────────────────────────────────────────────────────
RSS = """<?xml version="1.0"?><rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
<title>G1</title><atom:link href="https://g1.globo.com/rss" rel="self" xmlns:atom="http://www.w3.org/2005/Atom"/>
<item><title>Dólar cai após decisão do Copom</title><link>https://g1.globo.com/a</link>
<pubDate>Fri, 13 Nov 2026 18:00:00 -0300</pubDate></item>
<item><title><![CDATA[Chuva forte em Campo Grande]]></title><link>https://g1.globo.com/b</link>
<dc:date>2026-11-13</dc:date></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>STF decide sobre prescrição</title><link href="https://mig.com/x"/><updated>2026-11-13</updated></entry>
</feed>"""

ARTICLE = """<html><head><title>Guia de prescrição civil</title><script>var x=1;</script></head>
<body><nav>Menu Home Contato</nav><h1>Prescrição no Código Civil</h1>
<p>O prazo geral de prescrição é de dez anos (art. 205).</p><p>Reparação civil: três anos.</p>
<footer>Copyright</footer></body></html>"""


@pytest.fixture
def fake_web(monkeypatch):
    import types as pytypes

    from magnolia import feeds

    pages = {
        "https://g1.globo.com": '<link rel="alternate" type="application/rss+xml" href="/rss/g1/">',
        "https://g1.globo.com/rss/g1/": RSS,
        "https://mig.com": "<html>sem feed</html>",
        "https://mig.com/feed": ATOM,
        "https://blog.com/artigo-prescricao": ARTICLE,
    }

    def fake_get(url, headers=None, timeout=None):
        text = pages.get(url)
        return pytypes.SimpleNamespace(text=text or "", ok=text is not None, url=url,
                                       headers={"Content-Type": "text/html"}, raise_for_status=lambda: None)

    monkeypatch.setattr(feeds.requests, "get", fake_get)
    return pages


def test_library_links_news_and_pages(fake_web):
    from magnolia import library

    g1 = library.add_link("www.g1.globo.com", "notícias")
    assert g1["tipo"] == "noticias" and g1["feed"] == "https://g1.globo.com/rss/g1/"
    mig = library.add_link("mig.com", "direito, Notícias")
    assert mig["tipo"] == "noticias" and mig["colecoes"] == ["direito", "notícias"]
    page = library.add_link("https://blog.com/artigo-prescricao", "direito")
    assert page["tipo"] == "pagina" and page["titulo"] == "Guia de prescrição civil"
    with pytest.raises(ValueError, match="já está"):
        library.add_link("g1.globo.com")

    # A página salva só o texto (sem menu, script e rodapé)
    text = library.read(page)
    assert "dez anos" in text and "Menu" not in text and "var x" not in text

    news = run_tool("biblioteca_noticias", {})
    assert "[g1.globo.com]" in news and "Dólar cai" in news and "STF decide" in news
    only_law = run_tool("biblioteca_noticias", {"colecao": "direito"})
    assert "STF decide" in only_law and "Dólar" not in only_law
    assert "Dólar" in run_tool("biblioteca_noticias", {"assunto": "dólar"})

    assert "três anos" in run_tool("biblioteca_buscar", {"termo": "reparação", "colecao": "direito"})
    assert "não aparece" in run_tool("biblioteca_buscar", {"termo": "reparação", "colecao": "notícias"})
    assert "Guia de prescrição" in run_tool("biblioteca_listar", {"colecao": "direito"})
    assert "Organizado" in run_tool("biblioteca_organizar", {"item": "guia", "colecoes": "faculdade"})
    assert library.find("guia")["colecoes"] == ["faculdade"]
    assert "Removido" in run_tool("biblioteca_remover", {"item": "mig.com"})
    assert library.collections() == ["faculdade", "notícias"]


def test_library_files_are_encrypted(tmp_path, monkeypatch):
    pytest.importorskip("reportlab")  # só para criar o PDF de teste
    from docx import Document

    from magnolia import library

    monkeypatch.setattr(accounts, "ITERATIONS", 1000)
    accounts.create_account("amanda", "123456", "Amanda", "k").activate()

    pdf = tmp_path / "Cronograma.pdf"
    _make_pdf(pdf, ["17/11 - Prova de Direito Civil", "18/11 - Entrega do trabalho de TI"])
    doc = Document()
    row = doc.add_table(rows=1, cols=2).rows[0]
    row.cells[0].text, row.cells[1].text = "20/11", "Seminário de Geopolítica"
    doc.save(tmp_path / "Agenda da liga.docx")

    crono = library.add_file(pdf, "faculdade")
    library.add_file(tmp_path / "Agenda da liga.docx", "liga")
    assert "Cronograma (arquivo; coleções: faculdade)" in library.for_prompt()
    assert "Direito Civil" in run_tool("biblioteca_ler", {"item": "crono"})
    hits = run_tool("biblioteca_buscar", {"termo": "20/11"})
    assert "Seminário" in hits and "[Agenda da liga]" in hits

    stored = (config.USER_DIR / "biblioteca" / f"{crono['id']}.txt").read_bytes()
    assert b"Direito Civil" not in stored
    with pytest.raises(ValueError, match="não suportado"):
        library.add_file(tmp_path / "foto.png")


def test_custom_commands():
    from magnolia import library

    out = run_tool("criar_comando", {"nome": "Resumo Jurídico",
                                     "instrucao": "Busque as novidades e resuma em 5 tópicos.",
                                     "colecoes": "direito"})
    assert '"resumo jurídico" criado' in out
    prompt = library.for_prompt()
    assert '"resumo jurídico": Busque as novidades' in prompt and "coleção: direito" in prompt
    run_tool("criar_comando", {"nome": "resumo jurídico", "instrucao": "Resuma em 3 tópicos."})
    assert len(library.commands()) == 1 and "3 tópicos" in run_tool("listar_comandos", {})
    assert run_tool("apagar_comando", {"nome": "resumo jurídico"}) == "Comando apagado."
    assert library.for_prompt() == ""


def test_old_documents_and_sources_are_migrated():
    import json

    from magnolia import library

    (config.USER_DIR / "documentos").mkdir(parents=True)
    (config.USER_DIR / "documentos" / "Cronograma.txt").write_text("17/11 prova", encoding="utf-8")
    (config.USER_DIR / "fontes.json").write_text(json.dumps([{"site": "g1.globo.com", "feed": "https://g1/rss"}]))

    items = library.load()["itens"]
    assert {(i["tipo"], i["titulo"]) for i in items} == {("arquivo", "Cronograma"), ("noticias", "g1.globo.com")}
    assert "17/11" in library.read(library.find("cronograma"))


def test_gui_library_api(tmp_path, monkeypatch, fake_web):
    monkeypatch.setattr(accounts, "ITERATIONS", 1000)
    from magnolia.gui.app import Api

    api = Api()
    api.create_account({"usuario": "amanda", "senha": "123456", "nome": "Amanda", "chave": "k"})
    note = tmp_path / "notas.txt"
    note.write_text("Reunião da liga na quinta", encoding="utf-8")
    result = api.add_files([str(note), str(tmp_path / "x.exe")], "liga")
    assert result["adicionados"] == ["notas"] and len(result["erros"]) == 1
    assert api.add_link("g1.globo.com", "notícias")["ok"] is True
    assert "já está" in api.add_link("g1.globo.com")["erro"]
    state = api.status()["biblioteca"]
    assert state["colecoes"] == ["liga", "notícias"] and len(state["itens"]) == 2
    item_id = state["itens"][0]["id"]
    assert api.organize_item(item_id, "faculdade")["itens"][0]["colecoes"] == ["faculdade"]
    assert len(api.remove_item(item_id)["itens"]) == 1
