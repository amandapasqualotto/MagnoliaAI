# Política de Privacidade da Magnólia

*Última atualização: 13 de novembro de 2026*

A Magnólia é uma assistente pessoal de código aberto que roda **no seu próprio computador**. Este
documento explica quais dados ela usa, para quê e onde eles ficam.

## 1. Quem controla os seus dados

Você. A Magnólia não tem servidor próprio: não existe um "banco de dados da Magnólia" na internet.
A desenvolvedora não recebe, não vê e não tem acesso a nenhum dado de quem usa o aplicativo.

## 2. O que fica guardado no seu computador

Na pasta `data/usuarios/<sua conta>/`, somente no seu computador:

- **Conta local:** nome, usuário e um *hash* da senha (a senha em si nunca é guardada).
- **Chave da API do Gemini e acesso ao Google:** criptografados com uma chave derivada da sua senha.
- **Memória:** fatos que você pediu para a Magnólia lembrar.
- **Biblioteca:** textos dos arquivos e páginas que você adicionou (criptografados) e a lista de sites e comandos.
- **Configurações:** voz, cidade e preferências.

Você pode apagar tudo a qualquer momento excluindo a pasta `data`.

## 3. Dados da sua conta Google

Se você escolher conectar sua conta Google, a Magnólia pede acesso a:

| Serviço | Para quê |
|---|---|
| Google Agenda | ver e criar compromissos quando você pede |
| Google Planilhas | criar, ler e adicionar linhas em planilhas quando você pede |
| Google Docs | criar, ler e escrever em documentos quando você pede |
| Google Drive (somente leitura) | procurar arquivos pelo nome quando você pede |
| Gmail (leitura e rascunhos) | ler e-mails e criar **rascunhos**; a Magnólia **nunca envia** e-mails |

Esses dados são acessados **apenas para atender a um pedido seu, no momento do pedido**. Eles não são
guardados pela Magnólia, a não ser que você peça explicitamente para adicionar um documento à Biblioteca.
Eles não são vendidos, não são compartilhados com terceiros e não são usados para publicidade.

O uso e a transferência de informações recebidas das APIs do Google seguem a
[Política de Dados do Usuário dos Serviços de API do Google](https://developers.google.com/terms/api-services-user-data-policy),
incluindo os requisitos de Uso Limitado.

Você pode revogar o acesso a qualquer momento em **Configurações → Desconectar** na Magnólia, ou em
[myaccount.google.com/permissions](https://myaccount.google.com/permissions).

## 4. Inteligência artificial (Google Gemini)

Para entender e responder, a Magnólia envia à API do Google Gemini, usando a **sua própria chave**:
o que você digita ou fala, o resultado das ferramentas necessárias para responder (por exemplo, seus
compromissos, quando você pergunta da agenda) e, no modo voz, o áudio do microfone durante a conversa.

O tratamento desses dados pelo Google segue os
[Termos Adicionais da API do Gemini](https://ai.google.dev/gemini-api/terms). Consulte esses termos
para saber como o Google usa os dados, que pode variar entre o nível gratuito e o pago.

## 5. Microfone e palavra de ativação

Enquanto espera ouvir "Ei, Magnólia", o reconhecimento de voz roda **offline** no seu computador
(Vosk) e nenhum áudio é enviado para a internet. O áudio só vai para o Gemini depois que você chama a
Magnólia ou liga a voz manualmente.

## 6. Outros serviços consultados

- **Previsão do tempo:** Open-Meteo (envia apenas o nome da cidade).
- **Pesquisa na web e notícias:** DuckDuckGo e os sites que você adicionou à Biblioteca.
- **Favoritos do navegador:** lidos apenas no arquivo local do Chrome/Edge/Brave, sem envio para a internet.

## 7. Contato

Dúvidas ou pedidos sobre privacidade: abra uma *issue* no repositório da Magnólia no GitHub.
