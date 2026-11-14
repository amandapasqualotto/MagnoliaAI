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
        ("gemini-live-translate", ["bidiGenerateContent"]),
        ("gemini-3.9-flash-live-transcribe", ["bidiGenerateContent"]),
    ]
    fake = pytypes.SimpleNamespace(models=pytypes.SimpleNamespace(list=lambda: [
        pytypes.SimpleNamespace(name=f"models/{n}", supported_actions=a) for n, a in available]))

    # Os nomes da configuração não existem para esta chave: escolhe pelo que existe
    assert models.pick_text_models(fake) == [
        "gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash-preview"]
    # Voz natural prefere "native audio"; a rápida prefere o Live mais novo
    assert models.pick_live_model(fake, "natural") == "gemini-2.5-flash-native-audio"
    assert models.pick_live_model(fake, "rapida") == "gemini-3.2-flash-live"


def test_pick_models_without_internet_uses_config():
    import types as pytypes

    from magnolia import models

    models._cache.clear()

    def boom():
        raise OSError("sem internet")

    fake = pytypes.SimpleNamespace(models=pytypes.SimpleNamespace(list=boom))
    assert models.pick_text_models(fake) == config.TEXT_MODELS
    assert models.pick_live_model(fake, "natural") == config.LIVE_MODELS_BY_STYLE["natural"][0]
    assert models.pick_live_model(fake, "rapida") == config.LIVE_MODEL


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
        page = pages.get(url)
        content_type = "text/html"
        if isinstance(page, tuple):  # (tipo de conteúdo, bytes) para links de arquivos
            content_type, page = page
        data = page if isinstance(page, bytes) else (page or "").encode()
        return pytypes.SimpleNamespace(text=data.decode(errors="ignore"), content=data, ok=page is not None,
                                       url=url, headers={"Content-Type": content_type},
                                       raise_for_status=lambda: None)

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
    assert api.add_link("   ")["ok"] is False
    state = api.status()["biblioteca"]
    assert state["colecoes"] == ["liga", "notícias"] and len(state["itens"]) == 2
    item_id = state["itens"][0]["id"]
    assert api.organize_item(item_id, "faculdade")["itens"][0]["colecoes"] == ["faculdade"]
    assert len(api.remove_item(item_id)["itens"]) == 1


def test_gemini_client_uses_v1beta(monkeypatch):
    """A conversa por voz (Live API) só existe na v1beta; a biblioteca usa v1 por padrão."""
    from magnolia.models import make_client

    monkeypatch.setattr(config, "GEMINI_API_KEY", "chave-falsa")
    options = make_client(timeout_seconds=45)._api_client._http_options
    assert options.api_version == "v1beta" and options.timeout == 45_000


def test_shortcut_script_handles_tricky_paths():
    from pathlib import Path

    from magnolia.shortcut import build_script

    root = Path(r"C:\Users\LUCIANO\Downloads\magnolia (1)\magnolia d'Amanda")
    script = build_script(root / ".venv/Scripts/pythonw.exe", root / "main.py", root, root / "favicon.ico")
    assert "magnolia (1)\\magnolia d''Amanda" in script        # aspas simples dobradas
    assert "GetFolderPath('Desktop')" in script and "GetFolderPath('Programs')" in script
    assert "Magnolia.lnk" in script and "Test-Path" in script and "ErrorActionPreference = 'Stop'" in script
    script.encode("utf-16-le")                                 # pode ir no -EncodedCommand


def test_shortcut_only_reports_success_when_files_exist(monkeypatch, tmp_path):
    import types as pytypes

    from magnolia import shortcut

    monkeypatch.setattr(shortcut.platform, "system", lambda: "Windows")
    # O PowerShell "termina bem" mas não cria nada: tem que avisar que falhou
    monkeypatch.setattr(shortcut.subprocess, "run",
                        lambda *a, **k: pytypes.SimpleNamespace(returncode=0, stdout=b"", stderr=b""))
    assert shortcut.create_shortcuts().startswith("Não consegui")

    link = tmp_path / "Magnolia.lnk"
    link.write_text("x")
    output = f"{link}\r\n".encode()
    monkeypatch.setattr(shortcut.subprocess, "run",
                        lambda *a, **k: pytypes.SimpleNamespace(returncode=0, stdout=output, stderr=b""))
    assert "Pronto" in shortcut.create_shortcuts()


# ── Leitura de mais formatos e links de arquivos ────────────────────────────
def test_readers_for_office_html_and_json(tmp_path):
    import json

    from openpyxl import Workbook
    from pptx import Presentation
    from pptx.util import Inches

    from magnolia.readers import extract_file_text

    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "Plano de estudos"
    box = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(5), Inches(1))
    box.text_frame.text = "Revisar Direito Civil na segunda"
    deck.save(tmp_path / "aula.pptx")
    assert "[slide 1]" in (text := extract_file_text(tmp_path / "aula.pptx")) and "Direito Civil" in text

    book = Workbook()
    book.active.title = "Gastos"
    book.active.append(["Data", "Item", "Valor"])
    book.active.append(["14/11", "Mercado", 85.9])
    book.save(tmp_path / "gastos.xlsx")
    text = extract_file_text(tmp_path / "gastos.xlsx")
    assert "[aba Gastos]" in text and "14/11 | Mercado | 85.9" in text

    (tmp_path / "pagina.html").write_text(ARTICLE, encoding="utf-8")
    text = extract_file_text(tmp_path / "pagina.html")
    assert text.startswith("Guia de prescrição civil") and "dez anos" in text and "var x" not in text

    (tmp_path / "dados.json").write_text(json.dumps({"curso": "Direito", "semestre": 7}), encoding="utf-8")
    assert '"semestre": 7' in extract_file_text(tmp_path / "dados.json")


def test_links_to_files_and_google_exports(fake_web):
    pytest.importorskip("reportlab")
    import io

    from reportlab.pdfgen import canvas

    from magnolia import feeds, library

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(72, 800, "Edital: prova em 20/12")
    c.save()
    fake_web["https://site.gov.br/edital.pdf"] = ("application/pdf", buffer.getvalue())
    sheet_export = "https://docs.google.com/spreadsheets/d/ABC123/export?format=csv"
    fake_web[sheet_export] = ("text/csv", "Data,Item\n14/11,Mercado")

    item = library.add_link("https://site.gov.br/edital.pdf", "concursos")
    assert item["tipo"] == "pagina" and item["titulo"] == "edital.pdf"
    assert "prova em 20/12" in library.read(item)

    title, text = feeds.fetch_page("https://docs.google.com/spreadsheets/d/ABC123/edit#gid=0")
    assert title == "Google Planilhas" and "14/11,Mercado" in text


def test_gui_adds_several_links_at_once(monkeypatch, fake_web):
    monkeypatch.setattr(accounts, "ITERATIONS", 1000)
    from magnolia.gui.app import Api

    api = Api()
    api.create_account({"usuario": "amanda", "senha": "123456", "nome": "Amanda", "chave": "k"})
    result = api.add_link("g1.globo.com\nhttps://blog.com/artigo-prescricao, site-que-nao-existe.com", "estudos")
    assert result["ok"] and len(result["itens"]) == 2 and len(result["erros"]) == 1
    assert {i["tipo"] for i in result["itens"]} == {"noticias", "pagina"}


# ── Spotify ─────────────────────────────────────────────────────────────────
def test_spotify_reads_window_title():
    from magnolia.tools.spotify import describe_title

    assert describe_title([]).startswith("Não encontrei o aplicativo do Spotify aberto")
    assert describe_title(["Spotify Premium"]) == "O Spotify está aberto, mas pausado."
    playing = describe_title(["GDI+ Window", "Taylor Swift - Cruel Summer"])
    assert playing == "Tocando agora: Cruel Summer (Taylor Swift)."


def test_spotify_controls_and_search(monkeypatch):
    from magnolia.tools import spotify

    pressed = []
    monkeypatch.setattr(spotify, "SYSTEM", "Windows")
    monkeypatch.setattr(spotify, "_press_media_key", lambda action, times=1: pressed.append((action, times)))
    assert run_tool("spotify_proxima_musica", {}) == "Próxima música."
    assert run_tool("spotify_musica_anterior", {}) == "Voltei."
    assert run_tool("volume_do_computador", {"acao": "aumentar", "passos": 3}) == "Volume ajustado."
    assert pressed == [("proxima", 1), ("anterior", 2), ("volume_mais", 3)]

    opened = []
    monkeypatch.setattr(spotify, "_open", lambda uri, web: opened.append(uri) or "app")
    out = run_tool("spotify_buscar", {"busca": "lofi para estudar"})
    assert opened == ["spotify:search:lofi%20para%20estudar"] and "aplicativo do Spotify" in out


def test_spotify_search_uses_web_when_app_is_missing(monkeypatch):
    from magnolia.tools import spotify

    opened = []
    monkeypatch.setattr(spotify, "SYSTEM", "Windows")
    monkeypatch.setattr(spotify, "spotify_app_installed", lambda: False)
    monkeypatch.setattr(spotify.webbrowser, "open", lambda url: opened.append(url))
    out = run_tool("spotify_buscar", {"busca": "Choosing Texas"})
    assert opened == ["https://open.spotify.com/search/Choosing%20Texas"] and "Spotify Web" in out


# ── Spotify Premium (API oficial) ───────────────────────────────────────────
class FakeResponse:
    def __init__(self, status=200, data=None):
        import json as _json

        self.status_code, self._data = status, data
        self.content = _json.dumps(data).encode() if data is not None else b""
        self.ok = status < 400
        self.text = self.content.decode()

    def json(self):
        return self._data


def test_spotify_api_token_refresh_and_errors(monkeypatch):
    import time

    from magnolia import spotify_api

    monkeypatch.setattr(config, "SPOTIFY_CLIENT_ID", "cliente123")
    assert spotify_api.is_connected() is False
    spotify_api._save_token({"access_token": "velho", "refresh_token": "r1", "expires_at": time.time() - 10})
    assert spotify_api.is_connected() is True

    calls = []

    def fake_post(url, data, timeout):
        calls.append(data)
        return FakeResponse(200, {"access_token": "novo", "expires_in": 3600})

    premium_error = FakeResponse(403, {"error": {"reason": "PREMIUM_REQUIRED"}})
    responses = iter([FakeResponse(204), FakeResponse(404), premium_error])
    used_tokens = []

    def fake_request(method, url, headers, timeout, **kwargs):
        used_tokens.append(headers["Authorization"])
        return next(responses)

    monkeypatch.setattr(spotify_api.requests, "post", fake_post)
    monkeypatch.setattr(spotify_api.requests, "request", fake_request)

    assert spotify_api.call("PUT", "/me/player/pause") is None          # 204: deu certo, sem conteúdo
    assert calls[0]["grant_type"] == "refresh_token" and used_tokens[0] == "Bearer novo"
    assert spotify_api._load_token()["refresh_token"] == "r1"           # o refresh antigo é mantido
    with pytest.raises(spotify_api.SpotifyError, match="NO_DEVICE"):
        spotify_api.call("POST", "/me/player/next")
    with pytest.raises(spotify_api.SpotifyError, match="Premium"):
        spotify_api.call("PUT", "/me/player/play")


def test_spotify_plays_when_connected_and_opens_player_if_needed(monkeypatch):
    from magnolia import spotify_api
    from magnolia.tools import spotify

    monkeypatch.setattr(spotify_api, "is_connected", lambda: True)
    track = {"type": "track", "uri": "spotify:track:abc", "name": "Choosing Texas",
             "artists": [{"name": "Ella Langley"}]}
    monkeypatch.setattr(spotify_api, "search", lambda q, kind="musica": track)
    device_lists = iter([[], [], [{"id": "pc", "is_active": False}]])
    monkeypatch.setattr(spotify_api, "devices", lambda: next(device_lists))
    monkeypatch.setattr(spotify_api.time, "sleep", lambda s: None)
    opened, played = [], []
    monkeypatch.setattr(spotify, "_open_spotify_player", lambda: opened.append(True))
    monkeypatch.setattr(spotify_api, "play", lambda item, device: played.append((item["uri"], device)))

    out = run_tool("spotify_tocar", {"musica": "Choosing Texas"})
    assert out == "Tocando Choosing Texas (Ella Langley)."
    assert opened == [True] and played == [("spotify:track:abc", "pc")]   # abriu o Spotify e esperou

    # Sem nenhum Spotify aberto nem depois de esperar: explica o que fazer
    monkeypatch.setattr(spotify_api, "devices", lambda: [])
    assert "Não achei nenhum Spotify aberto" in run_tool("spotify_tocar", {"musica": "x"})


def test_spotify_my_playlists_and_controls_via_api(monkeypatch):
    from magnolia import spotify_api

    monkeypatch.setattr(spotify_api, "is_connected", lambda: True)
    monkeypatch.setattr(spotify_api, "my_playlists", lambda: [
        {"name": "Treino pesado", "uri": "spotify:playlist:1", "type": "playlist"},
        {"name": "Estudos lofi", "uri": "spotify:playlist:2", "type": "playlist"}])
    monkeypatch.setattr(spotify_api, "ensure_device", lambda opener: "pc")
    played, api_calls = [], []
    monkeypatch.setattr(spotify_api, "play", lambda item, device: played.append(item["uri"]))
    monkeypatch.setattr(spotify_api, "call", lambda method, path, **kw: api_calls.append((method, path)))

    assert run_tool("spotify_tocar_minha_playlist", {"nome": "estudo"}) == "Tocando a sua playlist Estudos lofi."
    assert played == ["spotify:playlist:2"]
    assert run_tool("spotify_pausar", {}) == "Pausei."
    assert run_tool("spotify_volume", {"porcentagem": 140}) == "Volume do Spotify em 100%."
    assert api_calls == [("PUT", "/me/player/pause"), ("PUT", "/me/player/volume")]


def test_spotify_connect_needs_client_id(monkeypatch):
    from magnolia import spotify_api

    monkeypatch.setattr(config, "SPOTIFY_CLIENT_ID", "")
    assert "Client ID" in spotify_api.connect()
    assert "conecte o Spotify Premium" in run_tool("spotify_listar_minhas_playlists", {})


# ── Abrir sozinho o que foi criado ──────────────────────────────────────────
class FakeGoogle:
    """Imita os clientes da API do Google: qualquer método devolve ele mesmo; execute() devolve a resposta."""

    def __init__(self, response):
        self.response = response

    def __getattr__(self, name):
        return lambda *a, **k: self

    def execute(self):
        return self.response


def test_google_creations_open_in_browser(monkeypatch):
    import webbrowser

    from magnolia.tools import google_agenda, google_docs_drive, google_gmail, google_planilhas

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(google_docs_drive, "service", lambda *a: FakeGoogle({"documentId": "DOC1"}))
    monkeypatch.setattr(google_planilhas, "service", lambda *a: FakeGoogle(
        {"spreadsheetId": "S1", "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/S1"}))
    monkeypatch.setattr(google_agenda, "service", lambda *a: FakeGoogle(
        {"summary": "Dentista", "start": {"dateTime": "2026-11-20T15:00:00-04:00"},
         "htmlLink": "https://calendar.google.com/event?eid=E1"}))
    monkeypatch.setattr(google_gmail, "service", lambda *a: FakeGoogle({"message": {"id": "M1"}}))

    assert "aberto" in run_tool("documento_criar", {"titulo": "Ideias"})
    assert "aberta" in run_tool("planilha_criar", {"titulo": "Gastos"})
    event = {"titulo": "Dentista", "data": "20/11/2026", "hora": "15:00"}
    assert "aberto" in run_tool("agenda_criar_compromisso", event)
    assert "aberto no Gmail" in run_tool("gmail_criar_rascunho", {"para": "p@x.com", "assunto": "Oi", "texto": "Olá"})
    assert opened == ["https://docs.google.com/document/d/DOC1/edit", "https://docs.google.com/spreadsheets/d/S1",
                      "https://calendar.google.com/event?eid=E1", "https://mail.google.com/mail/u/0/#drafts?compose=M1"]

    monkeypatch.setattr(google_docs_drive, "service", lambda *a: FakeGoogle(
        {"files": [{"name": "Gastos de novembro", "webViewLink": "https://drive/x"}]}))
    assert run_tool("abrir_arquivo_do_google", {"nome": "gastos"}) == "Abri 'Gastos de novembro' no navegador."
    assert run_tool("agenda_abrir", {"data": "20/11/2026"}) == "Abri o Google Agenda em 20/11."
    assert opened[-2:] == ["https://drive/x", "https://calendar.google.com/calendar/r/day/2026/11/20"]


def test_open_url_only_accepts_web_links(monkeypatch):
    import webbrowser

    from magnolia.gui.app import Api

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    api = Api()
    assert api.open_url("https://docs.google.com/document/d/1") is True
    assert api.open_url("file:///C:/Windows/system32") is False
    assert opened == ["https://docs.google.com/document/d/1"]


# ── Timers, cronômetro e alarme ─────────────────────────────────────────────
def test_timer_rings_and_updates_screen(monkeypatch):
    import time

    from magnolia import alerts
    from magnolia.tools import timers

    rings, changes = [], []
    monkeypatch.setattr(alerts, "listener", lambda kind, text: rings.append((kind, text)))
    monkeypatch.setattr(alerts, "on_change", lambda state: changes.append(len(state["timers"])))
    monkeypatch.setattr("magnolia.tools.lembretes.notify", lambda *a: True)

    assert "Preciso saber" in run_tool("criar_timer", {})
    assert run_tool("criar_timer", {"segundos": 1, "nome": "Macarrão"}) == "Timer 'Macarrão' de 1 s iniciado."
    state = timers.state()["timers"][0]
    assert state["nome"] == "Macarrão" and 0 < state["fim"] - time.time() <= 1 and "_thread" not in state
    time.sleep(1.3)
    assert rings == [("timer", "Macarrão terminou!")] and changes == [1, 0]


def test_cancel_timer_alarm_and_stopwatch(monkeypatch):
    import time

    from magnolia import alerts
    from magnolia.tools import timers

    monkeypatch.setattr(alerts, "on_change", None)
    run_tool("criar_timer", {"minutos": 10, "nome": "Estudo"})
    out = run_tool("criar_alarme", {"horario": "06:30", "nome": "Acordar"})
    assert "Alarme 'Acordar' marcado para" in out and "06:30" in out
    assert "Estudo: faltam" in run_tool("ver_timers", {})
    assert run_tool("cancelar_timer", {"qual": "estudo"}) == "'Estudo' cancelado."
    assert run_tool("cancelar_timer", {"qual": "acordar"}) == "'Acordar' cancelado."
    assert timers.state()["timers"] == []

    assert run_tool("iniciar_cronometro", {}) == "Cronômetro iniciado."
    timers._stopwatch["inicio"] -= 75  # finge que passou 1 min e 15 s
    assert run_tool("parar_cronometro", {}) == "Cronômetro parado em 1 min e 15 s."
    assert run_tool("parar_cronometro", {}) == "O cronômetro não está rodando."
    assert time.time() > 0


def test_reminder_rings_with_sound(monkeypatch):
    from magnolia import alerts
    from magnolia.tools import lembretes

    rings = []
    monkeypatch.setattr(alerts, "listener", lambda kind, text: rings.append((kind, text)))
    monkeypatch.setattr(lembretes, "notify", lambda *a: True)
    run_tool("criar_lembrete", {"mensagem": "beber água", "minutos": 1})
    rid = max(lembretes._reminders)
    lembretes._reminders[rid][2].cancel()
    lembretes._reminders[rid][2].function()  # dispara agora, sem esperar 1 minuto
    assert rings == [("lembrete", "beber água")]


def test_gui_timer_controls(monkeypatch):
    monkeypatch.setattr(accounts, "ITERATIONS", 1000)
    from magnolia.gui.app import Api
    from magnolia.tools import timers

    api = Api()
    api.create_account({"usuario": "amanda", "senha": "123456", "nome": "Amanda", "chave": "k"})
    run_tool("criar_timer", {"minutos": 5, "nome": "Chá"})
    assert api.status()["timers"]["timers"][0]["nome"] == "Chá"
    tid = timers.state()["timers"][0]["id"]
    assert api.cancel_timer(tid)["timers"] == []
    run_tool("iniciar_cronometro", {})
    assert api.stop_stopwatch()["cronometro"] is None


# ── "Ei, Magnólia" ──────────────────────────────────────────────────────────
def test_wake_word_grammar_uses_known_words():
    import json

    from magnolia.wakeword import build_grammar

    class FakeModel:
        def __init__(self, vocab):
            self.vocab = vocab

        def vosk_model_find_word(self, word):  # mesmo nome do método do Vosk de verdade
            return 1 if word in self.vocab else -1

    phrases = json.loads(build_grammar(FakeModel({"magnolia", "mangólia"})))
    assert phrases == ["magnolia", "mangólia", "ei magnolia", "ei mangólia", "[unk]"]
    assert build_grammar(FakeModel(set())) is None  # nenhuma conhecida: sem gramática
    assert build_grammar(object()) is None           # modelo sem o método: segue sem gramática


def test_wake_word_grammar_with_real_vosk_class():
    """Confere o nome do método na classe Model do Vosk instalado (sem carregar modelo)."""
    vosk = pytest.importorskip("vosk")
    assert hasattr(vosk.Model, "vosk_model_find_word") or hasattr(vosk.Model, "find_word")


def test_alarm_sound_comes_before_slow_notification(monkeypatch):
    """A notificação do Windows pode demorar; o som (evento da janela) não pode esperar por ela."""
    import time

    from magnolia import alerts

    order = []
    monkeypatch.setattr("magnolia.tools.lembretes.notify", lambda *a: (time.sleep(0.5), order.append("notificação")))
    monkeypatch.setattr(alerts, "listener", lambda kind, text: order.append("som"))
    started = time.monotonic()
    alerts.ring("timer", "Chá terminou!")
    assert time.monotonic() - started < 0.2 and order == ["som"]
    time.sleep(0.7)
    assert order == ["som", "notificação"]


def test_gui_alarm_event_keeps_its_name(monkeypatch):
    """O evento que faz a janela tocar o sino tem que chegar como "alarme"."""
    import time

    monkeypatch.setattr("magnolia.tools.lembretes.notify", lambda *a: True)
    from magnolia.gui.app import Api

    api = Api()
    queue = api.subscribe()
    run_tool("criar_timer", {"segundos": 1, "nome": "Chá"})
    time.sleep(1.4)
    events = []
    while not queue.empty():
        events.append(queue.get())
    assert {"tipo": "alarme", "categoria": "timer", "texto": "Chá terminou!"} in events


# ── Conversa de voz que cai ─────────────────────────────────────────────────
def test_voice_error_is_explained_from_exception_group():
    from magnolia.voice import explain_voice_error, root_errors

    error = ExceptionGroup("unhandled errors in a TaskGroup",
                           [ConnectionError("received 1011 (internal error) Internal error encountered")])
    assert [type(e) for e in root_errors(error)] == [ConnectionError]
    message = explain_voice_error(error)
    assert "TaskGroup" not in message and "problema interno" in message and "1011" in message


def test_voice_reconnects_and_falls_back_to_fast_voice(monkeypatch):
    from magnolia import assistant as assistant_module

    monkeypatch.setattr(config, "VOICE_STYLE", "natural")
    monkeypatch.setattr(assistant_module.time, "sleep", lambda s: None)
    styles_used = []

    class FlakySession:
        def __init__(self, style=None, **kwargs):
            self.style, self.model = style, f"modelo-{style}"
            styles_used.append(style)

        async def run(self):
            if self.style == "natural":  # a voz natural sempre cai
                raise ExceptionGroup("unhandled errors in a TaskGroup", [ConnectionError("1008 policy violation")])

        def stop(self):
            pass

    monkeypatch.setattr(assistant_module, "VoiceSession", FlakySession)
    events = []
    a = assistant_module.Assistant(on_event=lambda name, data: events.append((name, data)))
    a._voice_loop(wake_word=False, headphones=False)

    assert styles_used == ["natural", "rapida"]  # a natural caiu: trocou na hora para a rápida
    assert ("aviso", {"texto": "A voz natural deu problema; mudei para a voz rápida."}) in events
    assert all("TaskGroup" not in d.get("texto", "") for n, d in events if n == "erro")


def test_tool_results_are_shortened_for_speed(monkeypatch):
    from magnolia import tools
    from magnolia.tools import tool

    @tool
    def ferramenta_que_fala_demais() -> str:
        """Devolve um texto enorme (só para o teste)."""
        return "x" * 50_000

    try:
        text_result = ferramenta_que_fala_demais()
        assert len(text_result) < tools.MAX_TEXT_CHARS + 200 and "resultado cortado" in text_result
        voice_result = run_tool("ferramenta_que_fala_demais", {}, tools.MAX_VOICE_CHARS)
        assert len(voice_result) < tools.MAX_VOICE_CHARS + 200
    finally:
        tools._REGISTRY.pop("ferramenta_que_fala_demais", None)


def test_fast_voice_is_the_default(monkeypatch):
    monkeypatch.setattr(accounts, "ITERATIONS", 1000)
    accounts.create_account("nova", "123456", "Nova", "k").activate()
    assert config.VOICE_STYLE == "rapida"


def test_spotify_connect_does_not_restart_voice(monkeypatch):
    monkeypatch.setattr(accounts, "ITERATIONS", 1000)
    from magnolia import spotify_api
    from magnolia.gui.app import Api

    api = Api()
    api.create_account({"usuario": "amanda", "senha": "123456", "nome": "Amanda", "chave": "k"})
    resets = []
    monkeypatch.setattr(api.assistant, "reset", lambda: resets.append(1))
    monkeypatch.setattr(spotify_api, "connect", lambda: "Spotify conectado.")
    assert api.spotify_connect("meu-client-id")["mensagem"] == "Spotify conectado."
    assert resets == [] and config.SPOTIFY_CLIENT_ID == "meu-client-id"
    assert api.account.settings["spotify_client_id"] == "meu-client-id"


def test_friendly_gemini_errors():
    from magnolia.gui.app import friendly_error

    assert "não tem permissão" in friendly_error(Exception("403 Forbidden"))
    assert "não é válida" in friendly_error(Exception("400 API key not valid. API_KEY_INVALID"))
    assert "cota" in friendly_error(Exception("429 RESOURCE_EXHAUSTED"))
