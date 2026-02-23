# TECO_LLM_cli

## Il problema

I requisiti di business approvati vengono trasformati in user stories prima di generare i test cases. Le user stories, per loro natura, operano a un livello di astrazione **più alto** rispetto ai requisiti formali: sintetizzano, riformulano, interpretano.

Questa trasformazione comporta un rischio concreto: le user stories possono **perdere informazioni** presenti nel requisito originale (omissione di vincoli, semplificazione di criteri di accettazione) oppure **aggiungerne** di non previste (inferenze del modello, edge cases inventati, attori non menzionati). In entrambi i casi, i test cases generati a valle delle user stories rischiano di **allontanarsi dal requisito formalmente approvato** — producendo una copertura di test che non riflette fedelmente ciò che il business ha validato.

Il problema si amplifica quando la trasformazione è assistita da un LLM: il modello riscrive, arricchisce e interpreta con una libertà che può migliorare la qualità degli artefatti ma che introduce anche uno scostamento difficile da misurare senza strumenti dedicati.

## Obiettivo dello strumento

TECO_LLM_cli è una CLI Python che permette di **misurare empiricamente lo scostamento** che il passaggio intermedio attraverso le user stories introduce rispetto al requisito originale.

Per farlo, la pipeline genera test cases seguendo **due percorsi paralleli** a partire dallo stesso requisito:

```
Percorso indiretto (via user stories):
  Requisito → LLM → User Stories → LLM → Test Cases (indiretti)

Percorso diretto:
  Requisito → LLM → Test Cases (diretti)
```

I due set di test cases vengono poi confrontati tramite un **prompt di valutazione** che analizza:

- **Copertura degli acceptance criteria**: tutti gli AC del requisito originale sono coperti in entrambi i percorsi?
- **Informazioni aggiunte**: quali test cases coprono aspetti non presenti nel requisito?
- **Informazioni perse**: quali aspetti del requisito non sono coperti dai test cases?
- **Ridondanze**: ci sono test cases duplicati o sovrapposti tra i due set?

Il risultato è un report (JSON + HTML) che rende visibile e quantificabile la distanza tra i test cases e il requisito approvato, in entrambe le casistiche.

## Quando il passaggio per le user stories aggiunge valore e quando no

Lo strumento nasce dalla constatazione che non tutti i requisiti beneficiano allo stesso modo della trasformazione in user stories:

- **Requisiti funzionali** con attori chiari e azioni concrete: la user story aggiunge struttura (persona, obiettivo, beneficio) e facilita la decomposizione
- **Requisiti non funzionali, vincoli, dati, integrazione**: non hanno un attore naturale. Forzarli nel formato "Come... Voglio... In modo che..." produce artefatti artificiali
- **Requisiti già strutturati** con acceptance criteria verificabili: la user story riformula le stesse informazioni in un formato diverso, senza aggiungere conoscenza

TECO_LLM_cli permette di verificare queste ipotesi sui propri dati, confrontando i risultati dei due percorsi per ogni categoria di requisito.

## Comandi disponibili

| Comando | Descrizione |
|---------|-------------|
| `teco-cli` | Invio singolo di file + prompt ad Azure OpenAI |
| `teco-pipeline` | Pipeline completa: requisiti → user stories → test cases (entrambi i percorsi) |
| `teco-interactive` | Shell interattiva con menu per generazione, valutazione e configurazione |

## Pipeline di elaborazione

La pipeline elabora ogni requisito individualmente (ADR-002) in quattro step:

1. **Validazione sintattica** — Verifica che il requisito abbia i campi obbligatori (code, description, title, acceptance_criteria). Se mancano, il requisito viene skippato.

2. **Step 1 — Requisito → User Stories** — Il requisito viene inviato al LLM con un prompt di sistema che istruisce il modello a generare user stories Agile. Il modello può rifiutare requisiti immaturi (AC assenti, descrizione vaga, contraddizioni). La decomposizione segue la regola di ADR-001: una user story per ogni acceptance criterion.

3. **Step 2 — User Stories → Test Cases (indiretti)** — Le user stories generate vengono inviate al LLM per produrre test cases funzionali completi.

4. **Step 3 — Requisito → Test Cases (diretti)** — Lo stesso requisito originale viene inviato al LLM per generare test cases direttamente, senza passare per le user stories.

5. **Step 4 — Valutazione coerenza** — I test cases indiretti e diretti vengono confrontati dal LLM rispetto al requisito originale. Il risultato è un report di valutazione con metriche di copertura e scostamento.

## Prompt di sistema

I prompt sono organizzati in `teco_cli/prompts/` con struttura gerarchica per fase:

| File | Funzione |
|------|----------|
| `user_stories/ac_based.md` | Requisito → User stories (decomposizione per acceptance criterion) |
| `user_stories/persona_based.md` | Requisito → User stories (decomposizione alternativa per persona) |
| `test_cases/from_user_stories.md` | User stories → Test cases (percorso indiretto) |
| `test_cases/from_requirements.md` | Requisito → Test cases (percorso diretto) |
| `evaluation/coherence.md` | Valutazione coerenza tra test cases indiretti e diretti |
| `*/strict_check/` | Varianti dei prompt con validazione più rigorosa |

## Catena di tracciabilità

Ogni artefatto è collegato al precedente tramite identificativi gerarchici (ADR-003):

```
REQ-F-001                  → requisito originale
REQ-F-001.US01             → user story 1 (da AC 1)
REQ-F-001.US01.TC01        → test case 1 della user story 1 (indiretto)
REQ-F-001.TC01             → test case 1 diretto (senza user stories)
```

## Struttura output

```
output/
├── percorso_indiretto/
│   ├── ac_based/
│   │   ├── user_stories/          User stories AC-based (step 1)
│   │   └── test_cases/            Test cases da US AC-based (step 2, indiretti)
│   └── persona_based/
│       ├── user_stories/          User stories persona-based (step 1)
│       └── test_cases/            Test cases da US persona-based (step 2, indiretti)
├── percorso_diretto/
│   └── test_cases/                Test cases da requisiti (step 3, diretti)
├── valutazioni/                   Report di valutazione coerenza (step 4)
│   └── REQ-F-001/
│       ├── evaluation.json
│       └── evaluation_report.html
├── rejected_requirements.json
├── skipped_syntax.json
└── errors.json
```

## Stack tecnologico

| Componente | Tecnologia |
|------------|------------|
| Linguaggio | Python 3.10+ |
| LLM | Azure OpenAI (gpt-4.1 default) |
| Dipendenze | openai >= 1.30.0, python-dotenv >= 1.0.0 |

## Configurazione

Creare un file `.env` con le credenziali Azure OpenAI:

```env
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://....openai.azure.com
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1
```

Il file `.env` viene cercato in questo ordine:
1. Parametro CLI `--env-file`
2. Variabile d'ambiente `DOTENV_PATH`
3. File `.env` nella directory del progetto

## Installazione

```bash
pip install -e .
```

Questo registra i tre comandi: `teco-cli`, `teco-pipeline`, `teco-interactive`.

## Decisioni architetturali

Le ADR sono documentate in `docs/adr/`:

| ADR | Decisione |
|-----|-----------|
| ADR-001 | Decomposizione user stories per acceptance criterion (1 US per AC) |
| ADR-002 | Elaborazione singola dei requisiti (1 requisito per chiamata LLM) |
| ADR-003 | Convenzione identificativi con notazione a punto gerarchica |
| ADR-004 | Analisi side effects dell'approccio persona-based alternativo |
