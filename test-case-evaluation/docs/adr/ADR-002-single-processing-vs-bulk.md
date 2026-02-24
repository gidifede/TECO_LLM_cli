# ADR-002: Elaborazione singola dei requisiti vs invio in blocco

**Data**: 2026-02-19
**Stato**: Accettata
**Decisori**: Team TECO_LLM_cli

## Contesto

La pipeline TECO_LLM_cli trasforma requisiti in user stories e poi in test cases tramite chiamate ad Azure OpenAI. L'input attuale e un file JSON con **82 requisiti**, ciascuno con una media di **3,1 acceptance criteria**. Ogni requisito occupa in media ~360 token; l'intero dataset occupa ~29.500 token.

I prompt di sistema pesano ~1.650 token (user stories) e ~1.940 token (test cases). Il parametro `max_tokens` per la risposta e impostato a **16.384** (default della pipeline).

### Modelli disponibili

L'interfaccia interattiva (`teco-interactive`) permette all'utente di selezionare uno dei seguenti modelli Azure OpenAI. I limiti di token variano significativamente:

| Modello | Context window | Max output | Note |
|---------|---------------|------------|------|
| **gpt-4.1** (default) | 1.048.576 | 32.768 | Deploy standard/provisioned: context effettivo 128K |
| **gpt-5.1** | 400.000 (272K input + 128K output) | 128.000 | |
| **gpt-5.2** | 400.000 (272K input + 128K output) | 128.000 | |
| **gpt-5.1-chat** | 128.000 (112K input + 16K output) | 16.384 | Preview, output limitato |
| **gpt-5-mini** | 400.000 (272K input + 128K output) | 128.000 | |

Le stime di token nelle sezioni successive usano questi limiti come riferimento. L'analisi di fattibilita e condotta per modello dove rilevante.

La domanda e: come suddividere le chiamate al modello? Un requisito alla volta, tutti insieme, o a gruppi?

## Opzioni valutate

### Opzione A — Single (un requisito per chiamata)

Per ogni requisito si esegue una chiamata LLM per generare le user stories, poi una seconda per generare i test cases delle US appena prodotte. Con 82 requisiti si eseguono 164 chiamate totali.

- **Input per chiamata US**: ~2.000 token (system prompt + 1 requisito)
- **Output per chiamata US**: ~1.500 token (3 user stories)
- **Input per chiamata TC**: ~3.400 token (system prompt + 3 US)
- **Output per chiamata TC**: ~4.500 token (test cases)

### Opzione B — Bulk (tutti i requisiti in una chiamata)

Si inviano tutti gli 82 requisiti in una singola chiamata per la generazione delle US, poi tutte le US risultanti in una singola chiamata per i TC. Si eseguono 2 chiamate totali.

- **Input chiamata US**: ~31.000 token (system prompt + 82 requisiti)
- **Output atteso US**: ~123.000 token (82 x 3 US x ~500 token)
- **Input chiamata TC**: ~125.000 token (system prompt + ~250 US)
- **Output atteso TC**: ~370.000 token

### Opzione C — Batch (gruppi di N requisiti per chiamata)

Si inviano gruppi di 5-10 requisiti per chiamata. Si eseguono 9-17 chiamate per le US e altrettante per i TC.

- **Input per chiamata US** (batch da 10): ~5.200 token
- **Output per chiamata US** (batch da 10): ~15.000 token
- **Chiamate totali US**: ~9

## Confronto

### 1. Fattibilita tecnica (token limit)

Output richiesto per chiamata:

| | Single | Batch (10) | Bulk |
|---|---|---|---|
| Output per chiamata US | ~1.500 | ~15.000 | ~123.000 |
| Output per chiamata TC | ~4.500 | ~45.000 | ~370.000 |

Compatibilita per modello (step US):

| Modello | Max output | Single (~1.500) | Batch 10 (~15.000) | Bulk (~123.000) |
|---------|-----------|-----------------|--------------------|--------------------|
| gpt-4.1 | 32.768 | Si | Si | No |
| gpt-5.1 | 128.000 | Si | Si | Limite (~123K su 128K) |
| gpt-5.2 | 128.000 | Si | Si | Limite (~123K su 128K) |
| gpt-5.1-chat | 16.384 | Si | Si (margine ridotto) | No |
| gpt-5-mini | 128.000 | Si | Si | Limite (~123K su 128K) |

Compatibilita per modello (step TC):

| Modello | Max output | Single (~4.500) | Batch 10 (~45.000) | Bulk (~370.000) |
|---------|-----------|-----------------|--------------------|--------------------|
| gpt-4.1 | 32.768 | Si | No | No |
| gpt-5.1 | 128.000 | Si | Si | No |
| gpt-5.2 | 128.000 | Si | Si | No |
| gpt-5.1-chat | 16.384 | Si | No | No |
| gpt-5-mini | 128.000 | Si | Si | No |

**Osservazioni:**

- **Bulk US** e teoricamente al limite con i modelli da 128K di output (gpt-5.1, gpt-5.2, gpt-5-mini): l'output stimato (~123K) si avvicina al tetto massimo, lasciando margine quasi nullo. In pratica, la generazione di JSON strutturato di quella dimensione produce degradazione dello schema e troncamenti parziali ben prima del limite nominale.
- **Bulk TC** e **impossibile su tutti i modelli**: ~370K di output richiesto eccede anche il massimo di 128K.
- **Batch TC** e fattibile solo con modelli da 128K di output. Con gpt-4.1 (32K) e gpt-5.1-chat (16K), un batch da 10 (~45K output) eccede il limite.
- **Single** e l'unico approccio **compatibile con tutti i modelli** senza eccezioni.

Batch richiede logica adattiva per regolare la dimensione dei gruppi in base al modello selezionato, introducendo complessita nella gestione.

### 2. Qualita dell'output

| Criterio | Single | Batch | Bulk |
|---|---|---|---|
| Attenzione del modello | Totale su 1 requisito | Divisa tra 5-10 | Dispersa su 82 |
| Effetto "lost in the middle" | Non applicabile | Rischio basso | Rischio alto |
| Validazione semantica (accept/reject) | Precisa per requisito | Ambigua — se 1 su 10 va rifiutato, il modello tende a includerlo | Non praticabile |
| Aderenza allo schema JSON | JSON piccolo, quasi sempre valido | JSON medio, generalmente valido | JSON enorme, alto rischio di drift |

La validazione semantica e particolarmente critica. Il prompt di generazione US prevede che il modello possa rifiutare un requisito immaturo restituendo `{"status": "rejected", ...}`. In modalita single questa decisione e netta: un requisito, un verdetto. In batch il modello dovrebbe gestire verdetti misti (alcuni ok, alcuni rejected) nello stesso output, con rischio di incoerenza.

### 3. Resilienza agli errori

| Scenario di fallimento | Single | Batch | Bulk |
|---|---|---|---|
| Timeout o rate limit | 1 requisito perso | 5-10 requisiti persi | Tutto perso |
| JSON malformato nella risposta | 1 requisito da riprovare | 5-10 da riprovare | Tutto da riprovare |
| Ripresa dopo interruzione | Riparti dall'ultimo completato | Riparti dall'ultimo batch | Riparti da zero |
| Errore in 1 requisito | Gli altri 81 sono gia completati | Gli altri batch non sono impattati ma il batch corrente va riprovato | Nessun risultato salvato |

In produzione con 82 requisiti la probabilita di almeno un errore (timeout, rate limit, risposta malformata) e significativa. L'approccio single isola ogni errore.

### 4. Coerenza cross-requisito

Questo e l'**unico vantaggio teorico** dell'approccio bulk/batch. Se il modello vede piu requisiti nella stessa chiamata:

- Puo uniformare la terminologia tra user stories di requisiti diversi
- Puo identificare sovrapposizioni o dipendenze tra requisiti
- Puo evitare duplicazioni cross-requisito

Tuttavia, nel contesto di questo progetto, i requisiti sono generati da una pipeline precedente (Storyteller web) e arrivano gia strutturati e auto-contenuti. La coerenza cross-requisito e responsabilita della fase di generazione dei requisiti, non della fase di trasformazione in user stories.

### 5. Costo

| | Single (164 call) | Batch (18 call) | Bulk (2 call) |
|---|---|---|---|
| System prompt | Cached dopo la 1a chiamata | Cached dopo la 1a chiamata | Pagato 1 volta |
| Input totale stimato | ~450k token (gran parte cached) | ~95k token | ~156k token |
| Output totale stimato | ~490k token | ~490k token | ~490k token (se non tronca) |

L'output totale e identico indipendentemente dall'approccio: il modello deve produrre lo stesso numero di user stories e test cases. Con il prompt caching di Azure OpenAI, il system prompt (~1.650-1.940 token) viene cachato dopo la prima chiamata, riducendo il costo effettivo delle chiamate successive. La differenza di costo tra single e batch e marginale.

### 6. Latenza

| | Single (sequenziale) | Single (5 parallele) | Batch (sequenziale) |
|---|---|---|---|
| Chiamate US | 82 x ~10s = ~14 min | ~3 min | 9 x ~30s = ~4.5 min |
| Chiamate TC | 82 x ~15s = ~20 min | ~5 min | 9 x ~45s = ~7 min |
| Totale stimato | ~34 min | ~8 min | ~11.5 min |

L'approccio single e il piu lento in modalita sequenziale, ma diventa competitivo con parallelismo. L'aggiunta futura di chiamate concorrenti (es. 5-10 in parallelo, compatibilmente con i rate limit di Azure) ridurrebbe la latenza senza cambiare la granularita.

## Sintesi

| Criterio | Single | Batch | Bulk |
|---|---|---|---|
| Fattibilita tecnica | Si (tutti i modelli) | Parziale (dipende dal modello e dallo step) | No (step TC impossibile su tutti) |
| Qualita per requisito | Massima | Buona | Non valutabile |
| Validazione semantica | Precisa | Ambigua | Non praticabile |
| Resilienza agli errori | Massima | Media | Minima |
| Coerenza cross-requisito | Nessuna | Parziale | Teoricamente alta |
| Costo | Comparabile | Comparabile | Inferiore ma irrealistico |
| Latenza (sequenziale) | Alta | Media | N/A |
| Latenza (con parallelismo) | Media | Media | N/A |
| Complessita implementativa | Bassa | Media (gestione batch size) | Bassa |

## Decisione

**Opzione A — Single processing (un requisito per chiamata).**

Ogni requisito viene elaborato individualmente: una chiamata per generare le user stories, una seconda per generare i test cases dalle US prodotte.

## Motivazioni

1. **Bulk e tecnicamente impossibile per lo step TC** (~370K output richiesto) su tutti i modelli disponibili. Per lo step US (~123K), i modelli con 128K di output (gpt-5.1, gpt-5.2, gpt-5-mini) sono al limite nominale, ma la generazione di JSON strutturato di grandi dimensioni degrada in pratica ben prima di quel tetto. Bulk non e fattibile con gpt-4.1 (32K) ne con gpt-5.1-chat (16K).

2. **La qualita per-requisito e massima** perche il modello dedica la totalita della finestra di attenzione a un singolo requisito. Non c'e rischio di effetto "lost in the middle".

3. **La validazione semantica accept/reject e precisa**: un requisito, un verdetto. Non ci sono ambiguita su verdetti misti nello stesso output.

4. **La resilienza e massima**: un errore (timeout, rate limit, JSON malformato) impatta solo 1 requisito su 82. I risultati gia prodotti sono salvi e la pipeline puo riprendere dall'ultimo requisito completato.

5. **La coerenza cross-requisito non e responsabilita di questo step**: i requisiti arrivano gia strutturati dalla pipeline Storyteller e devono essere auto-contenuti.

6. **Il costo e comparabile** agli altri approcci grazie al prompt caching di Azure OpenAI.

7. **La latenza e gestibile**: l'attuale approccio sequenziale puo essere migliorato in futuro con parallelismo senza cambiare la granularita dell'elaborazione.

## Conseguenze

- La pipeline mantiene l'architettura attuale con le funzioni `process_requirement_to_us()` e `process_us_to_tc()` che operano su singoli requisiti
- Il parametro `max_tokens` e impostato a **16.384** (default). Questo valore e compatibile con tutti i modelli disponibili (il piu limitato, gpt-5.1-chat, ha un massimo di 16.384). Per i modelli con output fino a 128K (gpt-5.1, gpt-5.2, gpt-5-mini), il valore puo essere alzato dall'utente via `--max-tokens` se necessario
- L'approccio single e l'unico **compatibile con tutti i modelli** senza necessita di adattamenti — un vantaggio ulteriore dato che l'interfaccia interattiva permette il cambio modello a runtime
- Un miglioramento futuro previsto e l'aggiunta di **parallelismo** (N chiamate concorrenti) per ridurre la latenza totale, senza modificare la granularita
- Se in futuro emergesse la necessita di coerenza cross-requisito, l'approccio consigliato e un **post-processing** di normalizzazione terminologica, non il passaggio a bulk
