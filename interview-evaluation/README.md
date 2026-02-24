# Interview Evaluator

CLI e interfaccia web per la **simulazione automatica** di interviste di raccolta requisiti, l'**estrazione dei requisiti** dalla conversazione e la **valutazione qualitativa** dei requisiti estratti.

## Obiettivo

L'agente Interviewer del progetto `TECO_LLM_storyteller_web` conduce interviste strutturate con stakeholder umani per raccogliere requisiti software. Questo strumento permette di:

1. **Simulare** l'intervista sostituendo lo stakeholder umano con un LLM collaborativo topic-guided
2. **Estrarre requisiti** dalla conversazione simulata, usando lo stesso prompt di produzione (`requirements_latest`)
3. **Valutare** la qualità dei requisiti estratti in termini di completezza, struttura e copertura

L'obiettivo è verificare l'intero flusso — dall'intervista alla generazione di requisiti — in modo automatizzato e senza bisogno di un utente reale.

## Architettura

```
              ┌──────────────────────┐
              │    Scenario          │  (project_idea + topic)
              └──────────┬───────────┘
                         │
            ┌────────────▼────────────┐
            │    Chat Simulator       │
            │                         │
            │  ┌───────────────────┐  │
            │  │   Interviewer     │──┼──► domanda JSON
            │  │   (LLM + prompt)  │  │   {message, suggestions, is_last_message}
            │  └───────────────────┘  │
            │           ▲  │          │
            │  risposta │  │ domanda  │
            │           │  ▼          │
            │  ┌───────────────────┐  │
            │  │   Stakeholder     │──┼──► risposta testo naturale
            │  │   (topic-guided)  │  │   (sceglie topic, accetta 1ª suggestion)
            │  └───────────────────┘  │
            └────────────┬────────────┘
                         │
              conversations/{id}_conversation.json
              (include chat_history pre-formattato)
                         │
            ┌────────────▼────────────┐
            │  Requirements Extractor │
            │  (LLM + prompt          │
            │   requirements_latest)  │
            └────────────┬────────────┘
                         │
              requirements/{id}_requirements.json
                         │
            ┌────────────▼────────────┐
            │      Evaluator          │
            │  (LLM + prompt:         │
            │   valutazione qualità   │
            │   requisiti estratti)   │
            └────────────┬────────────┘
                         │
              evaluations/{id}_evaluation.json
              (quality_score, topic_coverage,
               category_distribution, issues)
```

### Flusso di simulazione (turno per turno)

1. L'**Interviewer** riceve il system prompt con `project_idea` e la history della conversazione, genera una risposta JSON con `message`, `suggestions` e `is_last_message`
2. Se `is_last_message = true`, l'intervista termina
3. Lo **Stakeholder simulato** (topic-guided) riceve la domanda dell'interviewer e risponde in linguaggio naturale:
   - Al **turno 1**: sceglie il `topic` definito nello scenario
   - Ai **turni successivi**: basa la risposta sulla **prima suggestion** proposta dall'interviewer
4. La risposta viene aggiunta alla history di entrambi gli agenti e si passa al turno successivo

Le due history sono **indipendenti ma intrecciate**: per l'Interviewer le risposte dello stakeholder sono messaggi `user`, per lo Stakeholder le domande dell'interviewer sono messaggi `user`.

### Flusso post-simulazione

1. **Estrazione requisiti**: la conversazione (campo `chat_history` pre-formattato) viene sottomessa al prompt `requirements_latest` — lo stesso usato in produzione dal progetto web — per estrarre un array JSON di requisiti strutturati
2. **Valutazione qualità**: i requisiti estratti vengono valutati dall'Evaluator che produce un report con quality_score, copertura topic, distribuzione categorie e problemi trovati

## Struttura del progetto

```
interview-evaluation/
├── pyproject.toml                     # Build config, entry point CLI + web
├── README.md
├── interview_eval/
│   ├── __init__.py
│   ├── config.py                      # Configurazione Azure OpenAI da .env
│   ├── llm.py                         # Client LLM (single-shot + multi-turn)
│   ├── paths.py                       # Costanti path prompt e output
│   ├── chat_simulator.py              # Orchestratore conversazione multi-turn
│   ├── requirements_extraction.py     # Estrazione requisiti da conversazione
│   ├── evaluation.py                  # Valutazione qualità requisiti estratti
│   ├── comparison.py                  # Generazione HTML confronto A/B valutazioni
│   ├── services.py                    # Service layer condiviso (logica di business)
│   ├── interactive.py                 # CLI entry point (shell interattiva)
│   ├── prompts/
│   │   ├── interviewers/              # Prompt Interviewer versionati
│   │   │   └── interviewer_latest.md  # Prompt Interviewer corrente (da Storyteller)
│   │   ├── stakeholder.md             # Prompt Stakeholder topic-guided
│   │   ├── requirements.md            # Prompt estrazione requisiti (da requirements_latest)
│   │   └── evaluator.md              # Prompt Evaluator (qualità requisiti)
│   └── web/                           # Interfaccia web (FastAPI + Jinja2)
│       ├── app.py                     # FastAPI app factory + entry point
│       ├── dependencies.py            # Config condivisa, DI
│       ├── jobs.py                    # Gestione job background (pipeline/step)
│       ├── routers/
│       │   ├── dashboard.py           # GET /
│       │   ├── pipeline.py            # GET/POST /pipeline
│       │   ├── steps.py               # GET/POST /steps/{type}
│       │   ├── scenarios.py           # CRUD /scenarios
│       │   ├── comparisons.py         # GET/POST /comparisons
│       │   ├── evaluations.py         # GET /evaluations/detail
│       │   └── api.py                 # GET /api/jobs/{id} (JSON polling)
│       ├── templates/                 # Template Jinja2
│       │   ├── base.html
│       │   ├── dashboard.html
│       │   ├── pipeline/
│       │   ├── steps/
│       │   ├── scenarios/
│       │   ├── comparisons/
│       │   └── evaluations/
│       └── static/
│           ├── css/style.css
│           └── js/app.js
├── scenarios/
│   └── example_scenario.json          # Scenario di esempio (e-commerce)
└── output_test/                       # Output generato (gerarchia per confronto A/B)
    └── {prompt_label}/                # Nome del prompt interviewer (es. interviewer_latest)
        └── {model}/                   # Modello LLM (es. gpt-5.2)
            ├── conversations/
            │   └── {scenario_id}/     # Cartella per scenario, file numerati (1, 2, ...)
            ├── requirements/
            │   └── {scenario_id}/
            └── evaluations/
                └── {scenario_id}/
```

## Installazione

### Prerequisiti

- Python >= 3.10
- Accesso ad Azure OpenAI con un deployment configurato

### Setup

```bash
# Dalla root del repository
pip install -e TECO_LLM_cli/interview-evaluation/

# Configura le credenziali Azure OpenAI
# Opzione 1: crea un .env nella directory interview-evaluation/
# Opzione 2: usa --env-file per puntare a un .env esistente
# Opzione 3: imposta la variabile DOTENV_PATH
```

Le dipendenze installate includono `fastapi`, `uvicorn`, `jinja2` e `python-multipart` per l'interfaccia web.

### File `.env`

```env
AZURE_OPENAI_API_KEY=<la-tua-api-key>
AZURE_OPENAI_ENDPOINT=https://<risorsa>.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5.2
```

## Utilizzo

Il progetto offre due modalità di utilizzo: una **CLI interattiva** e un'**interfaccia web**.

### CLI — Shell interattiva

```bash
interview-evaluator
```

#### Menu principale

```
Menu principale:
  1. Nuova pipeline (Simula → Estrai → Valuta)
  2. Stato run
  3. Confronta valutazioni
  4. Step singolo
  5. Impostazioni
  6. Esci
```

| Opzione | Cosa fa |
|---|---|
| **Nuova pipeline** | Seleziona scenario, prompt interviewer e modelli per ogni fase, esegue Simula → Estrai → Valuta in sequenza |
| **Stato run** | Dashboard testuale con conteggi e score per ogni combinazione prompt/modello/scenario |
| **Confronta valutazioni** | Seleziona 2 valutazioni e genera un report HTML di confronto A/B |
| **Step singolo** | Esegue un singolo step (Simula / Estrai / Valuta) su dati esistenti |
| **Impostazioni** | Livello log (verbose/info), pulizia output |

#### Argomenti CLI

```
--scenarios-dir    Directory scenari (default: scenarios/)
--env-file         File .env custom
--deployment       Deployment Azure OpenAI (override del .env)
--temperature      Temperatura LLM (default: 0.7)
--max-tokens       Max token per risposta (default: 4096)
```

Esempio:

```bash
interview-evaluator --env-file ../test-case-evaluation/.env --deployment gpt-5.1
```

### Web — Interfaccia browser

```bash
interview-evaluator-web
```

Oppure:

```bash
python -m interview_eval.web.app
```

Il server si avvia su `http://127.0.0.1:8000/` (default). Aprire l'indirizzo nel browser.

#### Argomenti web server

```
--host             Host di ascolto (default: 127.0.0.1)
--port             Porta (default: 8000)
--env-file         File .env custom
--deployment       Deployment Azure OpenAI (override del .env)
--scenarios-dir    Directory scenari (default: scenarios/)
--output-dir       Directory output (default: ./output_test)
```

Esempio:

```bash
interview-evaluator-web --port 8080 --env-file ../test-case-evaluation/.env
```

#### Pagine disponibili

| Pagina | URL | Descrizione |
|---|---|---|
| **Dashboard** | `/` | Riepilogo di tutte le run per combinazione prompt/modello, con conteggi e score colorati |
| **Pipeline** | `/pipeline` | Form per lanciare una pipeline completa (Simula → Estrai → Valuta) con scelta di scenario, prompt interviewer e modello per ogni fase. Mostra il progresso in tempo reale |
| **Step Singolo** | `/steps/simulate` | Form per eseguire step singoli (Simula, Estrai, Valuta) su dati nuovi o esistenti |
| **Scenari** | `/scenarios` | Gestione CRUD degli scenari (lista, crea, modifica, elimina) |
| **Confronta** | `/comparisons` | Selezione di 2 valutazioni per generare un report HTML di confronto A/B. Lista dei confronti già generati |
| **Dettaglio** | `/evaluations/detail?path=...` | Dettaglio di una singola valutazione con score card, radar chart (qualità), bar chart (maturità), tabella quantità, lineage, punti di forza e debolezze |

#### Funzionamento job in background

Le operazioni LLM (pipeline e step singoli) vengono eseguite in **background** tramite un thread pool (max 2 worker). Dopo l'avvio, il browser mostra una pagina di stato con:
- **Barra di progresso** a 3 step (simulazione, estrazione, valutazione)
- **Log testuale** progressivo
- **Auto-polling** ogni 2 secondi via JavaScript

Al completamento, viene mostrato il link al risultato (valutazione o dettaglio).

## Scenari

Ogni scenario è un file JSON in `scenarios/` con questo formato:

```json
{
  "id": "ecommerce-01",
  "name": "Piattaforma e-commerce artigianale",
  "project_idea": "Descrizione del progetto...",
  "topic": "gestione catalogo prodotti",
  "extracted_reqs": []
}
```

| Campo | Descrizione |
|---|---|
| `id` | Identificativo univoco, usato per i nomi dei file di output |
| `name` | Nome leggibile dello scenario |
| `project_idea` | Descrizione del progetto, iniettata nei prompt Interviewer e Stakeholder |
| `topic` | Argomento che lo stakeholder simulato sceglie al turno 1, usato anche dall'Evaluator |
| `extracted_reqs` | Requisiti pre-esistenti da iniettare. Array vuoto per intervista da zero |

## Output

L'output è organizzato in una gerarchia `{prompt_label}/{model}/` che permette il confronto A/B tra prompt interviewer diversi e/o modelli diversi sullo stesso scenario.

### Gerarchia directory

```
output_test/
├── interviewer_latest/              # Prompt interviewer usato
│   ├── gpt-5.2/                     # Modello LLM
│   │   ├── conversations/
│   │   │   └── ecommerce-01/        # Cartella scenario (per ID)
│   │   │       ├── 1_conversation.json
│   │   │       ├── 2_conversation.json   # Run successive non sovrascrivono
│   │   │       └── ...
│   │   ├── requirements/
│   │   │   └── ecommerce-01/
│   │   │       ├── 1_requirements.json
│   │   │       └── ...
│   │   └── evaluations/
│   │       └── ecommerce-01/
│   │           ├── 1_evaluation.json
│   │           └── ...
│   └── gpt-4.1/                     # Stesso prompt, modello diverso
│       └── ...
└── interviewer_v2/                  # Prompt interviewer alternativo
    └── gpt-5.2/
        └── ...
```

I file di output hanno un **numero incrementale** (`1`, `2`, `3`, ...) per evitare sovrascritture tra run successive dello stesso scenario. Nella pipeline completa, lo stesso numero viene usato per conversazione, requisiti e valutazione per mantenere la tracciabilità.

### Prompt interviewer versionati

I prompt interviewer sono file `.md` nella cartella `prompts/interviewers/`. All'avvio della simulazione o della pipeline, la CLI mostra i prompt disponibili e chiede di selezionarne uno. Il nome del file (senza estensione) diventa il `prompt_label` usato nella gerarchia di output.

Per aggiungere un nuovo prompt interviewer, basta creare un file `.md` in `prompts/interviewers/`.

### Conversazione (`output_test/{prompt}/{model}/conversations/{id}/{N}_conversation.json`)

```json
{
  "scenario_id": "ecommerce-01",
  "scenario_name": "Piattaforma e-commerce artigianale",
  "project_idea": "...",
  "topic": "gestione catalogo prodotti",
  "interviewer_model": "gpt-5.2",
  "stakeholder_model": "gpt-5.2",
  "total_turns": 12,
  "total_tokens": 45230,
  "completed_naturally": true,
  "chat_history": "- sender='agent' text='Ciao! Sono Storyteller...'\n- sender='user' text='Vorrei partire dalla gestione del catalogo...'",
  "turns": [
    {
      "turn_number": 1,
      "interviewer_message": "Ciao! Sono Storyteller...",
      "interviewer_suggestions": ["Gestione catalogo", "Pagamenti", "Spedizioni"],
      "is_last_message": false,
      "stakeholder_response": "Vorrei partire dalla gestione del catalogo...",
      "interviewer_tokens": 1250,
      "stakeholder_tokens": 890
    }
  ]
}
```

Il campo `chat_history` contiene la conversazione pre-formattata nel formato richiesto dal prompt `requirements_latest`, pronta per l'estrazione requisiti.

### Requisiti (`output_test/{prompt}/{model}/requirements/{id}/{N}_requirements.json`)

```json
{
  "scenario_id": "ecommerce-01",
  "source_conversation": "ecommerce-01_conversation.json",
  "extraction_model": "gpt-5.2",
  "extraction_tokens": 8500,
  "requirements": [
    {
      "titolo": "Registrazione artigiani",
      "tipo": "FUNZIONALE",
      "descrizione": "Il sistema deve permettere agli artigiani di...",
      "priorita": "high",
      "fonte": "Chat",
      "criteri_accettazione": ["L'artigiano deve poter..."]
    }
  ]
}
```

Il formato dei requisiti è identico a quello prodotto dal prompt `requirements_latest.txt` in produzione, con un wrapper di metadati (scenario_id, modello, token).

### Valutazione (`output_test/{prompt}/{model}/evaluations/{id}/{N}_evaluation.json`)

```json
{
  "status": "ok",
  "scenario_id": "ecommerce-01",
  "topic": "gestione catalogo prodotti",
  "quantity": {
    "total_requirements": 8,
    "by_category": {"FUNZIONALE": 4, "DATI": 2, "INTERFACCIA": 1, "PERSONAS": 1},
    "distinct_categories": 4,
    "total_acceptance_criteria": 24
  },
  "quality": {
    "per_requirement": [{"titolo": "...", "specificita_titolo": 4, "...": "..."}],
    "avg_specificita_titolo": 3.8,
    "avg_completezza_descrizione": 3.5,
    "avg_qualita_criteri": 4.1,
    "avg_pertinenza_topic": 4.6,
    "quality_score": 4.0
  },
  "maturity": {
    "copertura_topic": {"score": 4, "aspetti_coperti": ["..."], "aspetti_mancanti": ["..."]},
    "prontezza_backlog": {"score": 3, "note": "..."},
    "ambiguita": {"score": 4, "requisiti_ambigui": []},
    "duplicati": {"score": 5, "coppie_duplicate": []},
    "maturity_score": 4.0
  },
  "overall_score": 4.0,
  "strengths": ["..."],
  "weaknesses": ["..."]
}
```

## Metriche di valutazione

L'**overall_score** (1-5) valuta i requisiti su 3 dimensioni con rubrica per-requisito, pensata per il confronto A/B tra interviste sullo stesso topic.

### Quantità (peso 20% nell'overall)

Conteggi puri: requisiti totali, per categoria, categorie distinte, criteri di accettazione. Il fattore quantità vale 5.0 con almeno 15 requisiti, scala linearmente sotto.

### Qualità (peso 50% nell'overall)

Rubrica per-requisito, scala 1-5 su 4 assi:

| Asse | 1 (minimo) | 5 (massimo) |
|---|---|---|
| **Specificità titolo** | Generico, potrebbe descrivere qualsiasi progetto | Univoco, preciso, auto-esplicativo |
| **Completezza descrizione** | Una frase generica | Attori, flussi, edge case, vincoli tecnici |
| **Qualità criteri accettazione** | Assenti | Misurabili, verificabili, pronti per test case |
| **Pertinenza al topic** | Non pertinente | Approfondisce aspetto specifico del topic |

`quality_score` = media dei 4 assi medi.

### Maturità (peso 30% nell'overall)

Valutazione d'insieme, scala 1-5 su 4 dimensioni:

| Dimensione | 1 (minimo) | 5 (massimo) |
|---|---|---|
| **Copertura topic** | Solo l'aspetto più ovvio | Macro, micro, edge case, aspetti non funzionali |
| **Prontezza backlog** | Note informali | Pronti per uno sviluppatore |
| **Chiarezza** | Maggior parte ambigua | Nessuna ambiguità |
| **Unicità** | Molti duplicati | Ogni requisito è unico |

`maturity_score` = media delle 4 dimensioni.

### Formula overall

`overall_score = quality_score × 0.5 + maturity_score × 0.3 + quantity_factor × 0.2`

## Prompt

### Interviewer (`prompts/interviewers/*.md`)

Prompt versionati nella cartella `prompts/interviewers/`. Ogni file `.md` è un prompt interviewer selezionabile dalla CLI. Il prompt di default (`interviewer_latest.md`) è una copia del prompt di produzione dell'agente Storyteller: conduce l'intervista con strategia a piramide invertita (da macro a micro), una domanda alla volta, con format di risposta JSON strutturato. Per testare varianti, aggiungere nuovi file `.md` nella stessa cartella.

### Stakeholder (`prompts/stakeholder.md`)

Stakeholder **topic-guided**: al turno 1 sceglie il `topic` specificato nello scenario, nei turni successivi basa la risposta sulla prima suggestion proposta dall'interviewer. Risponde con competenza di dominio in linguaggio naturale.

### Requirements (`prompts/requirements.md`)

Copia del prompt `requirements_latest.txt` di produzione dal progetto `TECO_LLM_storyteller_web`. Estrae requisiti strutturati (titolo, tipo, descrizione, priorità, fonte, criteri di accettazione) dalla conversazione. I placeholder `{{chat_history}}` e `{{project_idea}}` vengono sostituiti con i dati della conversazione.

### Evaluator (`prompts/evaluator.md`)

Valuta qualità, quantità e maturità dei **requisiti estratti** (non della conversazione). Riceve i requisiti, la `project_idea` e il `topic`, e applica una rubrica per-requisito (scala 1-5) su 4 assi di qualità + 4 dimensioni di maturità. Produce un JSON strutturato con overall_score, quality_score, maturity_score, dettaglio per-requisito, punti di forza e debolezze. Pensato per il confronto A/B tra interviste sullo stesso topic.

## Architettura software

Il progetto segue un'architettura a 3 livelli:

| Livello | File | Responsabilità |
|---|---|---|
| **Service layer** | `services.py` | Logica di business pura (caricamento dati, scansione artefatti, orchestrazione LLM, aggregazione dashboard). Nessuna dipendenza di presentazione |
| **CLI** | `interactive.py` | Shell interattiva che usa `services.py` aggiungendo presentazione console (colori ANSI, menu, input) |
| **Web** | `web/` | Interfaccia browser (FastAPI + Jinja2) che usa `services.py` aggiungendo routing HTTP, template HTML e job background |

CLI e web condividono lo stesso service layer e producono output nella stessa gerarchia `output_test/`. I dati generati da una modalità sono immediatamente visibili dall'altra.

## Relazione con il progetto esistente

| Componente | Riusato da `test-case-evaluation` | Adattamento |
|---|---|---|
| `config.py` | Pattern identico | Path `.env` relativo al progetto |
| `llm.py` | Base identica | Aggiunta `call_azure_openai_chat()` per multi-turn |
| `_extract_json()` | Logica identica | Copiata in `chat_simulator.py`, `requirements_extraction.py` e `evaluation.py` |
| Pattern CLI | `_ask_choice()`, `_ask_text()`, colori ANSI | Adattato al menu interviste |
| `pyproject.toml` | Stesso schema | Entry point e nome diversi |
| `requirements_latest.txt` | Prompt dal progetto web | Copiato in `prompts/requirements.md` |
