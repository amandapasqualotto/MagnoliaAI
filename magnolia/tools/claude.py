"""Pedir ajuda ao Claude (Anthropic) para tarefas mais difíceis.

Opcional: só funciona se a pessoa colocar uma chave da API da Anthropic nas
configurações (console.anthropic.com). Essa chave é paga por uso e é
diferente da assinatura do app do Claude.
"""

from magnolia import config
from magnolia.tools import tool


@tool
def perguntar_ao_claude(pergunta: str, contexto: str = "") -> str:
    """Pede ajuda ao Claude, outra IA, para tarefas que exigem raciocínio longo ou texto caprichado.

    Use quando o usuário pedir explicitamente para perguntar ao Claude, ou para
    redigir textos longos, revisar código, analisar documentos complexos ou
    resolver problemas difíceis. Não use para perguntas simples.

    Args:
        pergunta: o pedido completo, com tudo o que o Claude precisa saber.
        contexto: informações extras, como o texto de um documento (opcional).
    """
    if not config.CLAUDE_API_KEY:
        return ("O Claude não está configurado. Para usar, coloque uma chave da API da Anthropic "
                "(console.anthropic.com) nas configurações da Magnólia.")
    import anthropic

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
    content = f"{contexto}\n\n{pergunta}" if contexto else pergunta
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=2000,
        system=(f"Você está ajudando a {config.ASSISTANT_NAME}, uma assistente de voz, a atender "
                f"{config.USER_NAME or 'o usuário'}. Responda em português do Brasil, de forma direta."),
        messages=[{"role": "user", "content": content}],
    )
    return "".join(block.text for block in response.content if block.type == "text")
