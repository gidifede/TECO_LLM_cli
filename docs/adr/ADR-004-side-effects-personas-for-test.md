# ADR-004: Side effects dell'approccio persona-based per la generazione di user stories

**Data**: 2026-02-20
**Stato**: Proposta
**Decisori**: Team TECO_LLM_cli
**Relazione con**: ADR-001 (decomposizione per acceptance criterion)

## Contesto

La pipeline attuale decompone ogni requisito in user stories seguendo la regola stabilita in ADR-001: **una user story per ogni acceptance criterion**. Questa regola produce una catena di tracciabilità lineare: `REQ → AC → US → TC`.

Si sta valutando un approccio alternativo in cui l'asse di decomposizione diventa la **persona** (attore) anziché l'acceptance criterion: **una user story per ogni persona coinvolta nel requisito**. L'obiettivo è ottenere user stories più user-centred, che catturino l'esperienza completa di ogni tipo di utente.

Questo ADR documenta i side effects e le implicazioni di questa scelta, senza prendere una decisione definitiva. Serve come analisi d'impatto per guidare la progettazione del nuovo prompt.

## Confronto tra i due approcci

| Aspetto | AC-based (ADR-001) | Persona-based (proposto) |
|---|---|---|
| Asse di decomposizione | 1 US per acceptance criterion | 1 US per persona coinvolta |
| Cardinalità | N = numero di AC | N = numero di personas distinte nel requisito |
| Prevedibilità di N | Alta (basta contare gli AC) | Media-alta (personas note come contesto, serve determinare quali sono coinvolte) |
| Granularità | Uniforme, proporzionale alla complessità funzionale | Variabile, proporzionale al numero di attori |
| Testabilità intrinseca | Alta (ogni US = un criterio verificabile) | Media (ogni US aggrega più AC per una persona) |

## Side effects identificati

### 1. Cambio della regola fondamentale di decomposizione

La regola attuale è deterministica e verificabile: `N acceptance criteria → N user stories`. La regola proposta diventa: `N personas coinvolte nel requisito → N user stories`. Il numero di stories non dipende più da cosa il sistema deve fare, ma da chi interagisce con il sistema.

**Impatto**: la prevedibilità del volume di output cambia natura. Con l'approccio AC-based, basta contare gli AC nel JSON per sapere quante US aspettarsi. Con l'approccio persona-based, il numero massimo di US è noto (= numero di personas nel contesto), ma il modello deve determinare quali personas sono coinvolte nel requisito corrente — un passaggio interpretativo, anche se mitigato dal fatto che le personas sono fornite come input esplicito e non inferite dal testo.

### 2. Input aggiuntivo: le personas vengono passate come contesto

Nell'approccio AC-based, la persona è un campo derivato dal contesto di ogni acceptance criterion. Nell'approccio persona-based, le personas diventano l'asse portante della decomposizione e devono essere **definite in modo esplicito e condiviso**.

**Decisione**: le personas vengono passate come contesto aggiuntivo al prompt, estratte dai requisiti di categoria PERSONAS (es. REQ-P-001). Il modello non le inferisce dal singolo requisito.

Questo comporta:

- **Coerenza garantita**: tutte le US del progetto usano la stessa lista di personas, con nomi e canali identici. Non c'è rischio di variabilità tra esecuzioni diverse.
- **Prevedibilità migliorata**: il numero di personas è noto a priori (è nel JSON di input). Il modello deve solo determinare quali personas del contesto sono coinvolte nel requisito corrente.
- **Doppio input al prompt**: il modello riceve sia il requisito da trasformare sia il blocco personas come contesto. Il prompt deve istruire il modello su come usare il contesto senza confonderlo con il requisito.

**Impatto sulla pipeline**: la funzione `process_requirement_to_us` in `pipeline.py` deve essere modificata per:

1. Filtrare i requisiti di categoria PERSONAS dall'elenco dei requisiti da trasformare
2. Serializzare il contenuto dei REQ-P come blocco di contesto
3. Passare il contesto personas nel `user_content` insieme al singolo requisito

La funzione `_serialize_requirement` resta invariata. Serve una nuova funzione (es. `_serialize_personas_context`) che produca il blocco di contesto dalle personas.

### 3. Gestione degli acceptance criteria trasversali

Con l'approccio AC-based, ogni AC è assegnato a esattamente una US (mapping 1:1). Con l'approccio persona-based, ogni US dovrebbe contenere tutti gli AC rilevanti per quella persona. Questo crea una complessità:

- **AC trasversali a più personas**: un AC come "Il sistema espone offerte filtrate in output" potrebbe riguardare sia il cliente digitale (che le visualizza) sia l'operatore di sportello (che le propone).
- **AC senza persona esplicita**: un AC come "La funzionalità NBO è attivata e documentata" non ha un attore chiaro. Con l'approccio AC-based funziona (genera una US autonoma). Con l'approccio persona-based, dove si colloca?
- **AC tecnici o di sistema**: alcuni AC descrivono comportamenti del sistema che non sono legati a un attore specifico. Rischiano di rimanere orfani.

**Decisione**:

- **AC trasversali**: vengono replicati in ogni US delle personas coinvolte, riscrivendoli dal punto di vista di ciascuna persona. La ridondanza viene segnalata nel campo `notes` della US.
- **AC senza persona / tecnici**: vengono assegnati a una persona convenzionale "Sistema" e la US risultante riporta nel campo `assumptions` che l'attore è stato assunto in assenza di indicazione esplicita.

### 4. Modifica della catena di tracciabilità

La catena attuale è lineare e biunivoca:

```
REQ-F-001 → AC₁ → REQ-F-001.US01 → TC
            AC₂ → REQ-F-001.US02 → TC
            AC₃ → REQ-F-001.US03 → TC
```

La catena proposta diventa una relazione molti-a-molti:

```
REQ-F-001 → Persona A → REQ-F-001.US01 (contiene AC₁, AC₂)    → TC
            Persona B → REQ-F-001.US02 (contiene AC₁, AC₃)    → TC
            Persona C → REQ-F-001.US03 (contiene AC₂)          → TC
```

**Impatto**: lo stesso AC può apparire in più US (ridondanza controllata e segnalata nel campo `notes`). La tracciabilità dal TC al singolo AC originale diventa meno diretta, ma lo schema JSON resta invariato per compatibilità con il prompt test cases.

**Relazione con ADR-001**: l'approccio persona-based **contraddice** la decisione presa in ADR-001. Se adottato, ADR-001 andrebbe marcata come "Superata" per il prompt persona-based, pur restando valida per il prompt AC-based (se entrambi coesistono).

### 5. Variabilità nel numero di user stories

Con l'approccio AC-based, la granularità è proporzionale alla complessità funzionale del requisito (più AC = più US). Con l'approccio persona-based, la granularità dipende dalla pluralità degli attori:

| Scenario | AC-based | Persona-based |
|---|---|---|
| REQ con 5 AC, 1 persona | 5 US (granulari) | 1 US (ampia, 5 AC dentro) |
| REQ con 2 AC, 6 personas | 2 US (focalizzate) | 6 US (rischio di stories sottili) |
| REQ con 3 AC, 3 personas | 3 US | 3 US (coincidenza numerica, ma taglio diverso) |

**Impatto**: requisiti che coinvolgono un solo attore producono una singola user story che contiene tutti gli AC — di fatto una story ampia e meno atomica. Al contrario, requisiti che coinvolgono molti attori producono molte stories, alcune potenzialmente sottili (se la persona ha un ruolo marginale nel requisito).

### 6. Impatto sulla generazione dei test cases a valle

Il prompt dei test cases (`prompt_test_cases.md` e `prompt_test_cases_strict_check.md`) si aspetta user stories con:

- `acceptance_criteria` in formato "QUANDO... ALLORA..."
- `story_id` nel formato `REQ-XXX.USNN`
- `persona`, `channels`, `business_rules`, `edge_cases`

Lo schema JSON della user story non cambia. Il contenuto degli `acceptance_criteria` interni alla US cambia: con l'approccio persona-based, una singola US può contenere più AC originali riscritti dal punto di vista della persona.

**Impatto**: il prompt test cases non richiede modifiche strutturali, purché le US in output rispettino lo stesso schema JSON. Tuttavia, US più ampie (con più AC aggregati) tenderanno a produrre test cases più numerosi e meno focalizzati per singola story.

### 7. Cambio di ruolo per i requisiti di categoria PERSONAS

Attualmente i requisiti REQ-P-xxx (categoria PERSONAS) passano nella pipeline come qualsiasi altro requisito e vengono trasformati in user stories. Tuttavia le loro US risultano poco significative, perché descrivono la lista degli attori e non un comportamento del sistema.

Con l'approccio persona-based, i REQ-P diventano un **input di contesto** — la definizione autoritativa delle personas del progetto — e non un requisito da trasformare. Questo è coerente con la decisione presa nel side effect #2: le personas vengono passate come contesto aggiuntivo al prompt.

**Impatto sulla pipeline**: serve una logica di filtraggio in `run_pipeline` che:

1. Estragga i requisiti di categoria PERSONAS come contesto (prima del loop di elaborazione)
2. Li serializzi in un blocco di contesto con la nuova funzione `_serialize_personas_context`
3. Li passi come parte del `user_content` per ogni requisito non-PERSONAS
4. Li escluda dal loop di trasformazione in user stories

### 8. Rischio sulla testabilità delle user stories

Le US per AC sono intrinsecamente testabili: ogni story descrive un singolo comportamento verificabile. Le US per persona rischiano di essere più **narrative** (descrivono l'esperienza completa dell'utente) e meno **atomiche** (aggregano più comportamenti).

**Impatto**: il prompt persona-based deve includere regole esplicite per garantire che le US restino testabili:

- Ogni US deve comunque avere `acceptance_criteria` in formato "QUANDO... ALLORA..."
- Gli AC interni alla US devono essere verificabili individualmente
- L'aggregazione per persona non deve produrre stories vaghe o generiche

### 9. Vantaggio: user stories più user-centred

L'approccio persona-based produce stories più aderenti al design thinking e alla prospettiva dell'utente finale:

- Ogni story cattura l'**esperienza completa** di un tipo di utente
- Le stories sono più leggibili per **stakeholder non tecnici**
- Facilitano la **validazione con il business** (il PO può confermare: "sì, l'operatore di sportello fa esattamente questo")
- Sono più utili per il **design UX** e la progettazione delle interfacce
- Evidenziano meglio le **differenze di esperienza** tra canali e ruoli diversi

## Decisioni prese

1. **Input delle personas**: le personas vengono passate come contesto aggiuntivo, estratte dai requisiti di categoria PERSONAS (es. REQ-P-001). Il modello non le inferisce dal singolo requisito. Vedi side effect #2.
2. **AC trasversali**: vengono replicati in ogni US delle personas coinvolte, con segnalazione della ridondanza nel campo `notes`. Vedi side effect #3.
3. **AC senza persona / requisiti puramente tecnici**: vengono assegnati a una persona convenzionale "Sistema", con segnalazione nel campo `assumptions`. Vedi side effect #3.
4. **Requisito con una sola persona**: produce una singola US con tutti gli AC aggregati. Nessun fallback alla decomposizione per AC. Vedi side effect #5.
5. **Coesistenza dei due approcci**: il prompt persona-based coesiste con quello AC-based come file separato (`prompt_user_stories_persona.md`). ADR-001 resta valida per il flusso AC-based.
6. **Schema JSON di output**: resta identico all'attuale (stessi campi) per garantire compatibilità con il prompt test cases. Nessun campo aggiuntivo. Vedi side effect #6.

## Conseguenze

- Creazione del prompt `prompt_user_stories_persona.md` come file separato, coesistente con `prompt_user_stories.md`
- Modifica di `pipeline.py` per gestire l'input delle personas come contesto
- Modifica di `pipeline.py` per filtrare i requisiti PERSONAS dalla trasformazione
- ADR-001 resta valida per il flusso AC-based
- Nessuna modifica necessaria al prompt test cases (schema JSON invariato)
