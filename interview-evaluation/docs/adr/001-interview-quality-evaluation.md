# ADR-001: Valutazione della qualita dell'intervista

- **Data**: 2026-02-24
- **Stato**: Proposta
- **Autori**: Team TECO LLM

## Contesto

Il sistema attuale valuta solo l'**output** della pipeline (i requisiti estratti) tramite il prompt `evaluator.md`, che produce un `overall_score` composto da quality, maturity e quantity. Questa valutazione risponde alla domanda: *"I requisiti prodotti sono buoni?"*

Manca una valutazione del **processo**: la conversazione stessa tra interviewer e stakeholder. Due interviste possono produrre requisiti con lo stesso score ma con dinamiche radicalmente diverse — una con domande precise e progressione logica, l'altra con domande ridondanti e salti tematici. L'evaluator attuale non distingue i due casi.

Questo e rilevante perche il prompt dell'interviewer e il componente che si intende ottimizzare iterativamente. Senza una metrica sul processo, l'unico segnale di feedback e indiretto (qualita dei requisiti) e non permette di diagnosticare *cosa* l'interviewer fa bene o male.

## Decisione

Introdurre un nuovo step di valutazione — **Interview Quality Evaluation** — che analizza la conversazione (`*_conversation.json`) e produce un report strutturato sulla qualita del processo di intervista.

La valutazione si concentra esclusivamente sul comportamento dell'interviewer, dato che lo stakeholder simulato ha un comportamento fisso e deterministico (topic-guided, sceglie la prima suggestion).

## Rubrica proposta

### Dimensione 1: Efficienza conversazionale

Misura il rapporto tra turni che raccolgono informazioni utili e turni totali.

| Score | Criterio |
|-------|----------|
| 1 | Meno del 30% dei turni raccoglie informazioni nuove; conversazione dominata da preamboli, ripetizioni o meta-comunicazione |
| 2 | 30-50% di turni sostanziali; setup lungo o chiusura ridondante |
| 3 | 50-65% di turni sostanziali; qualche turno sprecato ma flusso accettabile |
| 4 | 65-80% di turni sostanziali; setup e chiusura snelli |
| 5 | Oltre 80% di turni sostanziali; ogni turno aggiunge informazione |

**Calcolo**: classificare ogni turno come `setup` (scelta topic, presentazione), `sostanziale` (domanda che raccoglie requisiti), `follow-up` (chiarimento su risposta precedente — conta come sostanziale), `chiusura` (conferma, checklist, salvataggio). Score = f(sostanziali / totali).

**Automazione**: parzialmente automatizzabile via pattern matching (turni senza domande, turni con checklist, turni con "Confermi che non hai altro"), completamente automatizzabile via LLM.

### Dimensione 2: Progressione tematica

Misura la coerenza logica della sequenza di domande, dalla visione macro ai dettagli micro (piramide invertita).

| Score | Criterio |
|-------|----------|
| 1 | Domande in ordine casuale, salti frequenti tra sotto-temi senza completare nessuno |
| 2 | Qualche sequenza logica ma frequenti interruzioni e ritorni |
| 3 | Progressione riconoscibile ma con 2-3 salti tematici immotivati |
| 4 | Progressione chiara macro → micro con al piu 1 salto giustificato |
| 5 | Progressione perfetta: ogni domanda approfondisce naturalmente la precedente o apre il sotto-tema logicamente successivo |

**Cosa valutare**: estrarre la sequenza dei sotto-temi trattati turno per turno e verificare che formino un percorso coerente. Penalizzare ritorni a sotto-temi gia chiusi e salti tra argomenti non correlati.

### Dimensione 3: Copertura degli aspetti

Misura quanti sotto-temi distinti dell'argomento sono stati esplorati, indipendentemente dalla profondita di ciascuno.

| Score | Criterio |
|-------|----------|
| 1 | 1-2 sotto-temi, solo gli aspetti piu ovvi |
| 2 | 3-4 sotto-temi, tutti superficiali |
| 3 | 5-6 sotto-temi, mix di ovvi e meno ovvi |
| 4 | 7-8 sotto-temi, include aspetti non funzionali o edge case |
| 5 | 9+ sotto-temi, copertura sistematica che include aspetti che uno stakeholder non avrebbe menzionato spontaneamente |

**Cosa valutare**: il valutatore identifica i sotto-temi trattati e li confronta con un elenco "ideale" di aspetti rilevanti per il topic dato il `project_idea`. La lista ideale viene generata dal valutatore stesso come benchmark.

### Dimensione 4: Profondita di elicitazione

Misura la capacita dell'interviewer di scavare oltre le risposte iniziali dello stakeholder: follow-up, richieste di chiarimento, richiesta di esempi concreti, esplorazione di edge case.

| Score | Criterio |
|-------|----------|
| 1 | Nessun follow-up; l'interviewer accetta ogni risposta e passa oltre |
| 2 | 1-2 follow-up nell'intera conversazione, prevalentemente superficiali |
| 3 | Follow-up presenti ma solo quando lo stakeholder e palesemente vago; non esplora proattivamente edge case |
| 4 | Follow-up sistematici su risposte vaghe; almeno 1-2 domande su edge case o scenari di errore |
| 5 | Ogni risposta non completamente dettagliata riceve un follow-up; l'interviewer anticipa scenari problematici e li esplora |

**Cosa valutare**: per ogni turno, verificare se la domanda e un approfondimento della risposta precedente (follow-up) o un cambio di sotto-tema. Contare i follow-up e valutarne la pertinenza. Un'intervista in cui ogni risposta produce immediatamente una nuova domanda su un sotto-tema diverso ha profondita bassa.

### Dimensione 5: Qualita delle domande

Misura la formulazione delle singole domande: chiarezza, specificita, e capacita di guidare lo stakeholder verso risposte utili senza predeterminarne il contenuto.

| Score | Criterio |
|-------|----------|
| 1 | Domande generiche e aperte che non guidano ("Parlami delle notifiche"), oppure domande chiuse che ammettono solo si/no |
| 2 | Mix di domande troppo aperte e troppo chiuse; formulazione confusa |
| 3 | Domande mediamente ben formulate; occasionali domande doppie (2 domande in una) o suggestive |
| 4 | Domande chiare, una alla volta, ben motivate ("Te lo chiedo perche..."); rare domande doppie |
| 5 | Ogni domanda e singola, chiara, motivata, e calibrata sulla risposta precedente; nessuna domanda suggestiva o doppia |

**Cosa valutare**: per ogni turno verificare se il `message` contiene una sola domanda, se include una motivazione, se e formulata in modo aperto ma focalizzato. Penalizzare domande che contengono gia la risposta attesa o che pongono piu quesiti contemporaneamente.

## Formula aggregata

```
interview_quality_score = (efficienza × 0.15) + (progressione × 0.20) + (copertura × 0.25) + (profondita × 0.25) + (qualita_domande × 0.15)
```

**Pesi**: copertura e profondita hanno il peso maggiore perche determinano direttamente la quantita e qualita delle informazioni raccolte. Progressione ha peso significativo perche una sequenza logica riduce il rischio di gap. Efficienza e qualita delle domande hanno peso minore: sono indicatori di "pulizia" del processo ma non impattano direttamente i requisiti prodotti.

## Output JSON proposto

```json
{
  "status": "ok",
  "scenario_id": "...",
  "topic": "...",

  "turn_analysis": [
    {
      "turn_number": 1,
      "turn_type": "setup",
      "subtopic": null,
      "is_followup": false,
      "question_count": 1,
      "has_motivation": true,
      "note": "Presentazione e scelta argomento"
    },
    {
      "turn_number": 3,
      "turn_type": "substantive",
      "subtopic": "eventi che generano notifica",
      "is_followup": false,
      "question_count": 1,
      "has_motivation": true,
      "note": "Prima domanda sostanziale, ben formulata"
    }
  ],

  "efficiency": {
    "score": 4,
    "total_turns": 11,
    "setup_turns": 2,
    "substantive_turns": 7,
    "closure_turns": 2,
    "ratio": 0.64,
    "note": "..."
  },

  "progression": {
    "score": 5,
    "subtopic_sequence": [
      "eventi notifica",
      "canali di invio",
      "configurabilita utente",
      "vincoli eventi obbligatori",
      "timing e anti-spam",
      "contenuto notifica",
      "deep link e fallback"
    ],
    "jumps": 0,
    "note": "..."
  },

  "coverage": {
    "score": 4,
    "subtopics_covered": ["..."],
    "subtopics_missing": ["..."],
    "ideal_subtopics": ["..."],
    "note": "..."
  },

  "depth": {
    "score": 3,
    "followup_count": 1,
    "followup_turns": [6],
    "edge_cases_explored": 1,
    "note": "..."
  },

  "question_quality": {
    "score": 4,
    "single_question_ratio": 0.85,
    "motivated_ratio": 1.0,
    "double_questions": [7],
    "note": "..."
  },

  "interview_quality_score": 3.9,
  "strengths": ["...", "..."],
  "weaknesses": ["...", "..."]
}
```

## Valore aggiunto

### 1. Diagnostica del prompt interviewer

Oggi se un set di requisiti ha score basso, non sappiamo se il problema e nel prompt dell'interviewer (domande sbagliate), nel prompt di estrazione (parsing difettoso) o nel prompt di valutazione (giudizio incoerente). L'interview quality score isola il primo anello della catena.

**Esempio concreto**: se `interview_quality_score` e alto ma `overall_score` dei requisiti e basso, il collo di bottiglia e nell'estrazione. Se entrambi sono bassi, il problema e nell'intervista.

### 2. Confronto A/B tra prompt interviewer

Attualmente il confronto tra prompt interviewer diversi passa solo dai requisiti prodotti. Due prompt possono produrre requisiti simili per vie molto diverse. L'interview quality score permette di confrontare il *come*: quale prompt produce interviste piu efficienti, con migliore progressione, con copertura piu ampia.

**Esempio concreto**: il prompt A produce 8 requisiti in 20 turni (efficienza bassa, molte ripetizioni), il prompt B ne produce 8 in 11 turni (efficienza alta). I requisiti hanno score simile, ma il prompt B e obiettivamente migliore. Senza la metrica di intervista, i due prompt risultano equivalenti.

### 3. Feedback specifico per l'ottimizzazione del prompt

Le 5 dimensioni indicano *dove* intervenire nel prompt:

| Score basso in... | Intervento sul prompt |
|-------------------|-----------------------|
| Efficienza | Ridurre le istruzioni di meta-comunicazione, semplificare il setup |
| Progressione | Rinforzare l'istruzione "piramide invertita", aggiungere sequenza esplicita |
| Copertura | Aggiungere una checklist di sotto-temi piu dettagliata |
| Profondita | Aggiungere istruzioni esplicite su follow-up e edge case |
| Qualita domande | Aggiungere vincoli sulla formulazione (una domanda, motivazione obbligatoria) |

### 4. Correlazione con la qualita dei requisiti

Avendo sia `interview_quality_score` che `overall_score` per lo stesso run, si puo misurare la correlazione: le interviste migliori producono effettivamente requisiti migliori? Se la correlazione e debole, significa che il bottleneck non e nell'intervista ma altrove nella pipeline. Questa informazione e impossibile da ottenere senza la metrica di intervista.

### 5. Regressione temporale

Man mano che il prompt dell'interviewer evolve (v1, v2, ...), l'interview quality score fornisce una serie storica che mostra se le modifiche migliorano o peggiorano il processo, indipendentemente dalla varianza naturale del modello LLM.

## Conseguenze

### Implementazione richiesta

1. Nuovo prompt `prompts/interview_evaluator.md` con la rubrica sopra descritta
2. Nuova funzione `evaluate_interview()` in `evaluation.py` (o file dedicato)
3. Nuova directory di output `output_test/{prompt}/{model}/interview_evaluations/{scenario_id}/`
4. Integrazione nella pipeline come step opzionale post-simulazione (prima dell'estrazione)
5. Integrazione nella web UI: dettaglio intervista con radar chart delle 5 dimensioni
6. Aggiornamento del confronto A/B per includere i dati dell'intervista

### Costi

- **Token aggiuntivi**: ogni valutazione di intervista richiede una chiamata LLM con la conversazione completa come input (~5-10K token input, ~2-3K output). Per una pipeline completa, aggiunge circa il 10-15% ai costi totali.
- **Complessita**: un nuovo step nella pipeline significa un nuovo punto di fallimento e un nuovo file di output da gestire.

### Rischi

- **Soggettivita del valutatore LLM**: la valutazione della "progressione tematica" o della "profondita di elicitazione" e intrinsecamente soggettiva. Va calibrata con valutazioni manuali su un campione iniziale.
- **Stabilita inter-run**: lo stesso LLM potrebbe dare score diversi sulla stessa conversazione in run diverse. Va misurata la varianza prima di usare lo score per decisioni.

## Alternative considerate

### A. Metriche puramente automatiche (senza LLM)

Calcolare solo metriche estratte dal JSON: numero turni, token per turno, rapporto domande/risposte, lunghezza media risposte. Scartata perche queste metriche catturano la forma ma non il contenuto: un'intervista con 15 turni di domande irrilevanti avrebbe le stesse metriche di una con 15 turni di domande perfette.

### B. Valutazione integrata nel requirements evaluator

Aggiungere le metriche di intervista al prompt `evaluator.md` esistente, che riceverebbe sia i requisiti che la conversazione. Scartata perche sovraccarica un prompt gia complesso e mescola due valutazioni indipendenti: i requisiti vanno valutati senza conoscere la conversazione (per essere confrontabili con requisiti scritti manualmente), e l'intervista va valutata senza conoscere i requisiti estratti (per isolare il processo dal risultato).

### C. Non fare nulla

Continuare a usare solo il requirements evaluation come proxy. Accettabile nel breve periodo, ma insufficiente per l'ottimizzazione sistematica del prompt interviewer.
