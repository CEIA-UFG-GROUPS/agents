# Planejador de Viagens Corporativas — Demo Multi-Agente

Sistema multi-agente que transforma um pedido em linguagem natural
("preciso ir a Goiânia entre 08 e 13 de junho para workshops") num plano de
viagem completo: voo, hotel, orçamento, checagem de política, aprovação humana
e relatório final.

Foi construído como material didático: cada conceito de sistemas multi-agente
tem um lugar visível e isolado no código — orquestração, planejamento, memória,
tool calling, ranking, human-in-the-loop.

---

## Começando

Requisitos: Python 3.12 e [uv](https://docs.astral.sh/uv/).

```bash
uv sync                      # instala as dependências
cp .env.example .env         # configure suas chaves
```

O `.env` controla se o sistema usa LLM:

```bash
LLM_ENABLED=false            # modo offline: nenhuma chave necessária
# ou
LLM_ENABLED=true
GEMINI_API_KEY=sua_chave_aqui
```

Com `LLM_ENABLED=false` tudo roda offline, com parsers determinísticos e
provedores simulados — útil para testes e para rodar sem custo. Com
`LLM_ENABLED=true` o Gemini interpreta os pedidos e resolve aeroportos.

### Rodando

```bash
uv run uvicorn app.main:app --reload      # API em http://127.0.0.1:8000
uv run streamlit run ui/streamlit_app.py  # UI de chat (com a API no ar)
uv run pytest                             # testes (sempre offline)
```

Swagger UI: <http://127.0.0.1:8000/docs>

Há também um modo de desenvolvimento que executa o pipeline inteiro no
startup, sem precisar de requisição — útil para ver tudo funcionando de uma vez:

```bash
DEV_MODE=true uv run uvicorn app.main:app
```

---

## Como funciona

Uma requisição HTTP cria um `TripRun`. O **Orchestrator** é uma máquina de
estados que empurra esse run por fases; cada fase chama **um agente**, que pode
chamar **ferramentas**. O estado vive todo dentro do `TripRun`.

```
  HTTP ──►  FastAPI  ──►  Orchestrator  ──►  Agente da fase  ──►  Ferramentas
                              │                                   (voos, hotéis,
                              └── grava o resultado no TripRun      orçamento,
                                  e avança para a próxima fase      política...)
```

### As fases

```
CREATED → UNDERSTANDING → PLANNING → RETRIEVING_MEMORY → RESOLVING_LOCATIONS
   → SEARCHING_FLIGHTS → SEARCHING_HOTELS → RANKING_FLIGHTS → RANKING_HOTELS
   → RECOMMENDING → ESTIMATING_BUDGET → VALIDATING_POLICY
   → AWAITING_APPROVAL ─┬─(aprovado)─► GENERATING_REPORT → COMPLETED
                        └─(rejeitado)─► REJECTED
```

O run **para sozinho** em três situações: falta informação
(`clarification_required`), a política bloqueou a viagem (`policy_block`), ou
chegou no portão de aprovação humana (`awaiting_approval`).

### Os agentes

Cada agente tem uma responsabilidade só (`app/agents/`):

| Agente | Papel |
|---|---|
| `IntentUnderstandingAgent` | Texto livre → `TripIntent` estruturado (Gemini, com fallback determinístico) |
| `TravelPlannerAgent` | Monta o plano ordenado de passos |
| `MemoryAgent` | Lê preferências do viajante e completa a origem quando não foi dita |
| `LocationUnderstandingAgent` | Resolve aeroportos e decide se precisa perguntar algo |
| `ClarificationAgent` | Formula a pergunta quando falta informação |
| `FlightSearchAgent` / `HotelSearchAgent` | Chamam as ferramentas de busca |
| `FlightRankingAgent` / `HotelRankingAgent` | Pontuam e ordenam as opções |
| `TravelRecommendationAgent` | Escolhe o par voo + hotel |
| `BudgetAgent` | Soma voo + hotel + diárias + contingência |
| `PolicyAgent` | Aplica as regras de política corporativa |
| `DocumentAgent` / `ExecutiveReportAgent` | Geram o relatório final |

### As ferramentas

Registradas em `app/tools/registry.py` e inspecionáveis em `GET /tools`. Todas
são **simuladas** — devolvem dados plausíveis sem chamar APIs externas pagas:

`google_flights_tool` · `skyscanner_tool` · `hotel_search_tool` ·
`budget_calculator_tool` · `policy_tool` · `memory_tool` ·
`document_generator_tool`

O padrão de provedor (`app/tools/providers/`) separa a ferramenta de sua
implementação: trocar o provedor simulado por uma API real não deveria exigir
mudança em nenhum agente.

---

## API

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/trips` | Cria um run a partir do texto do pedido |
| `POST` | `/trips/{id}/run` | Avança automaticamente até uma parada |
| `POST` | `/trips/{id}/advance` | Avança **uma** fase (modo didático) |
| `POST` | `/trips/{id}/clarify` | Responde a uma pergunta do sistema |
| `POST` | `/trips/{id}/approve` · `/reject` | Decisão humana |
| `GET` | `/trips` · `/trips/{id}` · `/trips/{id}/report` | Consulta |
| `GET` | `/memory` · `/tools` · `/tools/llm-status` | Inspeção |
| `POST` | `/tools/resolve-location` | Testa o resolvedor de aeroportos isoladamente |

---

## Estrutura

```
app/
  main.py            entrypoint FastAPI
  orchestrator/      máquina de estados + orquestração
  agents/            um arquivo por agente
  tools/             ferramentas + providers/ (simulados e reais)
  schemas/           modelos Pydantic (o contrato entre tudo)
  repositories/      persistência (hoje: em memória)
  llm/               cliente Gemini + prompts
  core/              configuração e parâmetros de negócio
ui/streamlit_app.py  UI de chat sobre a API
tests/               71 testes, todos offline
```

---

## E agora, a parte que interessa

O que você acabou de ler é um esqueleto que **funciona** — o caminho feliz vai
do texto ao relatório aprovado sem intervenção. Mas "funciona" e "está pronto"
são coisas bem diferentes, e a distância entre as duas é exatamente o exercício
de vocês.

Não vou entregar uma lista de tarefas. Vou entregar perguntas incômodas:

**Ele esquece tudo.** Reinicie o servidor e cada viagem planejada desaparece —
os repositórios são dicionários em memória. Há um `database_url` apontando para
um SQLite que nunca foi conectado. Quanto do sistema precisa mudar para que o
estado sobreviva? E se dois usuários planejarem viagens ao mesmo tempo?

**Ele trava e não avisa direito.** Quando a política bloqueia uma viagem, o run
para numa fase que não é terminal — e o chat passa a responder "já existe uma
viagem em andamento" para sempre, sem saída. Quantos outros becos sem saída
como esse existem? Como você *descobriria* isso sem alguém te contar?

**Ele fica burro quando a rede falha.** Se o Gemini der timeout no meio de uma
chamada, o sistema cai silenciosamente num parser de expressões regulares muito
mais fraco, e o usuário só percebe pelo resultado ruim. Degradar é certo —
degradar em silêncio é aceitável? O que você faria diferente: retry, aviso ao
usuário, as duas coisas?

**Ele só conversa até o plano ficar pronto.** Depois disso, "quero um voo mais
barato" ou "tem outro hotel?" recebem a mesma mensagem fixa. O chat entende
criar viagem e responder pergunta — mais nada. O que muda na arquitetura para
suportar uma conversa que continua sobre um plano existente?

**Existe um agente inteiro que ninguém chama.** `ConversationalPlanningAgent`
tem 189 linhas, controla pendências por turno e é referenciado apenas pelo seu
próprio arquivo de teste. Ele deveria estar ligado? Ou deveria ser apagado? Ter
uma opinião fundamentada sobre isso vale mais do que implementar qualquer uma
das duas.

**Os testes passam em 0,06 segundo.** São 71, todos com mock, todos verdes — e
mesmo assim três bugs reais sobreviveram a eles até alguém rodar o sistema de
verdade. Um teste que nunca falha não está te protegendo de nada. O que
faltava: teste de integração? Contrato? Rodar o fluxo real em CI?

**E a pergunta mais desconfortável:** as ferramentas são todas simuladas. O dia
em que uma delas virar uma API real — com latência, erro 429, resposta
malformada e cobrança por chamada — o que quebra primeiro?

Escolham as perguntas que acharem mais interessantes. As respostas de vocês
serão mais valiosas que este código.
