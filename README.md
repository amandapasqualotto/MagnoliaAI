# 🤖 JARVIS: assistente pessoal com Gemini

Um assistente pessoal inspirado no J.A.R.V.I.S. do Homem de Ferro, feito em Python com a API do Google Gemini.
Ele conversa **por texto ou por voz em tempo real**, pesquisa na internet, mostra a previsão do tempo,
cria lembretes com notificação, monitora o computador e **lembra de você** entre uma conversa e outra.

> Projeto de portfólio de **Amanda Maciel Pasqualotto**, estudante de Direito e de Tecnologia da Informação (UFMS).

---

## ✨ O que ele faz

| Habilidade | Exemplos do que dizer |
|---|---|
| 🔎 Pesquisa na web e notícias | "Quais as notícias de tecnologia hoje?" |
| 🌦️ Previsão do tempo | "Vai chover amanhã em São Paulo?" |
| ⏰ Lembretes e notificações | "Me lembra de beber água em 30 minutos" |
| 🧠 Memória de longo prazo | "Lembra que eu prefiro respostas curtas" |
| 💻 Status do computador | "Como está a bateria? O que está pesando na RAM?" |
| 🚀 Abrir programas e sites | "Abre o VS Code", "Abre o GitHub" |
| 🎵 YouTube | "Toca Back in Black no YouTube" |
| 📅 Datas | "Quantos dias faltam para o Natal?" |

## 🧩 Arquitetura

```
main.py                  ← escolhe o modo (texto ou voz)
jarvis/
├── config.py            ← lê o .env (chave, nome, modelos)
├── prompt.py            ← personalidade do Jarvis
├── memory.py            ← memória permanente em JSON
├── brain.py             ← modo texto: Gemini + chamada automática de funções
├── voice.py             ← modo voz: Gemini Live API (áudio em tempo real)
└── tools/               ← habilidades (cada arquivo é descoberto sozinho)
    ├── web.py  clima.py  lembretes.py  memoria.py  sistema.py  tempo.py
```

**Como as ferramentas funcionam:** toda função marcada com `@tool` dentro de `jarvis/tools/` vira uma
habilidade. O Gemini lê o nome, os parâmetros e a docstring da função e decide sozinho quando chamá-la.
Para ensinar algo novo ao Jarvis, basta criar um arquivo:

```python
from jarvis.tools import tool

@tool
def jogar_dado(lados: int = 6) -> str:
    """Joga um dado e devolve o resultado."""
    import random
    return str(random.randint(1, lados))
```

Outras decisões de projeto:
- **Fallback de modelos:** se um modelo estoura a cota ou sai do ar, o Jarvis troca para o próximo sem perder a conversa.
- **Erros não derrubam o assistente:** uma ferramenta que falha devolve o erro ao modelo, que explica o que houve.
- **Antieco no modo voz:** sem fone, o microfone fica mudo enquanto o Jarvis fala, para ele não responder a si mesmo.
- **Testes sem internet:** as APIs externas são substituídas por mocks, então os testes não gastam cota.

## 🚀 Como rodar

Pré-requisito: Python 3.10 ou mais novo.

```bash
git clone https://github.com/SEU-USUARIO/jarvis.git
cd jarvis
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copie `.env.example` para `.env` e cole sua chave gratuita do [Google AI Studio](https://aistudio.google.com/apikey).

```bash
python main.py               # conversa por texto
python main.py --voz         # conversa por voz
python main.py --voz --fone  # voz com fone (dá para interromper o Jarvis)
python -m pytest             # roda os testes
```

## 🗺️ Próximos passos

- [ ] Interface gráfica estilo HUD (reator animado)
- [ ] Palavra de ativação ("Ei, Jarvis")
- [ ] Integração com Google Agenda
- [ ] Lembretes que sobrevivem ao reiniciar
- [ ] Visão: o Jarvis enxerga a tela e a webcam

## 🙏 Créditos

A organização das habilidades foi inspirada no projeto
[MARK LVII de FatihMakes](https://www.youtube.com/@FatihMakes) (CC BY-NC 4.0).
Todo o código deste repositório foi escrito do zero.

## 📄 Licença

MIT
