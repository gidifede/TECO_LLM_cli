# ADR-001: Strategie di decomposizione dei requisiti in user stories

**Data**: 2026-02-19
**Ultimo aggiornamento**: 2026-02-23
**Stato**: Aggiornata
**Decisori**: Team TECO_LLM_cli


L'obiettivo è trasformare i requisiti di business in test cases tracciabili, completi e pronti per l'esecuzione (manuale o automatizzata).

## La scelta da compiere

Il passaggio intermedio attraverso le user stories deve produrre test cases consistenti con quanto validato dal business. Le user stories offrono un livello di scomposizione che migliora la qualita e la tracciabilita dei test cases a valle. Questa ADR non discute se usare le user stories (la pipeline le prevede), ma **come decomporle** a partire dal requisito.

Ogni requisito contiene piu acceptance criteria e puo coinvolgere piu personas. La scelta chiave e: quale dimensione del requisito deve guidare la generazione delle user stories? L'attore, il criterio di accettazione, o una combinazione dei due?

La regola di decomposizione scelta ha impatto diretto su:

- la **granularita** delle user stories prodotte
- la **tracciabilita** dalla user story al requisito originale
- la **qualita dei test cases** generati nello step successivo
- la **prevedibilita** del volume di output

## Opzioni valutate

### Opzione 1 — Una user story per ogni persona/attore (persona-based)

Ogni attore menzionato nel requisito (es. cliente, operatore, amministratore) genera una user story dedicata. Le personas vengono estratte dai requisiti di categoria PERSONAS e fornite come contesto al modello.

- **Cardinalita**: un requisito produce N stories, dove N = numero di attori coinvolti
- **Pro per i test cases**: i test cases prodotti a valle sono organizzati per prospettiva dell'utente; questo favorisce test di accettazione end-to-end e scenari multicanale (es. lo stesso flusso visto dal cliente web vs dall'operatore di sportello). La copertura dei canali e dei permessi per ruolo e esplicita
- **Contro per i test cases**: se il requisito coinvolge un solo attore (caso frequente), si ottiene una sola story che copre tutti gli acceptance criteria. Una story cosi ampia puo produrre test cases generici e poco mirati. Il numero di stories dipende da *chi* usa il sistema, non da *cosa* il sistema deve fare — ma e il "cosa" che determina la complessita da testare. I test cases rischiano di non coprire uniformemente tutti gli AC se la story e troppo ampia

### Opzione 2 — Una user story per ogni acceptance criterion (AC-based)

Ogni acceptance criterion del requisito genera una user story dedicata.

- **Cardinalita**: un requisito produce N stories, dove N = numero di acceptance criteria
- **Pro per i test cases**: ogni story descrive un singolo comportamento verificabile, quindi i test cases generati a valle sono precisi e mirati. La tracciabilita e lineare: Requisito → AC → User Story → Test Cases. Il numero di test cases prodotti e proporzionale alla complessita funzionale del requisito
- **Contro per i test cases**: requisiti con molti criteri producono molte stories e di conseguenza molti test cases; criteri strettamente correlati, se separati artificialmente, possono generare test cases ridondanti o con setup duplicato

### Opzione 3 — Una user story per ogni combinazione persona x scenario

Per ogni incrocio tra attore e acceptance criterion si genera una user story.

- **Cardinalita**: un requisito puo produrre fino a (attori x criteri) stories; requisiti diversi possono generare stories sovrapponibili
- **Pro**: massima copertura teorica
- **Contro**: il numero di stories e test cases non e prevedibile (dipende dall'interpretazione del modello); requisiti diversi che menzionano la stessa persona con scenari simili producono duplicati; richiede una fase aggiuntiva di deduplicazione che la pipeline attuale non prevede

## Confronto sintetico

| Criterio | Per persona | Per AC | Per persona x scenario |
|----------|-----------|--------|----------------------|
| Cardinalita | 1:N | 1:N | N:M |
| N prevedibile? | Si | Si | No |
| Sovrapposizioni tra requisiti? | No | No | Si |
| Serve deduplicazione? | No | No | Si |
| N riflette la complessita funzionale? | No | Si | Parzialmente |
| TC mirati per singolo comportamento? | Parzialmente | Si | Si |
| TC coprono prospettiva utente/canale? | Si | Parzialmente | Si |

## Decisione

**La CLI supporta entrambe le strategie — AC-based (opzione 2) e persona-based (opzione 1) — selezionabili dall'utente ad ogni generazione.**

Le due strategie producono user stories con caratteristiche complementari, che si traducono in test cases con punti di forza diversi. Invece di sceglierne una sola, la pipeline permette di usarle entrambe per confrontare i risultati e valutare quale approccio produce test cases piu adeguati al contesto del progetto.

- **AC-based** (`--strategy ac`, default): ogni acceptance criterion genera una user story. Produce test cases granulari e mirati al singolo comportamento.
- **Persona-based** (`--strategy persona`): ogni persona coinvolta nel requisito genera una user story. Produce test cases organizzati per prospettiva dell'utente e canale di interazione.

Le user stories persona-based vengono salvate in una directory dedicata (`user_stories_persona/`) per distinguerle da quelle AC-based (`user_stories/`).

## Motivazioni

### Perche mantenere AC-based come default

1. **Prevedibilita**: il numero di user stories attese e noto prima di chiamare il modello. Basta contare gli acceptance criteria nel JSON di input per sapere quante stories aspettarsi in output. Questo permette di verificare automaticamente la completezza della risposta.

2. **Tracciabilita completa**: si ottiene una catena lineare in cui ogni anello e collegato al precedente:
   - Requisito → Acceptance Criterion → User Story → Test Cases
   - In ogni momento e possibile risalire dal singolo test case al requisito di business originale.

3. **Qualita dei test cases**: lo step successivo della pipeline (generazione test cases) riceve in input user stories focalizzate su un singolo comportamento. Questo produce test cases piu specifici e mirati rispetto a quelli derivati da una story generica che copre tutto il requisito.

4. **Semplicita della pipeline**: non serve alcuno step intermedio di deduplicazione o merge. Ogni requisito e autocontenuto e non genera sovrapposizioni con altri requisiti.

5. **Granularita proporzionale alla complessita**: un requisito con 5 acceptance criteria produce 5 user stories; uno con 2 ne produce 2. Il volume dell'output riflette la complessita effettiva del requisito.

### Perche supportare anche persona-based

1. **Copertura multicanale**: in progetti con piu personas che interagiscono sugli stessi flussi (es. cliente digitale vs operatore di sportello), la decomposizione per persona evidenzia differenze di canale, permessi e comportamento atteso che la strategia AC-based puo non rendere esplicite.

2. **Test di accettazione end-to-end**: i test cases derivati da user stories persona-based sono naturalmente organizzati come scenari end-to-end dal punto di vista dell'utente, utili per test di accettazione e UAT.

3. **Confronto tra approcci**: avere entrambe le strategie permette di generare test cases da due prospettive diverse sullo stesso requisito e confrontarne qualita, copertura e ridondanza — anche tramite la funzione di valutazione coerenza gia presente nella pipeline.

## Eccezione consentita (AC-based)

Se due acceptance criteria sono strettamente correlati e non testabili separatamente, il modello puo accorparli in una singola user story. In tal caso deve indicare nel campo `notes` quali criteri originali sono stati uniti e perche.

## Eccezione consentita (persona-based)

Se il requisito non coinvolge nessuna delle personas fornite nel contesto (es. requisiti puramente tecnici), il modello deve usare la persona convenzionale "Sistema" e segnalarlo nel campo `assumptions`.

## Conseguenze

- Il prompt `user_stories/ac_based.md` implementa la strategia AC-based
- Il prompt `user_stories/persona_based.md` implementa la strategia persona-based; riceve come contesto le personas estratte dai requisiti di categoria PERSONAS
- La scelta della strategia e disponibile sia nel menu interattivo (`teco-interactive`) sia come flag CLI (`teco-pipeline --strategy ac|persona`)
- Le user stories persona-based vengono salvate in `percorso_indiretto/persona_based/user_stories/`, quelle AC-based in `percorso_indiretto/ac_based/user_stories/`
- I requisiti di categoria PERSONAS vengono automaticamente esclusi dal loop di trasformazione quando si usa la strategia persona-based (servono solo come contesto)
- Primo test AC-based su REQ-F-001 (3 acceptance criteria): il modello ha generato correttamente 3 user stories distinte, successivamente trasformate in 14 test cases

## Aggiornamento — Rimozione strategia AC-based (2026-02-23)

A seguito delle valutazioni di coerenza condotte su 5 requisiti (REQ-F-001, REQ-F-004, REQ-F-007, REQ-F-008, REQ-F-009), la strategia AC-based è stata rimossa dalla pipeline.

**Risultati:**
- Percorso diretto: score medio ~73/100
- Percorso indiretto persona-based: score medio ~52/100
- Percorso indiretto AC-based: score medio ~4/100 (0 in 3 casi su 4)

**Motivazione:** Il percorso AC-based presenta un difetto strutturale: la catena Requisito → User Stories (1 US per AC, ciascuna con AC riscritti) → Test Cases produce `traced_criteria` che non corrispondono agli AC del requisito originale. Il valutatore rileva un disallineamento sistematico. Inoltre, la decomposizione 1 US per AC amplifica il drift informativo (15-23 TC con molte informazioni inventate vs 5-11 del percorso diretto).

**Conseguenze operative:**
- Il prompt `user_stories/ac_based.md` resta su disco ma non è più referenziato dal codice
- La pipeline supporta solo la strategia persona-based (applicata automaticamente, senza menu di scelta)
- Le directory di output `percorso_indiretto/ac_based/` non sono più create dalla pipeline
- Il menu di scelta strategia (`_ask_us_strategy`) è stato eliminato
- La valutazione di coerenza confronta solo 2 set: `direct` e `indirect_persona`
