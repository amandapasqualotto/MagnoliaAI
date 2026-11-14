"""O "cérebro" da Magnólia no modo texto: conversa com o Gemini e usa as ferramentas.

O SDK do Google faz a parte difícil sozinho (Automatic Function Calling):
passamos as funções Python, o Gemini decide qual chamar, o SDK executa a
função e devolve o resultado para o modelo, que então responde em português.
"""

from google import genai
from google.genai import errors, types

from magnolia import config
from magnolia.models import make_client, pick_text_models
from magnolia.prompt import build_system_prompt
from magnolia.tools import load_tools

# Erros que valem tentar com o próximo modelo da lista:
# 404 = modelo não existe mais, 429 = cota estourada, 5xx = fora do ar
RETRYABLE = {404, 429, 500, 503, 504}
TIMEOUT_SECONDS = 45   # se o Gemini não responder nesse tempo, tenta o próximo modelo
MAX_ATTEMPTS = 4       # quantos modelos tentar antes de desistir


def log(message: str) -> None:
    """Mensagens na tela preta (terminal), para entender o que está acontecendo."""
    print(f"[Magnólia] {message}", flush=True)


def _is_timeout(error: Exception) -> bool:
    name = type(error).__name__.lower()
    return "timeout" in name or "timed out" in str(error).lower()


class Brain:
    def __init__(self, client: genai.Client | None = None):
        if client is None:
            if not config.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY não configurada. Copie .env.example para .env e preencha.")
            client = make_client(timeout_seconds=TIMEOUT_SECONDS)
        self.client = client
        self.tools = load_tools()
        self.models = pick_text_models(client)  # modelos que a sua chave pode usar
        log(f"modelos disponíveis, em ordem: {', '.join(self.models[:5])}")
        self.model_index = 0
        self.chat = self._new_chat()

    @property
    def model(self) -> str:
        return self.models[self.model_index]

    def _new_chat(self, history=None):
        return self.client.chats.create(
            model=self.model,
            history=history or [],
            config=types.GenerateContentConfig(
                system_instruction=build_system_prompt(),
                tools=self.tools,
            ),
        )

    def ask(self, message: str) -> str:
        """Envia uma mensagem e devolve a resposta da Magnólia."""
        attempts = 0
        while True:
            attempts += 1
            log(f"perguntando ao {self.model}...")
            try:
                response = self.chat.send_message(message)
                log("respondeu.")
                return response.text or "(sem resposta)"
            except Exception as e:  # noqa: BLE001
                retry = (isinstance(e, errors.APIError) and e.code in RETRYABLE) or _is_timeout(e)
                log(f"erro no {self.model}: {str(e)[:200]}")
                if not retry or attempts >= MAX_ATTEMPTS or self.model_index + 1 >= len(self.models):
                    raise
                # Troca de modelo mantendo o histórico da conversa
                self.model_index += 1
                self.chat = self._new_chat(self.chat.get_history())
