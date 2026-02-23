# ADR-001: Decomposizione dei requisiti in user stories per acceptance criterion

**Data**: 2026-02-19
**Stato**: Accettata
**Decisori**: Team TECO_LLM_cli


L'obiettivo è trasformare questi requisiti in test cases tracciabili, completi e pronti per l'esecuzione (manuale o automatizzata). 

## La scelta da compiere

Il passaggio intermedio attraverso le user stories deve produrre test cases consistenti con quanto validato dal business. Tuttavia, le user stories offrono un livello di scomposizione che migliora la qualita e la tracciabilita dei test cases a valle. Questa ADR non discute se usare le user stories (la pipeline le prevede), ma **come decomporle** a partire dal requisito.

Ogni requisito contiene piu acceptance criteria, ciascuno dei quali descrive un aspetto verificabile del comportamento atteso. La scelta chiave e: quale dimensione del requisito deve guidare la generazione delle user stories? L'attore, il criterio di accettazione, o una combinazione dei due?

La regola di decomposizione scelta ha impatto diretto su:

- la **granularita** delle user stories prodotte
- la **tracciabilita** dalla user story al requisito originale
- la **qualita dei test cases** generati nello step successivo
- la **prevedibilita** del volume di output

## Opzioni valutate

### Opzione 1 — Una user story per ogni persona/attore

Ogni attore menzionato nel requisito (es. cliente, operatore, amministratore) genera una user story dedicata.

- **Cardinalita**: un requisito produce N stories, dove N = numero di attori distinti
- **Pro**: il numero di stories e prevedibile; nessuna sovrapposizione tra requisiti
- **Contro**: se il requisito coinvolge un solo attore (caso frequente), si ottiene comunque una sola story che copre tutti gli acceptance criteria. Una story cosi ampia produce test cases generici e poco mirati, riducendo la qualita della copertura a valle. Il numero di stories dipende da *chi* usa il sistema, non da *cosa* il sistema deve fare — ma e il "cosa" che determina la complessita da testare

### Opzione 2 — Una user story per ogni acceptance criterion

Ogni acceptance criterion del requisito genera una user story dedicata.

- **Cardinalita**: un requisito produce N stories, dove N = numero di acceptance criteria
- **Pro**: il numero di stories e prevedibile (basta contare i criteri nel JSON); ogni story e tracciabile a un singolo criterio verificabile; la generazione dei test cases a valle e piu precisa perche ogni story descrive un comportamento specifico
- **Contro**: requisiti con molti criteri producono molte stories; criteri strettamente correlati potrebbero risultare artificialmente separati

### Opzione 3 — Una user story per ogni combinazione persona x scenario

Per ogni incrocio tra attore e acceptance criterion si genera una user story.

- **Cardinalita**: un requisito puo produrre fino a (attori x criteri) stories; requisiti diversi possono generare stories sovrapponibili
- **Pro**: massima copertura teorica
- **Contro**: il numero di stories non e prevedibile (dipende dall'interpretazione del modello); requisiti diversi che menzionano la stessa persona con scenari simili producono duplicati; richiede una fase aggiuntiva di deduplicazione che la pipeline attuale non prevede

## Confronto sintetico

| Criterio | Per persona | Per AC | Per persona x scenario |
|----------|-----------|--------|----------------------|
| Cardinalita | 1:N | 1:N | N:M |
| N prevedibile? | Si | Si | No |
| Sovrapposizioni tra requisiti? | No | No | Si |
| Serve deduplicazione? | No | No | Si |
| N riflette la complessita funzionale? | No | Si | Parzialmente |

## Decisione

**Opzione 2 — Una user story per ogni acceptance criterion.**

Ogni acceptance criterion presente nel requisito genera una user story dedicata. La relazione tra requisiti e user stories e 1:N, dove N corrisponde al numero di acceptance criteria del requisito.

## Motivazioni

1. **Prevedibilita**: il numero di user stories attese e noto prima di chiamare il modello. Basta contare gli acceptance criteria nel JSON di input per sapere quante stories aspettarsi in output. Questo permette di verificare automaticamente la completezza della risposta.

2. **Tracciabilita completa**: si ottiene una catena lineare in cui ogni anello e collegato al precedente:
   - Requisito → Acceptance Criterion → User Story → Test Cases
   - In ogni momento e possibile risalire dal singolo test case al requisito di business originale.

3. **Qualita dei test cases**: lo step successivo della pipeline (generazione test cases) riceve in input user stories focalizzate su un singolo comportamento. Questo produce test cases piu specifici e mirati rispetto a quelli derivati da una story generica che copre tutto il requisito.

4. **Semplicita della pipeline**: non serve alcuno step intermedio di deduplicazione o merge. Ogni requisito e autocontenuto e non genera sovrapposizioni con altri requisiti.

5. **Granularita proporzionale alla complessita**: un requisito con 5 acceptance criteria produce 5 user stories; uno con 2 ne produce 2. Il volume dell'output riflette la complessita effettiva del requisito, non caratteristiche accessorie come il numero di attori.

## Eccezione consentita

Se due acceptance criteria sono strettamente correlati e non testabili separatamente, il modello puo accorparli in una singola user story. In tal caso deve indicare nel campo `notes` quali criteri originali sono stati uniti e perche.

## Conseguenze

- Il prompt che guida il modello (`prompt_user_stories.md`) e stato aggiornato per rendere obbligatoria questa regola di decomposizione
- Requisiti con molti acceptance criteria producono un numero proporzionato di user stories. Questo aumenta il volume dell'output ma migliora la copertura e la testabilita
- Il conteggio delle user stories e verificabile a posteriori: se un requisito ha 3 AC e produce 3 US, il risultato e coerente; se ne produce 1, qualcosa non ha funzionato
- Primo test su REQ-F-001 (3 acceptance criteria): il modello ha generato correttamente 3 user stories distinte, successivamente trasformate in 14 test cases
