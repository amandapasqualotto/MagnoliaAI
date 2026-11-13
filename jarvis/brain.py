"""O "cérebro" do Jarvis no modo texto: conversa com o Gemini e usa as ferramentas.

O SDK do Google faz a parte difícil sozinho (Automatic Function Calling):
passamos as funções Python, o Gemini decide qual chamar, o SDK executa a
função e devolve o resultado para o modelo, que então responde em português.
"""

from google import genai
from google.genai import errors, types

from jarvis import config
from jarvis.prompt import build_system_prompt
from jarvis.tools import load_tools

# Erros que valem tentar com o próximo modelo da lista:
# 404 = modelo não existe mais, 429 = cota estourada, 5xx = fora do ar
RETRYABLE = {404, 429, 500, 503, 504}


class Brain:
    def __init__(self, client: genai.Client | None = None):
        if client is None:
            if not config.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY não configurada. Copie .env.example para .env e preencha.")
            client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.client = client
        self.tools = load_tools()
        self.model_index = 0
        self.chat = self._new_chat()

    @property
    def model(self) -> str:
        return config.TEXT_MODELS[self.model_index]

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
        """Envia uma mensagem e devolve a resposta do Jarvis."""
        while True:
            try:
                response = self.chat.send_message(message)
                return response.text or "(sem resposta)"
            except errors.APIError as e:
                if e.code not in RETRYABLE or self.model_index + 1 >= len(config.TEXT_MODELS):
                    raise
                # Troca de modelo mantendo o histórico da conversa
                self.model_index += 1
                self.chat = self._new_chat(self.chat.get_history())
