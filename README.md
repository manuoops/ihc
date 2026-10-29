# IHC — Bot de Estoque Inteligente

Bot Telegram e API FastAPI para consultas Text2SQL no SQLite, com validação de consultas somente leitura.

## Configuração

Use Python 3.10 ou superior. Instale as dependências com `python -m pip install -r requirements.txt`. O RLM padrão do DSPy requer o extra `dspy[deno]` e runtime Deno.

Instale também o runtime Deno conforme a [documentação oficial do DSPy](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/api/modules/RLM.md). Depois, crie `.env` na raiz do projeto com:

```dotenv
TELEGRAM_BOT_TOKEN=seu_token
LLM_MODEL=openai/gemma-4-E2B-it-IQ4_XS
LLM_API_BASE=http://localhost:1337/v1
LLM_API_KEY=not-needed
VOICE_TRANSCRIPTION_URL=http://localhost:1337/v1/audio/transcriptions
VOICE_TRANSCRIPTION_MODEL=whisper-1
VOICE_TRANSCRIPTION_API_KEY=
```

O texto do requisito “GEMMA 2.4” não identifica um modelo único: a lista oficial separa Gemma 2 (2B, 9B e 27B), Gemma 3 (inclui 4B) e Gemma 4 (E2B/E4B). Em 2026-10-29, Jan serviu `gemma-4-E2B-it-IQ4_XS` em `/v1/models`, e esse ID foi confirmado com uma chamada direta. Configure LLM_MODEL com o identificador efetivamente servido. Consulte a [lista de releases Gemma](https://ai.google.dev/gemma/docs/releases) e a [visão geral Gemma 4](https://ai.google.dev/gemma/docs/core.md).

A transcrição de voz precisa de um endpoint de áudio compatível com a API OpenAI. Se o provedor exigir autenticação, configure VOICE_TRANSCRIPTION_API_KEY; a aplicação envia Bearer somente quando a variável está preenchida. Nenhuma credencial real deve ser adicionada ao repositório.

## Diagnóstico

Com o ambiente virtual do projeto ativado, rode `python src/server_services.py --preflight` para conferir RLM/GEPA/Deno, endpoint/modelo LLM e presença das configurações do Telegram e transcrição. O relatório mostra apenas se os segredos estão configurados; não imprime seus valores. A presença da URL STT não confirma que o serviço esteja disponível.

## Execução

Na raiz do projeto:

```bash
uvicorn src.server_services:app --reload
python src/bot_services.py
```

A rota GET aceita pergunta como parâmetro:

```
GET /query?question=Qual%20o%20departamento%20do%20sabonete
```

A API retorna 400 para pergunta inválida, 502 para falha de geração/modelo, 503 quando o gerador não está pronto e 500 para falha do banco.

## Otimização e avaliação

A avaliação offline não precisa do modelo:

```bash
python src/server_services.py --evaluate-safety
```

Ela verifica consultas conhecidas, sintaxe, rejeição de instruções de escrita e integridade dos dados em memória. É uma validação do SQL e do banco; não mede a qualidade do modelo.

Em 2026-10-29, uma pergunta real atravessou Jan, RLM, validação SQLite e a rota HTTP `/query`, retornando o departamento correto do sabonete. Isso confirma um caso ponta a ponta, mas não substitui a avaliação completa de qualidade.

**W.I.P — avaliação e otimização:** `--evaluate` e `--optimize` ainda precisam ser executados com sucesso contra o modelo escolhido. A avaliação completa ficou muito lenta no teste de 2026-10-29; GEPA, artefato otimizado e comparação antes/depois seguem sem evidência.

**W.I.P — integrações externas:** o token Telegram passou por `getMe`, mas não houve teste de conversa nem envio de mensagem. A URL de transcrição está configurada, porém não foi validada com áudio; a lista Jan consultada não continha `whisper-1`, então é necessário configurar um modelo/serviço STT compatível.

## Segurança e estrutura

Cada consulta tem limite de 4.000 caracteres, 1 segundo de execução e 500 linhas retornadas.

A lógica da aplicação está em `src/server_services.py` e `src/bot_services.py`. O SQL é rejeitado se não for um único SELECT; a consulta é validada numa base SQLite em memória e executada no banco real em modo somente leitura, com authorizer. A carga de dados de exemplo é idempotente.
