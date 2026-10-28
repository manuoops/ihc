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

O texto do requisito “GEMMA 2.4” não identifica um modelo único: a lista oficial separa Gemma 2 (2B, 9B e 27B), Gemma 3 (inclui 4B) e Gemma 4 (E2B/E4B). Configure LLM_MODEL com o identificador exato retornado por GET /v1/models; o valor de exemplo atual é apenas a configuração herdada do projeto, não uma confirmação do modelo disponível. Consulte a [lista de releases Gemma](https://ai.google.dev/gemma/docs/releases) e a [visão geral Gemma 4](https://ai.google.dev/gemma/docs/core.md).

A transcrição de voz precisa de um endpoint de áudio compatível com a API OpenAI. Se o provedor exigir autenticação, configure VOICE_TRANSCRIPTION_API_KEY; a aplicação envia Bearer somente quando a variável está preenchida. Nenhuma credencial real deve ser adicionada ao repositório.

## Diagnóstico

Rode `.venv/bin/python src/server_services.py --preflight` para conferir RLM/GEPA/Deno, endpoint/modelo LLM e presença das configurações do Telegram e transcrição. O relatório mostra apenas se os segredos estão configurados; não imprime seus valores. A presença da URL STT não confirma que o serviço esteja disponível.

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

O loop RLM, sandbox Deno, validação SQLite e avaliação dinâmica foram exercitados com ações determinísticas. Isso valida o pipeline, mas não mede a qualidade do modelo configurado.

**W.I.P — depende de servidor LLM:** `--evaluate` mede as respostas do RLM e `--optimize` executa GEPA e salva `src/sql_generator_optimized.json`. Ambos exigem o endpoint e o modelo definidos no `.env`; ainda precisam ser executados contra o modelo escolhido.

**W.I.P — integrações externas:** o bot requer token válido do Telegram; voz requer endpoint de transcrição compatível. A identificação “Gemma 2.4” do requisito ainda precisa ser confirmada contra o modelo efetivamente servido.

## Segurança e estrutura

Cada consulta tem limite de 4.000 caracteres, 1 segundo de execução e 500 linhas retornadas.

A lógica da aplicação está em `src/server_services.py` e `src/bot_services.py`. O SQL é rejeitado se não for um único SELECT; a consulta é validada numa base SQLite em memória e executada no banco real em modo somente leitura, com authorizer. A carga de dados de exemplo é idempotente.
