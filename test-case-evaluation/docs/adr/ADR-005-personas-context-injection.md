# ADR-005: Iniezione del contesto personas nella pipeline persona-based

**Data**: 2026-02-23
**Stato**: Accettata
**Decisori**: Team TECO_LLM_cli
**Relazione con**: ADR-001 (decomposizione per AC), ADR-004 (side effects persona-based)

## Contesto

Il prompt `user_stories/persona_based.md` (ADR-004) prevede che il modello riceva, oltre al requisito da trasformare, un blocco di contesto contenente la definizione autoritativa delle personas del progetto. Questo contesto deve essere estratto dai requisiti di categoria `PERSONAS` presenti nel file `requirements.json`.

Attualmente la pipeline non distingue tra categorie di requisiti: tutti vengono trasformati in user stories con lo stesso prompt (AC-based). I requisiti PERSONAS vengono elaborati come qualsiasi altro requisito, producendo user stories poco significative perché descrivono attori, non comportamenti del sistema.

La decisione riguarda come e quando estrarre il contesto personas e renderlo disponibile al prompt persona-based.

## Decisione

**Il contesto personas viene estratto automaticamente dal file `requirements.json` al momento dell'esecuzione**, filtrando i requisiti con `category == "PERSONAS"`. Il contesto viene serializzato come JSON e iniettato nel `user_content` di ogni chiamata LLM che usa il prompt persona-based.

### Meccanismo

1. Una nuova funzione `extract_personas_context(requirements)` in `pipeline.py`:
   - Filtra i requisiti con `category == "PERSONAS"` (case-insensitive)
   - Serializza ciascuno con i campi rilevanti (code, title, description, acceptance_criteria)
   - Restituisce il contesto serializzato e la lista dei requisiti non-PERSONAS

2. Il `user_content` inviato al LLM nel percorso persona-based diventa:
   ```
   ## Contesto — Personas del progetto
   {personas_json}

   ## Requisito da trasformare
   {requisito_json}
   ```

3. I requisiti PERSONAS vengono esclusi dal loop di trasformazione in user stories quando si usa la strategia persona-based (diventano input di contesto, non requisiti da elaborare).

4. La scelta della strategia (AC-based o persona-based) avviene:
   - Nella shell interattiva: domanda ad ogni generazione di user stories
   - Nella CLI batch: argomento `--strategy ac|persona`

### Opzione alternativa scartata: file personas separato

Si è valutata l'opzione di mantenere le personas in un file dedicato (`personas.json`) separato dai requisiti. Scartata perché:
- Introduce un secondo file di input da gestire e mantenere sincronizzato
- Le personas sono già definite come requisiti nel flusso esistente
- Duplicherebbe informazione già presente in `requirements.json`

## Conseguenze

- Modifica di `pipeline.py`: nuova funzione `extract_personas_context()`, parametro `personas_context` in `process_requirement_to_us()`, parametro `strategy` in `run_pipeline()`
- Modifica di `interactive.py`: domanda sulla strategia prima di ogni generazione US
- Modifica di `pipeline_cli.py`: nuovo argomento `--strategy`
- Il prompt `user_stories/persona_based.md` non richiede modifiche (è già progettato per ricevere il doppio input)
- Nessuna modifica ai prompt dei test cases (lo schema JSON delle user stories è identico tra i due approcci)
