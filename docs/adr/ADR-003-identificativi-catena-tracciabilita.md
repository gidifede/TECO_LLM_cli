# ADR-003: Convenzione degli identificativi nella catena di tracciabilita

**Data**: 2026-02-19
**Stato**: Accettata
**Decisori**: Team TECO_LLM_cli

## Contesto

La pipeline TECO_LLM_cli produce tre livelli di artefatti collegati:

1. **Requisiti** (input, codice fisso es. `REQ-F-001`)
2. **User stories** derivate da ogni requisito
3. **Test cases** derivati dalle user stories oppure direttamente dai requisiti

Ogni livello deve avere un identificativo univoco e la catena deve essere tracciabile: dato un test case, si deve poter risalire alla user story e al requisito d'origine.

### Convenzione attuale

La convenzione attuale incorpora l'intero ID del livello padre come prefisso:

```
REQ-F-001                          → requisito (input)
US-REQ-F-001-01                    → user story 1
TC-US-REQ-F-001-01-01              → test case 1 della user story 1
TC-REQ-F-001-01                    → test case diretto 1
```

### Problemi riscontrati

1. **Lunghezza eccessiva**: `TC-US-REQ-F-001-01-01` e 22 caratteri con 7 segmenti separati da trattino. La leggibilita degrada rapidamente.
2. **Ridondanza a cascata**: ogni livello re-incorpora l'ID completo del padre. `TC-US-REQ-F-001-01-01` contiene `US-REQ-F-001-01` che contiene `REQ-F-001` — lo stesso codice requisito appare 3 volte nell'ID del test case.
3. **Ambiguita visiva**: con tutti i segmenti separati da trattino, e difficile distinguere dove finisce il codice requisito e dove iniziano i suffissi gerarchici (es. `REQ-F-001-01` potrebbe sembrare un requisito con sotto-codice).
4. **Incoerenza tra flussi**: il flusso US→TC produce `TC-US-REQ-F-001-01-01` mentre il flusso diretto produce `TC-REQ-F-001-01` — strutture diverse per artefatti dello stesso tipo.

## Opzioni valutate

### Opzione A — Notazione a punto (gerarchica)

Il codice requisito resta l'ancora. I livelli successivi sono suffissi brevi separati da punto.

```
REQ-F-001                          → requisito
REQ-F-001.US01                     → user story 1
REQ-F-001.US02                     → user story 2
REQ-F-001.US01.TC01                → test case 1 della user story 1
REQ-F-001.US01.TC02                → test case 2 della user story 1
REQ-F-001.TC01                     → test case diretto 1
```

- Il requisito e sempre in testa, una sola volta
- La profondita e visivamente immediata: 0 punti = requisito, 1 punto = US o TC diretto, 2 punti = TC da US
- La differenza tra TC diretto (`REQ-F-001.TC01`) e TC da US (`REQ-F-001.US01.TC01`) e evidente dalla struttura
- Compatibile con nomi file (il punto e valido su tutti gli OS)

### Opzione B — Trattino con suffissi corti

Stessa logica dell'opzione A ma con trattino al posto del punto.

```
REQ-F-001                          → requisito
REQ-F-001-US01                     → user story 1
REQ-F-001-US01-TC01                → test case 1 della user story 1
REQ-F-001-TC01                     → test case diretto 1
```

- Compatibilita massima (solo trattini)
- Meno distinguibile visivamente: `REQ-F-001-US01-TC01` ha 5 segmenti tutti separati da trattino, il confine tra codice requisito e suffissi non e immediato

### Opzione C — ID indipendenti con cross-reference

ID corti e autonomi per ogni livello. La tracciabilita e garantita da campi espliciti nel JSON.

```
REQ-F-001                          → requisito
US-F-001-01                        → user story (campo "requirement_id": "REQ-F-001")
TC-F-001-01-01                     → test case  (campo "story_id": "US-F-001-01")
TC-F-001-01                        → test case diretto (campo "requirement_id": "REQ-F-001")
```

- ID piu corti in assoluto
- Il prefisso (`US-`, `TC-`) rende il tipo leggibile al volo
- L'ID da solo non racconta la gerarchia completa — serve consultare il JSON per risalire la catena

## Confronto

| Criterio | Attuale | A (punto) | B (trattino) | C (ID indipendenti) |
|---|---|---|---|---|
| Esempio TC da US | `TC-US-REQ-F-001-01-01` | `REQ-F-001.US01.TC01` | `REQ-F-001-US01-TC01` | `TC-F-001-01-01` |
| Lunghezza (char) | 22 | 20 | 20 | 15 |
| Requisito leggibile nell'ID | Si (ripetuto) | Si (una volta) | Si (una volta) | Parziale |
| Gerarchia leggibile nell'ID | Si ma confusa | Si (punti = livelli) | Parziale | No (serve JSON) |
| Tipo artefatto nell'ID | Si (prefisso TC-US-) | No (serve contare i punti) | No (serve contesto) | Si (prefisso TC-) |
| Separazione visiva dei livelli | Bassa (tutti trattini) | Alta (punti vs trattini) | Bassa (tutti trattini) | N/A |
| Coerenza tra flusso US→TC e diretto | Bassa | Alta | Alta | Alta |
| Compatibilita naming file | OK | OK | OK | OK |

## Decisione

**Opzione A — Notazione a punto (gerarchica).**

### Formato degli identificativi

| Artefatto | Formato | Esempio |
|---|---|---|
| Requisito | `REQ-{cat}-{NNN}` (input, invariato) | `REQ-F-001` |
| User story | `{req_code}.US{NN}` | `REQ-F-001.US01` |
| Test case (da US) | `{story_id}.TC{NN}` | `REQ-F-001.US01.TC01` |
| Test case (diretto) | `{req_code}.TC{NN}` | `REQ-F-001.TC01` |

Dove `NN` e un progressivo a due cifre (01, 02, ...).

## Motivazioni

1. **Leggibilita**: il punto introduce una separazione visiva netta tra livelli gerarchici, che i trattini non offrono. `REQ-F-001.US01.TC01` si legge immediatamente come "requisito F-001, user story 01, test case 01".

2. **Non ridondanza**: il codice requisito appare una sola volta, in testa. Non c'e nidificazione di prefissi.

3. **Profondita immediata**: il numero di punti indica il livello — 0 punti = requisito, 1 punto = user story o TC diretto, 2 punti = TC da user story.

4. **Coerenza tra flussi**: la differenza tra TC diretto (`REQ-F-001.TC01`) e TC da US (`REQ-F-001.US01.TC01`) e strutturale e autoesplicativa — stessa convenzione, diversa profondita.

5. **Compatibilita**: il punto e un carattere valido nei nomi file su tutti gli OS e non causa conflitti con i formati JSON o CSV usati dalla pipeline.

## Conseguenze

- Aggiornare i tre prompt (`user_stories/ac_based.md`, `test_cases/from_user_stories.md`, `test_cases/from_requirements.md`) con la nuova convenzione
- Aggiornare il campo `test_id` nella tabella descrizione campi di entrambi i prompt TC
- Aggiornare il campo `story_id` nella tabella del prompt US
- Aggiornare gli esempi JSON nei prompt
- Il codice Python (`pipeline.py`, `interactive.py`) non usa gli ID internamente — non servono modifiche al codice, perche gli ID sono generati dal modello LLM in base al prompt
- I file di output gia generati con la vecchia convenzione non vengono rinominati retroattivamente
