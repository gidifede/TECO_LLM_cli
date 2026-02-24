# Strategie suggerite per la pipeline test-evaluator

> **Nota (2026-02-23):** La **Strategia A** (usare solo diretto + persona-based) è stata implementata. Il percorso AC-based è stato rimosso dalla pipeline. La sezione 2.1 e la Strategia E sono ora superate.

Analisi basata sulle valutazioni di coerenza di 5 requisiti (REQ-F-001, REQ-F-004, REQ-F-007, REQ-F-008, REQ-F-009) e sulla lettura completa dei prompt di generazione requisiti, user stories (AC-based e persona-based), test cases (diretti e indiretti) e valutazione.

---

## 1. Quadro dei risultati

| Requisito | Direct | Indirect Persona | Indirect AC | Vincitore |
|-----------|--------|-------------------|-------------|-----------|
| REQ-F-001 | 78     | 43                | 15          | direct    |
| REQ-F-004 | —      | —                 | —           | REJECTED  |
| REQ-F-007 | 73     | 60                | 0           | direct    |
| REQ-F-008 | 63     | 60                | 0           | direct    |
| REQ-F-009 | 77     | 43                | 0           | direct    |
| **Media** | **~73**| **~52**           | **~4**      | **direct sempre** |

Il percorso diretto vince in tutti i casi valutati. Il percorso indiretto AC-based ha score catastrofici (0 in 3 casi su 4). Il percorso persona-based si posiziona a metà ma con problemi sistematici.

---

## 2. Problemi per approccio

### 2.1 Percorso indiretto AC-based — Score medio: ~4/100 *(SUPERATA — rimosso dalla pipeline)*

Questo approccio ha un **difetto strutturale** che lo rende inutilizzabile nella forma attuale.

**Problema principale: disallineamento traced_criteria**

La catena è: Requisito (con AC-1..AC-N) → User Stories (1 US per AC, ciascuna con i propri AC riscritti) → Test Cases (traced_criteria riferiti agli AC della US).

Quando il valutatore confronta i TC con il requisito originale, i `traced_criteria` non corrispondono. Un TC che traccia "AC-1" della US si riferisce a un criterio riscritto, non all'AC-1 del requisito. Il valutatore vede un disallineamento sistematico e assegna score 0.

Questo non è un problema di qualità del modello: è un problema di **architettura della pipeline**. Il passaggio intermedio (US) riscrive gli AC in una nuova numerazione, e questa informazione di mappatura viene persa.

**Problema secondario: esplosione dei TC e drift informativo**

La decomposizione 1 US per AC produce 3-5 user stories, ciascuna con i propri edge cases, business rules, assumptions. Quando queste diventano input per la generazione TC, il modello genera 15-23 TC (vs 5-11 del percorso diretto) con molte informazioni inventate. REQ-F-001 ha 15 added_info nel percorso AC-based vs 4 nel diretto. È un effetto "telefono senza fili" amplificato: ogni passaggio aggiunge rumore.

### 2.2 Percorso indiretto persona-based — Score medio: ~52/100

Funziona meglio dell'AC-based ma ha problemi propri.

**Problema: AC inesistenti**

Il modello genera TC con riferimenti ad AC che non esistono nel requisito. In REQ-F-007 i TC tracciano AC-5 e AC-6 quando il requisito ha solo AC-1..AC-4. In REQ-F-009 si riferiscono ad AC-4 inesistente. Questo indica che il passaggio attraverso le US persona-based "inquina" la numerazione degli AC originali.

**Problema: copertura incompleta**

In REQ-F-007 manca AC-4, in REQ-F-009 manca AC-3. La decomposizione per persona tende a concentrarsi sugli aspetti rilevanti per quel ruolo, tralasciando AC trasversali o tecnici che non si attaccano naturalmente a nessuna persona.

**Problema: informazioni aggiunte da contesto persona**

Le US persona-based arricchiscono il contesto con canali specifici (App/Web/UP), ruoli operativi, pattern di autenticazione. Queste info diventano parte dei TC ma non sono tracciabili al requisito → penalizzazione coerenza.

### 2.3 Percorso diretto — Score medio: ~73/100

È il migliore, ma non è esente da problemi.

**Problema: informazioni aggiunte sistematiche**

Anche il percorso diretto aggiunge informazioni non presenti nel requisito (4-7 added_info per valutazione). Questo è causato dal prompt `from_requirements.md` che istruisce esplicitamente il modello a generare test per "autorizzazioni", "edge cases", "multi-channel", "resilienza" — anche quando il requisito non menziona nulla di tutto ciò. Il modello obbedisce al prompt e inventa scenari di timeout, ruoli specifici, canali API, strutture di log.

**Problema: conflitto obiettivo prompt vs obiettivo valutazione**

Il prompt TC dice: "genera almeno test per input non validi, permessi insufficienti, servizi non disponibili, dati mancanti". Il valutatore dice: "ogni informazione presente nei TC deve essere tracciabile al requisito". Questi due obiettivi sono **in contraddizione**: il primo chiede di aggiungere, il secondo penalizza le aggiunte.

---

## 3. Problemi a monte: la qualità dei requisiti

L'analisi delle valutazioni e del prompt di generazione requisiti (`requirements_latest.txt`) rivela che molti problemi nascono **prima** della pipeline TECO.

### 3.1 AC dichiarativi e non verificabili

Molti acceptance criteria sono formulati in modo dichiarativo invece che comportamentale:

- *"La funzionalità NBO è attivata e documentata come obiettivo primario"* (REQ-F-001 AC-1) — cosa significa "documentata"? Dove? Come si verifica?
- *"È possibile verificare tramite test funzionali che..."* (REQ-F-001 AC-3) — è un meta-criterio che parla dei test stessi, non di un comportamento del sistema
- *"Test di integrazione dimostrano che..."* (REQ-F-004 AC-3) — idem

Questo costringe il modello a *interpretare* gli AC, generando assunzioni che poi vengono penalizzate come "added_info".

### 3.2 Disallineamento descrizione vs AC

REQ-F-004 è stato **REJECTED** dalla valutazione perché la description parla di "flag upgrade per clienti che possiedono prodotti in bundle entro X giorni" ma gli AC non coprono questa funzionalità. Il modello di generazione TC interpreta la description e produce TC su funzionalità che gli AC non tracciano.

Questo è un problema del prompt di generazione requisiti: non impone che **ogni comportamento nella description sia coperto da almeno un AC**.

### 3.3 Dipendenze cross-requisito irrisolte

Diversi AC contengono rimandi ad altri requisiti:

- *"vedere criteri di integrazione e configuratore"* (REQ-F-001 AC-2)
- *"salvo eccezioni configurate dal marketing come specificato in REQ-F-004"* (REQ-F-009)

Questi rimandi sono opachi per il modello che genera i TC: non ha accesso all'altro requisito, quindi o ignora il vincolo o lo inventa.

### 3.4 Il prompt dei requisiti non struttura gli AC

Il prompt `requirements_latest.txt` chiede una lista generica `"criteri_accettazione": [""]` senza imporre formato o vincoli. Non chiede:
- formato QUANDO/ALLORA
- un attore esplicito per AC
- copertura completa della description
- assenza di riferimenti circolari

Il risultato sono AC vaghi, dichiarativi, a volte contraddittori con la description.

---

## 4. Strategie consigliate

### Strategia A — Intervento immediato: usare solo il percorso diretto *(IMPLEMENTATA)*

**Cosa fare:** Disabilitare o deprioritizzare i percorsi indiretti (AC-based e persona-based) per la generazione TC. Usare esclusivamente il percorso diretto `requisito → TC`.

**Perché:** I dati sono inequivocabili. Il percorso diretto ha score medio 73 vs 52 e 4. Il passaggio intermedio attraverso le user stories non aggiunge valore ai test cases — anzi lo sottrae.

**Nota:** Le user stories restano utili per backlog e refinement di sviluppo. Ma non dovrebbero essere usate come input per la generazione TC. Sono due output paralleli, non una catena sequenziale.

**Effort:** Minimo — basta modificare il flusso "Pipeline completa" per generare US e TC diretti in parallelo invece che in catena.

---

### Strategia B — Intervento sul prompt TC diretto: ridurre le added_info

**Cosa fare:** Modificare `from_requirements.md` per allinearlo all'obiettivo di coerenza:

1. Rimuovere o attenuare le istruzioni che chiedono esplicitamente di generare test per scenari non menzionati nel requisito (autorizzazione, resilienza, timeout, multi-canale) **a meno che il requisito li menzioni**
2. Aggiungere un vincolo esplicito: *"Non assumere funzionalità, ruoli, canali o comportamenti non derivabili dalla description e dagli acceptance criteria. Se un aspetto non è menzionato nel requisito, non generare TC per esso."*
3. Distinguere tra TC "core" (tracciabili al requisito) e TC "suggeriti" (aggiunte utili ma non nel requisito) usando un campo come `"source": "requirement"` vs `"source": "inference"`

**Perché:** Lo score 73 del percorso diretto perde punti quasi esclusivamente per added_info. Ridurre le aggiunte porterebbe lo score sopra 85-90.

**Effort:** Medio-basso — modifiche al prompt.

---

### Strategia C — Intervento strutturale: riscrivere il prompt dei requisiti

**Cosa fare:** Modificare `requirements_latest.txt` per produrre requisiti con AC di qualità superiore. Modifiche specifiche:

1. **Imporre il formato QUANDO/ALLORA per gli AC:**
   ```
   "criteri_accettazione": [
       "QUANDO [condizione/azione] ALLORA [risultato atteso verificabile]"
   ]
   ```

2. **Aggiungere un vincolo di copertura:** *"Ogni comportamento descritto nella description deve essere coperto da almeno un criterio di accettazione. Se la description menziona una funzionalità, deve esistere un AC che la renda verificabile."*

3. **Vietare rimandi generici:** *"I criteri di accettazione devono essere auto-contenuti. Non usare rimandi come 'vedere requisito X' o 'come definito nel configuratore'. Se il criterio dipende da un altro requisito, esplicitare il comportamento atteso in questo contesto."*

4. **Richiedere un attore per AC:** *"Ogni criterio di accettazione deve indicare chi esegue l'azione o chi osserva il risultato."*

**Perché:** AC strutturati e comportamentali riducono l'ambiguità che forza il modello a inventare. Il rejection di REQ-F-004 e i problemi di interpretazione di REQ-F-001 AC-1 nascono da AC mal formulati. Migliorare i requisiti a monte migliora tutti i percorsi a valle.

**Effort:** Medio — modifica al prompt requirements + ri-generazione dei requisiti.

---

### Strategia D — Pensiero laterale: generare direttamente user stories dalla chat

**Cosa fare:** Creare un prompt alternativo per `requirements_latest.txt` che produca direttamente user stories in formato strutturato dalla conversazione, saltando il passaggio intermedio dei requisiti tradizionali.

Il flusso diventa: **Chat → User Stories → TC diretti dalle US**

Invece di: Chat → Requisiti → (US) → TC

**Perché:** I requisiti generati dall'AI dalla chat sono un artefatto intermedio che:
- introduce ambiguità (description vs AC non allineati)
- usa formulazioni dichiarative invece che comportamentali
- contiene dipendenze cross-requisito irrisolvibili

Le user stories nel formato COME/VOGLIO/IN MODO CHE + AC in formato QUANDO/ALLORA sono già il formato più adatto alla generazione TC. Saltare il passaggio requisiti elimina una trasformazione lossy.

**Rischio:** Le user stories sono meno adatte a documentazione di alto livello e governance. Potrebbe servire un processo di "rollup" per generare documentazione requisiti dalle US (invertire la direzione).

**Effort:** Alto — nuovo prompt, nuovo flusso.

---

### Strategia E — Se si vuole mantenere il percorso indiretto: fix della tracciabilità *(SUPERATA — percorso AC-based rimosso)*

**Cosa fare (solo se i percorsi indiretti sono richiesti per altri motivi):**

1. **Passare gli AC originali come contesto ai TC:** Nel prompt `from_user_stories.md`, aggiungere un campo `original_requirement_ac` che contenga gli AC del requisito originale con la loro numerazione. Istruire il modello a tracciare i TC sia agli AC della US sia agli AC del requisito.

2. **Oppure post-processare i traced_criteria:** Dopo la generazione TC, usare un passo automatico (o un LLM call) che rimappi i `traced_criteria` dalla numerazione US alla numerazione requisito.

3. **Oppure cambiare la naming convention:** I `traced_criteria` nei TC indiretti dovrebbero essere nel formato `{REQ}.AC-N` (riferito al requisito) invece che `AC-N` (ambiguo — riferito alla US o al requisito?).

**Perché:** Il problema fondamentale dell'indirect_ac (score 0) è puramente un problema di tracciabilità, non di qualità dei TC. Risolvere il mapping renderebbe i punteggi più alti, anche se il drift informativo resterebbe.

**Effort:** Medio — modifiche ai prompt + eventuale step di post-processing.

---

## 5. Raccomandazione

Combinare le strategie in quest'ordine di priorità:

1. **Strategia A** (subito) — Usare il percorso diretto come default. Non servono modifiche al codice di pipeline, solo alla scelta dell'utente.

2. **Strategia B** (breve termine) — Allineare il prompt TC diretto all'obiettivo di coerenza. Guadagno atteso: +10/15 punti di coherence_score.

3. **Strategia C** (medio termine) — Ristrutturare il prompt dei requisiti per produrre AC comportamentali. Questo migliora tutta la catena a valle indipendentemente dal percorso scelto.

4. **Strategia D** (da valutare) — Se il processo lo consente, sperimentare la generazione diretta di US dalla chat. Ha il potenziale più alto ma richiede il cambiamento più profondo.

5. **Strategia E** (solo se necessario) — Fix della tracciabilità indiretta. Ha senso solo se i percorsi indiretti devono essere mantenuti per ragioni non legate alla coerenza (es. copertura per persona, analisi ruoli).
