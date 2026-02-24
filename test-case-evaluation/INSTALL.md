# Guida di installazione — test-evaluator

Questa guida è pensata per essere seguita da un agente AI o da uno sviluppatore su un desktop che non ha l'ambiente configurato. L'obiettivo è arrivare a lanciare `test-evaluator`.

---

## Prerequisiti

### 1. Python 3.12+

```bash
# Verifica se Python è installato
python --version

# Se non installato, scarica da https://www.python.org/downloads/
# Durante l'installazione seleziona "Add Python to PATH"
```

### 2. Git (opzionale, per clonare il repo)

```bash
git --version

# Se non installato, scarica da https://git-scm.com/downloads
```

### 3. Credenziali Azure OpenAI

Servono le seguenti informazioni:

- `AZURE_OPENAI_API_KEY` — chiave API
- `AZURE_OPENAI_ENDPOINT` — endpoint Azure OpenAI (es. `https://<nome>.openai.azure.com`)
- `AZURE_OPENAI_API_VERSION` — versione API (default: `2024-12-01-preview`)
- `AZURE_OPENAI_DEPLOYMENT_NAME` — nome del deployment (es. `gpt-5.2`)

---

## Installazione

```bash
cd TECO_LLM_cli/test-case-evaluation

# Crea virtual environment
python -m venv .venv

# Attiva il virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (cmd):
.venv\Scripts\activate.bat
# Linux/macOS:
source .venv/bin/activate

# Installa il pacchetto in modalità sviluppo
pip install -e .
```

---

## Configurazione

La CLI cerca il file `.env` in questo ordine:

1. Parametro esplicito `--env-file <path>`
2. Variabile d'ambiente `DOTENV_PATH`
3. File `.env` nella directory `test-case-evaluation/`

Creare un file `.env` in `test-case-evaluation/`:

```env
AZURE_OPENAI_API_KEY=<la-tua-chiave>
AZURE_OPENAI_ENDPOINT=<il-tuo-endpoint>
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5.2
```

---

## Verifica installazione

```bash
test-evaluator --help
```

Output atteso:

```
usage: test-evaluator [-h] [--requirements REQUIREMENTS]
                      [--prompts-dir PROMPTS_DIR] [--env-file ENV_FILE]
                      [--deployment DEPLOYMENT] [--temperature TEMPERATURE]
                      [--max-tokens MAX_TOKENS]
```

---

## Avvio

```bash
# Con .env nella directory test-case-evaluation/
test-evaluator

# Con .env esplicito
test-evaluator --env-file .env

# Con deployment specifico
test-evaluator --env-file .env --deployment gpt-5-mini
```

La shell interattiva mostra un menu con le seguenti opzioni:

- **Genera** — User Stories, Test Cases indiretti (da US), Test Cases diretti (da requisiti), oppure la pipeline completa
- **Valuta** — Coerenza tra test cases diretti e indiretti
- **Impostazioni** — Cambia modello, pulisci output

---

## Risoluzione problemi

### `AZURE_OPENAI_API_KEY non configurata`

Il file `.env` non è stato trovato o non contiene la chiave. Verifica:
- che il file `.env` esista nel path atteso
- che la variabile `AZURE_OPENAI_API_KEY` sia valorizzata (non vuota)
- in alternativa, passa il path esplicito con `--env-file`

### `uv: command not found`

La CLI **non** richiede `uv`. Usa `pip install -e .` come indicato sopra.

### Modulo non trovato (`ModuleNotFoundError`)

Assicurati di aver attivato il virtual environment e di aver eseguito `pip install -e .` dalla directory `TECO_LLM_cli/test-case-evaluation`.

### File requirements.json non trovato

Per default `test-evaluator` cerca `input_test/requirements.json` nella directory corrente. Puoi specificare un path diverso:

```bash
test-evaluator --env-file .env --requirements /path/to/requirements.json
```
