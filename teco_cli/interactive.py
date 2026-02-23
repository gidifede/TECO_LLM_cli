"""Shell interattiva per la pipeline requisiti → user stories → test cases."""

import argparse
import json
import shutil
import sys
from pathlib import Path

from .config import AzureOpenAIConfig, load_config
from .paths import OutputDirs, PromptFiles, TC_CHAINS
from .pipeline import (
    evaluate_test_cases,
    extract_personas_context,
    process_requirement_to_tc_direct,
    process_requirement_to_us,
    process_us_to_tc,
)


# ---------------------------------------------------------------------------
# Colori ANSI (varianti bright per sfondo nero)
# ---------------------------------------------------------------------------


class _C:
    """Codici ANSI per output colorato nel terminale."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"


# Livelli di log
_LOG_INFO = "info"
_LOG_VERBOSE = "verbose"


def _vlog(msg: str, log_level: str) -> None:
    """Stampa un messaggio solo in modalita verbose."""
    if log_level == _LOG_VERBOSE:
        print(f"  {_C.DIM}{msg}{_C.RESET}")


# Costanti per identificare il tipo di generazione
_MODE_FULL = "full"
_MODE_US_ONLY = "us_only"
_MODE_TC_FROM_US = "tc_from_us"
_MODE_TC_DIRECT = "tc_direct"


# ---------------------------------------------------------------------------
# Helper di input
# ---------------------------------------------------------------------------


def _ask_choice(
    prompt: str,
    options: list[str],
    separators: dict[int, str] | None = None,
) -> int:
    """Mostra un menu numerato e restituisce l'indice scelto (0-based).

    ``separators`` e un dizionario opzionale {indice: testo} che stampa un
    separatore visivo *prima* dell'opzione a quell'indice.
    Ripete la domanda finche l'utente non inserisce un valore valido.
    """
    print(f"\n{_C.CYAN}{prompt}{_C.RESET}")
    for i, opt in enumerate(options):
        if separators and i in separators:
            sep_text = separators[i]
            if sep_text:
                print(f"\n  {_C.DIM}── {sep_text} ──{_C.RESET}")
            else:
                print()
        print(f"  {_C.WHITE}{i + 1}.{_C.RESET} {opt}")

    while True:
        raw = input(f"{_C.YELLOW}› {_C.RESET}").strip()
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        print(
            f"  {_C.RED}Scelta non valida. "
            f"Inserisci un numero tra 1 e {len(options)}.{_C.RESET}"
        )


def _ask_text(prompt: str) -> str:
    """Chiede un testo libero all'utente (non vuoto)."""
    while True:
        raw = input(f"{_C.CYAN}{prompt}:{_C.RESET} ").strip()
        if raw:
            return raw
        print(f"  {_C.RED}Input non valido, riprova.{_C.RESET}")


def _ask_us_strategy() -> str | None:
    """Chiede la strategia di decomposizione user stories.

    Restituisce ``"ac"``, ``"persona"``, ``"both"`` oppure ``None`` se
    l'utente sceglie *Indietro*.
    """
    choice = _ask_choice(
        "Come generare le user stories?",
        [
            "Per criterio di accettazione",
            "Per persona",
            "Entrambe le strategie",
            "Indietro",
        ],
    )
    if choice == 3:
        return None
    return ("ac", "persona", "both")[choice]


# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------


DEFAULT_REQUIREMENTS = "input_test/requirements.json"
DEFAULT_OUTPUT_DIR = "./output_test"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="teco-interactive",
        description="Shell interattiva per la pipeline TECO (user stories / test cases).",
    )

    parser.add_argument(
        "--requirements",
        default=DEFAULT_REQUIREMENTS,
        help=f"Path al file requirements.json (default: {DEFAULT_REQUIREMENTS}).",
    )
    parser.add_argument(
        "--prompts-dir",
        default=None,
        help=(
            "Directory contenente i prompt (user_stories/, test_cases/, evaluation/). "
            "Default: teco_cli/prompts/ nel progetto."
        ),
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Path a un file .env custom.",
    )
    parser.add_argument(
        "--deployment",
        default=None,
        help="Nome del deployment Azure OpenAI (default dal .env).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Temperatura per la generazione (default: 0.7).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=16384,
        help="Max token nella risposta (default: 16384).",
    )

    args = parser.parse_args(argv)

    # Output dir fisso
    args.output_dir = DEFAULT_OUTPUT_DIR

    if args.prompts_dir is None:
        args.prompts_dir = str(Path(__file__).resolve().parent / "prompts")

    if not Path(args.prompts_dir).is_dir():
        parser.error(f"Directory prompts non trovata: {args.prompts_dir}")

    return args


# ---------------------------------------------------------------------------
# Flusso interattivo — sotto-funzioni
# ---------------------------------------------------------------------------


def _handle_tc_result(
    tc_result: dict,
    tc_dir: Path,
    errors: list[dict],
    all_test_cases: list,
    label: str,
    log_level: str = _LOG_VERBOSE,
) -> None:
    """Gestisce il risultato di una chiamata process_us_to_tc."""
    if tc_result["status"] == "rejected":
        print(f"  {_C.YELLOW}[step 2] REJECTED dal modello:{_C.RESET}")
        for r in tc_result["reasons"]:
            print(f"    - {r}")
        errors.append({
            "code": label, "step": "test_cases",
            "error": f"Rejected: {'; '.join(tc_result['reasons'])}",
        })
    elif tc_result["status"] == "error":
        print(f"  {_C.RED}[step 2] ERRORE: {tc_result['error']}{_C.RESET}", file=sys.stderr)
        if tc_result.get("raw_text"):
            raw_file = tc_dir / f"{label}_test_cases_RAW.txt"
            raw_file.write_text(tc_result["raw_text"], encoding="utf-8")
        errors.append({
            "code": label, "step": "test_cases", "error": tc_result["error"],
        })
    else:
        test_cases = tc_result["test_cases"]
        tc_file = tc_dir / f"{label}_test_cases.json"
        tc_file.write_text(
            json.dumps(test_cases, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if isinstance(test_cases, list):
            all_test_cases.extend(test_cases)
        else:
            all_test_cases.append(test_cases)

        tc_count = sum(
            len(item.get("test_cases", []))
            for item in (test_cases if isinstance(test_cases, list) else [test_cases])
        )
        print(f"  {_C.GREEN}[step 2] OK - {tc_count} test cases generati{_C.RESET}")
        _vlog(f"File scritto: {tc_file} ({tc_file.stat().st_size} bytes)", log_level)


def _handle_direct_tc_result(
    result: dict,
    direct_dir: Path,
    code: str,
    errors: list[dict],
    skipped: list[dict],
    rejected: list[dict],
    all_test_cases_direct: list,
    log_level: str = _LOG_VERBOSE,
) -> None:
    """Gestisce il risultato di una chiamata process_requirement_to_tc_direct."""
    if result["status"] == "skipped":
        print(f"  {_C.YELLOW}[validazione] SKIP - problemi sintattici:{_C.RESET}")
        for p in result["problems"]:
            print(f"    - {p}")
        skipped.append({
            "requirement_id": code,
            "problems": result["problems"],
        })
    elif result["status"] == "rejected":
        print(f"  {_C.YELLOW}[direct] REJECTED dal modello:{_C.RESET}")
        for r in result["reasons"]:
            print(f"    - {r}")
        rejected.append({
            "requirement_id": code,
            "reasons": result["reasons"],
        })
    elif result["status"] == "error":
        print(
            f"  {_C.RED}[direct] ERRORE: {result['error']}{_C.RESET}",
            file=sys.stderr,
        )
        if result.get("raw_text"):
            raw_file = direct_dir / f"{code}_test_cases_RAW.txt"
            raw_file.write_text(result["raw_text"], encoding="utf-8")
        errors.append({
            "code": code, "step": "direct_tc", "error": result["error"],
        })
    else:
        test_cases = result["test_cases"]
        tc_file = direct_dir / f"{code}_test_cases.json"
        tc_file.write_text(
            json.dumps(test_cases, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if isinstance(test_cases, list):
            all_test_cases_direct.extend(test_cases)
        else:
            all_test_cases_direct.append(test_cases)

        tc_count = len(test_cases) if isinstance(test_cases, list) else 1
        print(f"  {_C.GREEN}[direct] OK - {tc_count} test cases generati{_C.RESET}")
        _vlog(f"File scritto: {tc_file} ({tc_file.stat().st_size} bytes)", log_level)


def _ask_requirements_file(default: Path) -> Path | None:
    """Chiede all'utente quale file requirements.json usare.

    Restituisce None se l'utente sceglie di tornare indietro.
    """
    choice = _ask_choice(
        "File requisiti:",
        [
            f"Usa {_C.DIM}{default}{_C.RESET}",
            "Scegli un altro file",
            "Indietro",
        ],
    )
    if choice == 2:
        return None
    if choice == 0:
        req_path = default
    else:
        while True:
            custom = _ask_text("Inserisci il path al file requirements.json")
            req_path = Path(custom)
            if req_path.is_file():
                break
            print(f"  {_C.RED}File non trovato: {req_path}{_C.RESET}")

    if not req_path.is_file():
        print(f"{_C.RED}File requisiti non trovato: {req_path}{_C.RESET}", file=sys.stderr)
        return None
    return req_path


def _ask_scope(
    requirements: list[dict],
) -> tuple[list[dict], str | None] | None:
    """Chiede l'ambito dei requisiti (tutti o specifico).

    Restituisce (selected_reqs, single_req_code) oppure None per tornare indietro.
    single_req_code e None se l'utente sceglie "tutti".
    """
    scope = _ask_choice(
        "Quali requisiti elaborare?",
        [
            f"Tutti ({len(requirements)})",
            "Uno specifico",
            "Indietro",
        ],
    )
    if scope == 2:
        return None

    if scope == 1:
        single_req_code = _ask_text(
            "\nInserisci il codice del requisito (es. REQ-F-001)"
        )
        selected = [r for r in requirements if r.get("code") == single_req_code]
        if not selected:
            print(f"\n  {_C.RED}Requisito '{single_req_code}' non trovato.{_C.RESET}", file=sys.stderr)
            return None
        return selected, single_req_code

    return requirements, None


def _load_existing_us(us_dir: Path) -> dict[str, list[dict]]:
    """Carica le user stories esistenti dalla directory di output, raggruppate per requisito."""
    us_by_req: dict[str, list[dict]] = {}
    for f in sorted(us_dir.glob("*_user_stories.json")):
        # Nome file: REQ-F-001_user_stories.json → codice = REQ-F-001
        req_code = f.name.replace("_user_stories.json", "")
        try:
            stories = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(stories, list) and stories:
                us_by_req[req_code] = stories
        except (json.JSONDecodeError, OSError):
            continue
    return us_by_req


def _generate_us(
    selected: list[dict],
    system_prompt_us: str,
    config: AzureOpenAIConfig,
    args: argparse.Namespace,
    us_dir: Path,
    personas_context: str | None = None,
    log_level: str = _LOG_VERBOSE,
) -> tuple[dict[str, list[dict]], list[dict], list[dict], list[dict], list[dict]]:
    """Genera user stories per i requisiti selezionati.

    Restituisce (us_by_req, all_user_stories_flat, skipped, rejected, errors).
    """
    us_by_req: dict[str, list[dict]] = {}
    all_user_stories: list[dict] = []
    skipped: list[dict] = []
    rejected: list[dict] = []
    errors: list[dict] = []
    total = len(selected)
    verbose = log_level == _LOG_VERBOSE

    _vlog(f"Directory output US: {us_dir}", log_level)
    _vlog(f"Prompt di sistema: {len(system_prompt_us)} char", log_level)
    if personas_context:
        _vlog(f"Contesto personas: {len(personas_context)} char", log_level)

    for i, req in enumerate(selected, 1):
        code = req.get("code", f"REQ-{i}")
        print(f"\n[pipeline] [{i}/{total}] Elaborazione {code}...")
        _vlog(
            f"Requisito {code}: {len(req.get('acceptance_criteria', []))} AC, "
            f"descrizione {len(req.get('description', ''))} char",
            log_level,
        )

        result = process_requirement_to_us(
            req=req,
            system_prompt=system_prompt_us,
            config=config,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            verbose=verbose,
            personas_context=personas_context,
        )

        if result["status"] == "skipped":
            print(f"  {_C.YELLOW}[validazione] SKIP - problemi sintattici:{_C.RESET}")
            for p in result["problems"]:
                print(f"    - {p}")
            skipped.append({"requirement_id": code, "problems": result["problems"]})
            continue

        if result["status"] == "rejected":
            print(f"  {_C.YELLOW}[step 1] REJECTED dal modello:{_C.RESET}")
            for r in result["reasons"]:
                print(f"    - {r}")
            raw_resp = result["raw_response"]
            rejected.append({
                "requirement_id": raw_resp.get("requirement_id", code),
                "reasons": result["reasons"],
            })
            rej_file = us_dir / f"{code}_REJECTED.json"
            rej_file.write_text(
                json.dumps(raw_resp, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            continue

        if result["status"] == "error":
            print(f"  {_C.RED}[step 1] ERRORE: {result['error']}{_C.RESET}", file=sys.stderr)
            if result.get("raw_text"):
                raw_file = us_dir / f"{code}_user_stories_RAW.txt"
                raw_file.write_text(result["raw_text"], encoding="utf-8")
            errors.append({"code": code, "step": "user_stories", "error": result["error"]})
            continue

        # OK
        us_list = result["user_stories"]
        if not isinstance(us_list, list):
            us_list = [us_list]
        us_file = us_dir / f"{code}_user_stories.json"
        us_file.write_text(
            json.dumps(us_list, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        us_by_req[code] = us_list
        all_user_stories.extend(us_list)
        print(f"  {_C.GREEN}[step 1] OK - {len(us_list)} user stories generate{_C.RESET}")
        _vlog(f"File scritto: {us_file} ({us_file.stat().st_size} bytes)", log_level)

    return us_by_req, all_user_stories, skipped, rejected, errors


def _generate_tc(
    us_by_req: dict[str, list[dict]],
    all_user_stories: list[dict],
    system_prompt_tc: str,
    config: AzureOpenAIConfig,
    args: argparse.Namespace,
    tc_dir: Path,
    errors: list[dict],
    log_level: str = _LOG_VERBOSE,
) -> list | None:
    """Genera test cases. Chiede all'utente l'ambito, poi elabora per-requisito.

    Restituisce la lista aggregata di test cases, o None se l'utente torna indietro.
    """
    all_test_cases: list = []
    verbose = log_level == _LOG_VERBOSE

    _vlog(f"Directory output TC: {tc_dir}", log_level)
    _vlog(f"Prompt di sistema: {len(system_prompt_tc)} char", log_level)

    tc_scope = _ask_choice(
        "Quali user stories elaborare?",
        [
            f"Tutte ({len(all_user_stories)})",
            "Una specifica",
            "Indietro",
        ],
    )

    if tc_scope == 2:
        return None

    if tc_scope == 1:
        # Mostra US disponibili
        print(f"\n{_C.DIM}User stories disponibili:{_C.RESET}")
        for idx, us in enumerate(all_user_stories, 1):
            us_id = us.get("story_id", us.get("id", f"US-{idx}"))
            us_title = us.get("title", us.get("name", "N/A"))
            print(f"  {idx}. {us_id} - {us_title}")

        us_code = _ask_text(
            "\nInserisci l'ID della user story (es. REQ-F-001.US01)"
        )
        tc_stories = [
            us for us in all_user_stories
            if us.get("story_id") == us_code or us.get("id") == us_code
        ]
        if not tc_stories:
            print(f"\n  {_C.RED}User story '{us_code}' non trovata.{_C.RESET}", file=sys.stderr)
            return None

        print(f"\n[pipeline] Generazione test cases per 1 user story...")
        tc_result = process_us_to_tc(
            user_stories=tc_stories,
            system_prompt=system_prompt_tc,
            config=config,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            verbose=verbose,
        )
        _handle_tc_result(tc_result, tc_dir, errors, all_test_cases, us_code, log_level)

    else:
        # Tutte le US: iteriamo per-requisito
        tc_total = len(us_by_req)
        for tc_i, (req_code, req_us) in enumerate(us_by_req.items(), 1):
            print(
                f"\n[pipeline] [{tc_i}/{tc_total}] "
                f"Test cases per {req_code} ({len(req_us)} user stories)..."
            )
            _vlog(f"{req_code}: {len(req_us)} user stories in input", log_level)
            tc_result = process_us_to_tc(
                user_stories=req_us,
                system_prompt=system_prompt_tc,
                config=config,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                verbose=verbose,
            )
            _handle_tc_result(tc_result, tc_dir, errors, all_test_cases, req_code, log_level)

    return all_test_cases


def _clean_output(out_path: Path) -> None:
    """Rimuove tutti i file e le sottodirectory dalla directory di output."""
    out_path = out_path.resolve()

    # Sottodirectory note della pipeline
    subdirs = [str(d) for d in OutputDirs.all_subdirs()]

    # Conta file per il report
    file_count = 0
    dir_count = 0

    # Elenca cosa verra rimosso
    items_in_root = [f for f in out_path.iterdir() if f.is_file()]
    existing_subdirs = [out_path / d for d in subdirs if (out_path / d).is_dir()]

    for f in items_in_root:
        file_count += 1
    for d in existing_subdirs:
        for f in d.rglob("*"):
            if f.is_file():
                file_count += 1
        dir_count += 1

    if file_count == 0 and dir_count == 0:
        print(f"\n  {_C.DIM}La directory di output e gia vuota: {out_path}{_C.RESET}")
        return

    # Mostra riepilogo
    print(f"\n{_C.YELLOW}Contenuto di {out_path}:{_C.RESET}")
    for f in sorted(items_in_root):
        print(f"  {f.name}")
    for d in existing_subdirs:
        sub_files = list(d.rglob("*"))
        sub_file_count = sum(1 for f in sub_files if f.is_file())
        print(f"  {d.name}/ ({sub_file_count} file)")

    print(
        f"\nTotale: {file_count} file in {dir_count} sottodirectory "
        f"+ {len(items_in_root)} file nella root"
    )

    confirm = _ask_choice(
        "Confermi la cancellazione?",
        ["Si, cancella tutto", "No, annulla"],
    )
    if confirm == 1:
        print(f"  {_C.DIM}Operazione annullata.{_C.RESET}")
        return

    # Rimuovi sottodirectory (ricrea vuote)
    for d in existing_subdirs:
        shutil.rmtree(d)
        d.mkdir()

    # Rimuovi file nella root di output
    for f in items_in_root:
        f.unlink()

    print(f"\n  {_C.GREEN}Pulizia completata: {file_count} file rimossi.{_C.RESET}")


def _evaluate_coherence(
    args: argparse.Namespace,
    config: AzureOpenAIConfig,
    out_path: Path,
    prompts_path: Path,
    log_level: str = _LOG_VERBOSE,
) -> None:
    """Valuta la coerenza tra test cases (2-3 catene) e requisito originale."""

    # Carica prompt di valutazione
    eval_prompt_file = prompts_path / PromptFiles.EVAL_COHERENCE
    if not eval_prompt_file.is_file():
        print(
            f"  {_C.RED}Prompt di valutazione non trovato: {eval_prompt_file}{_C.RESET}",
            file=sys.stderr,
        )
        return
    system_prompt_eval = eval_prompt_file.read_text(encoding="utf-8")

    # Chiedi file requirements
    req_path = _ask_requirements_file(Path(args.requirements))
    if req_path is None:
        return
    requirements: list[dict] = json.loads(req_path.read_text(encoding="utf-8"))
    print(f"Requisiti caricati: {len(requirements)}")

    # Chiedi codice requisito
    req_code = _ask_text(
        "\nInserisci il codice del requisito da valutare (es. REQ-F-001)"
    )
    requirement = next(
        (r for r in requirements if r.get("code") == req_code), None
    )
    if requirement is None:
        print(f"\n  {_C.RED}Requisito '{req_code}' non trovato nel file.{_C.RESET}", file=sys.stderr)
        return

    # --- 4a. Rilevamento catene disponibili ---
    available_chains: dict[str, list[Path]] = {}
    for key, chain in TC_CHAINS.items():
        tc_dir = out_path / chain.tc_dir
        if not tc_dir.is_dir():
            continue
        _vlog(f"Scansione {chain.label}: directory {tc_dir}", log_level)
        files: list[Path] = []
        if key == "direct":
            # TC diretti: {REQ}_test_cases.json
            main_file = tc_dir / f"{req_code}_test_cases.json"
            if main_file.is_file():
                files.append(main_file)
        else:
            # TC indiretti: {REQ}_test_cases.json + {REQ}.US*_test_cases.json
            main_file = tc_dir / f"{req_code}_test_cases.json"
            if main_file.is_file():
                files.append(main_file)
            files.extend(sorted(tc_dir.glob(f"{req_code}.US*_test_cases.json")))
        _vlog(f"  Trovati {len(files)} file", log_level)
        if files:
            available_chains[key] = files

    # --- Verifica minimo 2 catene ---
    if len(available_chains) < 2:
        present = [TC_CHAINS[k].label for k in available_chains]
        missing = [
            chain.label for key, chain in TC_CHAINS.items()
            if key not in available_chains
        ]
        print(f"\n  {_C.RED}Catene TC trovate per {req_code}: "
              f"{len(available_chains)}/3{_C.RESET}", file=sys.stderr)
        if present:
            for lbl in present:
                print(f"    {_C.GREEN}+{_C.RESET} {lbl}")
        for lbl in missing:
            print(f"    {_C.RED}-{_C.RESET} {lbl}")
        print(
            f"\n  {_C.YELLOW}La valutazione richiede almeno 2 set di test cases. "
            f"Genera prima i set mancanti per {req_code}.{_C.RESET}",
            file=sys.stderr,
        )
        return

    # --- 4b. Scelta utente ---
    selected_keys: list[str]
    if len(available_chains) == 2:
        # Solo 2 catene: procede direttamente
        selected_keys = list(available_chains.keys())
        labels_str = " vs ".join(TC_CHAINS[k].label for k in selected_keys)
        print(f"\n  {_C.DIM}2 catene rilevate: {labels_str}{_C.RESET}")
    else:
        # 3 catene: menu di scelta
        chain_keys = list(available_chains.keys())
        # Genera combinazioni a 2
        pairs: list[tuple[str, str]] = []
        for i in range(len(chain_keys)):
            for j in range(i + 1, len(chain_keys)):
                pairs.append((chain_keys[i], chain_keys[j]))

        options = [
            f"Tutti e 3 ({', '.join(TC_CHAINS[k].label for k in chain_keys)})"
        ]
        for a, b in pairs:
            options.append(f"{TC_CHAINS[a].label} vs {TC_CHAINS[b].label}")
        options.append("Indietro")

        choice = _ask_choice(
            f"3 catene TC rilevate per {req_code}. Quali confrontare?",
            options,
        )

        if choice == len(options) - 1:
            return

        if choice == 0:
            selected_keys = chain_keys
        else:
            pair = pairs[choice - 1]
            selected_keys = list(pair)

    # --- 4c. Caricamento TC unificato ---
    tc_sets: dict[str, list[dict]] = {}
    chain_metadata: dict[str, dict] = {}
    file_details: dict[str, list[tuple[str, int]]] = {}

    for key in selected_keys:
        chain = TC_CHAINS[key]
        chain_metadata[key] = {"label": chain.label, "naming": chain.naming}
        files = available_chains[key]
        tc_list: list[dict] = []
        seen: set[str] = set()
        details: list[tuple[str, int]] = []

        for fpath in files:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = [data]
            count_before = len(tc_list)
            if key == "direct":
                # Formato flat
                for tc in data:
                    tid = tc.get("test_id", "")
                    if tid not in seen:
                        seen.add(tid)
                        tc_list.append(tc)
            else:
                # Formato annidato (possibile wrapper test_cases)
                for item in data:
                    if isinstance(item, dict) and "test_cases" in item:
                        tcs = item["test_cases"]
                    else:
                        tcs = [item]
                    for tc in tcs:
                        tid = tc.get("test_id", "")
                        if tid not in seen:
                            seen.add(tid)
                            tc_list.append(tc)
            details.append((fpath.name, len(tc_list) - count_before))

        tc_sets[key] = tc_list
        file_details[key] = details
        _vlog(
            f"  {key}: {len(tc_list)} TC caricati da {len(files)} file "
            f"(deduplica da {len(seen)} ID)",
            log_level,
        )

    # --- 4d. Riepilogo file ---
    print(f"\n{_C.CYAN}{'─'*50}")
    print(f"  File che verranno inviati al modello per la valutazione:")
    print(f"{'─'*50}{_C.RESET}")

    total_tc = 0
    for key in selected_keys:
        chain = TC_CHAINS[key]
        files = available_chains[key]
        tc_list = tc_sets[key]
        total_tc += len(tc_list)
        print(f"\n  {_C.WHITE}{chain.label}{_C.RESET} — "
              f"{len(files)} file, "
              f"{_C.WHITE}{len(tc_list)}{_C.RESET} test cases:")
        for fname, n in file_details[key]:
            print(f"    {_C.DIM}-{_C.RESET} {fname}  {_C.DIM}({n} TC){_C.RESET}")

    print(f"\n  Totale test cases inviati: {_C.WHITE}{total_tc}{_C.RESET}")
    print(f"{_C.CYAN}{'─'*50}{_C.RESET}")

    # --- 4e. Chiamata valutazione ---
    verbose = log_level == _LOG_VERBOSE
    _vlog(
        f"Payload totale: "
        f"{sum(len(json.dumps(tc)) for tc in tc_sets.values())} char circa",
        log_level,
    )
    print(f"\n{_C.DIM}[eval] Avvio valutazione coerenza per {req_code}...{_C.RESET}")
    result = evaluate_test_cases(
        requirement=requirement,
        tc_sets=tc_sets,
        chain_metadata=chain_metadata,
        system_prompt=system_prompt_eval,
        config=config,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        verbose=verbose,
    )

    # Cartella di output per questo requisito
    eval_dir = out_path / OutputDirs.EVALUATIONS / req_code
    eval_dir.mkdir(parents=True, exist_ok=True)

    if result["status"] == "rejected":
        print(f"\n  {_C.YELLOW}REJECTED dal modello — input non valido:{_C.RESET}")
        for r in result["reasons"]:
            print(f"    - {r}")
        rej_file = eval_dir / "evaluation_REJECTED.json"
        rej_file.write_text(
            json.dumps(result["raw_response"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  {_C.DIM}Dettaglio salvato in: {rej_file}{_C.RESET}")
        return

    if result["status"] == "error":
        print(f"\n  {_C.RED}ERRORE: {result['error']}{_C.RESET}", file=sys.stderr)
        if result.get("raw_text"):
            raw_file = eval_dir / "evaluation_RAW.txt"
            raw_file.write_text(result["raw_text"], encoding="utf-8")
            print(f"  {_C.DIM}Risposta grezza salvata in: {raw_file}{_C.RESET}")
        return

    # Salva il risultato JSON
    evaluation = result["evaluation"]
    eval_file = eval_dir / "evaluation.json"
    eval_file.write_text(
        json.dumps(evaluation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _vlog(f"File scritto: {eval_file} ({eval_file.stat().st_size} bytes)", log_level)

    # --- 4f. Generazione HTML ---
    from .report_html import generate_evaluation_html

    html_content = generate_evaluation_html(
        evaluation=evaluation,
        requirement=requirement,
        tc_sets=tc_sets,
        chain_metadata=chain_metadata,
        model=config.deployment,
    )
    html_file = eval_dir / "evaluation_report.html"
    html_file.write_text(html_content, encoding="utf-8")
    _vlog(f"File scritto: {html_file} ({html_file.stat().st_size} bytes)", log_level)

    # --- 4g. Report console ---
    print(f"\n{_C.CYAN}{'='*50}")
    print(f"  Valutazione coerenza — {req_code}")
    print(f"{'='*50}{_C.RESET}")

    for key in selected_keys:
        label = chain_metadata[key]["label"]
        data = evaluation.get(key)
        if data is None:
            continue
        score = data.get("coherence_score", "N/A")
        tc_count = data.get("tc_count", "N/A")
        ac_cov = data.get("ac_coverage", {})
        covered = ac_cov.get("covered_ac", "?")
        total_ac = ac_cov.get("total_ac", "?")
        added_list = data.get("added_info", [])
        missing_list = data.get("missing_info", [])
        redundancies = len(data.get("redundancies", []))

        if isinstance(score, (int, float)):
            if score >= 80:
                score_color = _C.GREEN
            elif score >= 50:
                score_color = _C.YELLOW
            else:
                score_color = _C.RED
        else:
            score_color = _C.WHITE

        print(f"\n  {_C.WHITE}{label}:{_C.RESET}")
        print(f"    TC totali:           {tc_count}")
        print(f"    Punteggio coerenza:  {score_color}{score}/100{_C.RESET}")
        print(f"    Copertura AC:        {covered}/{total_ac}")
        print(f"    Info aggiunte:       {len(added_list)}")
        if added_list:
            for item in added_list:
                tid = item.get("test_id", "?")
                detail = item.get("detail", "")
                print(f"      {_C.YELLOW}[{tid}]{_C.RESET} {detail}")
        print(f"    Info mancanti:       {len(missing_list)}")
        if missing_list:
            for item in missing_list:
                source = item.get("source", "?")
                detail = item.get("detail", "")
                print(f"      {_C.YELLOW}[{source}]{_C.RESET} {detail}")
        print(f"    Ridondanze:          {redundancies}")

    comparison = evaluation.get("comparison")
    if comparison:
        winner_key = comparison.get("winner", "N/A")
        winner_label = chain_metadata.get(winner_key, {}).get("label", winner_key)
        ranking = comparison.get("ranking", [])
        reasoning = comparison.get("reasoning", "")
        print(f"\n  {_C.WHITE}Confronto:{_C.RESET}")
        print(f"    Vincitore: {_C.GREEN}{winner_label}{_C.RESET}")
        if ranking:
            ranking_labels = [
                chain_metadata.get(k, {}).get("label", k) for k in ranking
            ]
            print(f"    Classifica: {' > '.join(ranking_labels)}")
        print(f"    Motivazione: {reasoning}")

    print(f"\n  {_C.DIM}Output salvato in: {eval_dir}/{_C.RESET}")
    print(f"    {_C.DIM}- evaluation.json (dati grezzi){_C.RESET}")
    print(f"    {_C.DIM}- evaluation_report.html (report visuale){_C.RESET}")
    print(f"{_C.CYAN}{'='*50}{_C.RESET}")


# ---------------------------------------------------------------------------
# Flusso interattivo — report
# ---------------------------------------------------------------------------


def _print_report(
    mode: str,
    total: int,
    skipped: list[dict],
    rejected: list[dict],
    errors: list[dict],
    all_user_stories: list[dict],
    all_test_cases: list,
    out_path: Path,
    all_test_cases_direct: list | None = None,
) -> None:
    """Stampa il report finale dopo una generazione."""
    print(f"\n{_C.CYAN}{'='*50}")
    print(f"  Report")
    print(f"{'='*50}{_C.RESET}")

    # Statistiche requisiti (per modi che processano requisiti)
    if mode in (_MODE_FULL, _MODE_US_ONLY, _MODE_TC_DIRECT):
        elaborated = total - len(skipped) - len(rejected)
        print(f"  Requisiti totali:          {total}")
        print(f"  Skip sintattici:           {len(skipped)}")
        print(f"  Rifiutati (semantica LLM): {len(rejected)}")
        print(
            f"  Elaborati con successo:    "
            f"{_C.GREEN}{elaborated - len(errors)}{_C.RESET}"
        )

    if errors:
        print(f"  Errori tecnici:            {_C.RED}{len(errors)}{_C.RESET}")
    else:
        print(f"  Errori tecnici:            0")

    # Conteggi user stories
    if mode in (_MODE_FULL, _MODE_US_ONLY, _MODE_TC_FROM_US):
        print(f"  User stories totali:       {len(all_user_stories)}")

    # Conteggi test cases
    if mode == _MODE_FULL:
        print(f"  TC indiretti totali:       {len(all_test_cases)}")
        print(f"  TC diretti totali:         {len(all_test_cases_direct or [])}")
    elif mode != _MODE_US_ONLY:
        print(f"  Test cases totali:         {len(all_test_cases)}")

    print(f"\n  {_C.DIM}Output: {out_path}{_C.RESET}")
    print(f"{_C.CYAN}{'='*50}{_C.RESET}")


# ---------------------------------------------------------------------------
# Flusso interattivo — loop principale
# ---------------------------------------------------------------------------


def _run_interactive(args: argparse.Namespace, config: AzureOpenAIConfig) -> None:
    # Banner (stampato una sola volta)
    print(f"\n{_C.CYAN}{'='*50}")
    print(f"  TECO Pipeline Interattiva")
    print(f"{'='*50}{_C.RESET}")
    print(f"{_C.DIM}Endpoint: {config.endpoint}{_C.RESET}")

    # Prepara output (una sola volta)
    out_path = Path(args.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    us_dir = out_path / OutputDirs.US_AC
    tc_dir = out_path / OutputDirs.TC_FROM_US_AC
    us_dir.mkdir(parents=True, exist_ok=True)
    tc_dir.mkdir(parents=True, exist_ok=True)

    # Directory prompts
    prompts_path = Path(args.prompts_dir)

    # Modelli disponibili per il cambio deployment
    available_models = [
        config.deployment,  # modello corrente (da config / CLI)
        "gpt-5.1",
        "gpt-5.2",
        "gpt-5.1-chat",
        "gpt-5-mini",
    ]
    seen_models: set[str] = set()
    unique_models: list[str] = []
    for m in available_models:
        if m not in seen_models:
            seen_models.add(m)
            unique_models.append(m)
    available_models = unique_models

    log_level = _LOG_VERBOSE  # default: verbose

    # === Loop principale ===
    while True:
        # Barra di stato
        print(f"\n{_C.DIM}{'─'*50}{_C.RESET}")
        print(
            f"  {_C.YELLOW}Modello:{_C.RESET} {config.deployment}  "
            f"{_C.DIM}|{_C.RESET}  "
            f"{_C.YELLOW}Output:{_C.RESET} {out_path}  "
            f"{_C.DIM}|{_C.RESET}  "
            f"{_C.YELLOW}Log:{_C.RESET} {log_level}"
        )

        main_choice = _ask_choice(
            "Menu principale:",
            ["Genera", "Valuta coerenza test cases", "Impostazioni", "Esci"],
        )

        # --- Esci ---
        if main_choice == 3:
            print(f"\n{_C.CYAN}Arrivederci.{_C.RESET}")
            return

        # ===============================================================
        # Genera
        # ===============================================================
        if main_choice == 0:
            gen_choice = _ask_choice(
                f"{_C.GREEN}Genera ›{_C.RESET} Cosa vuoi generare?",
                [
                    f"Genera tutto {_C.DIM}(US → TC indiretti → TC diretti){_C.RESET}",
                    f"User Stories                        {_C.DIM}da requisiti{_C.RESET}",
                    f"Test Cases via User Stories         {_C.DIM}da US esistenti su disco{_C.RESET}",
                    f"Test Cases diretti                  {_C.DIM}da requisiti, senza passare dalle US{_C.RESET}",
                    "Indietro",
                ],
                separators={
                    0: "Pipeline completa",
                    1: "Passi singoli",
                },
            )
            if gen_choice == 4:
                continue

            # Variabili di sessione comuni
            errors: list[dict] = []
            skipped: list[dict] = []
            rejected: list[dict] = []
            all_user_stories: list[dict] = []
            all_test_cases: list = []
            all_test_cases_direct: list = []
            total = 0
            did_work = False
            mode = _MODE_TC_FROM_US  # default, sovrascritto sotto

            # -----------------------------------------------------------
            # Generazione completa (US + TC indiretti + TC diretti)
            # -----------------------------------------------------------
            if gen_choice == 0:
                mode = _MODE_FULL
                verbose = log_level == _LOG_VERBOSE
                system_prompt_tc = (
                    prompts_path / PromptFiles.TC_FROM_US
                ).read_text(encoding="utf-8")
                system_prompt_direct = (
                    prompts_path / PromptFiles.TC_FROM_REQ
                ).read_text(encoding="utf-8")

                req_path = _ask_requirements_file(Path(args.requirements))
                if req_path is None:
                    continue
                requirements = json.loads(
                    req_path.read_text(encoding="utf-8")
                )
                print(f"Requisiti caricati: {len(requirements)}")

                # Scelta strategia US
                us_strategy = _ask_us_strategy()
                if us_strategy is None:
                    continue

                # Estrai personas se necessario (persona o both)
                personas_ctx: str | None = None
                reqs_for_us = requirements  # requisiti per la generazione US
                if us_strategy in ("persona", "both"):
                    personas_ctx, reqs_for_us = extract_personas_context(requirements)
                    personas_list = json.loads(personas_ctx)
                    print(f"\n{_C.CYAN}Personas individuate ({len(personas_list)}):{_C.RESET}")
                    for p in personas_list:
                        print(f"  {_C.WHITE}-{_C.RESET} {p.get('code', '?')} | {p.get('title', 'N/A')}")
                    print(f"Requisiti da elaborare (esclusi PERSONAS): {len(reqs_for_us)}")
                if us_strategy == "ac":
                    print(f"Strategia: AC-based")
                elif us_strategy == "both":
                    print(f"Strategia: entrambe (AC + persona)")

                scope_result = _ask_scope(reqs_for_us)
                if scope_result is None:
                    continue
                selected, single_req_code = scope_result

                total = len(selected)
                did_work = True

                _vlog(f"File requisiti: {req_path} ({req_path.stat().st_size} bytes)", log_level)
                _vlog(f"Requisiti totali: {len(requirements)}, da elaborare: {len(selected)}", log_level)
                _vlog(f"Prompt TC caricato: {len(system_prompt_tc)} char", log_level)
                _vlog(f"Prompt TC diretti: {len(system_prompt_direct)} char", log_level)

                # Fase 1: genera User Stories
                if us_strategy == "both":
                    # --- AC-based ---
                    print(f"\n{_C.CYAN}── Fase 1/3a: User Stories (AC-based) ──{_C.RESET}")
                    system_prompt_us_ac = (
                        prompts_path / PromptFiles.US_AC
                    ).read_text(encoding="utf-8")
                    us_by_req, all_user_stories, skipped, rejected, errors = (
                        _generate_us(
                            selected=selected,
                            system_prompt_us=system_prompt_us_ac,
                            config=config,
                            args=args,
                            us_dir=us_dir,
                            log_level=log_level,
                        )
                    )
                    # --- Persona-based ---
                    print(f"\n{_C.CYAN}── Fase 1/3b: User Stories (persona-based) ──{_C.RESET}")
                    system_prompt_us_persona = (
                        prompts_path / PromptFiles.US_PERSONA
                    ).read_text(encoding="utf-8")
                    us_dir_persona = out_path / OutputDirs.US_PERSONA
                    us_dir_persona.mkdir(parents=True, exist_ok=True)
                    us_by_req_p, us_flat_p, skip_p, rej_p, err_p = (
                        _generate_us(
                            selected=selected,
                            system_prompt_us=system_prompt_us_persona,
                            config=config,
                            args=args,
                            us_dir=us_dir_persona,
                            personas_context=personas_ctx,
                            log_level=log_level,
                        )
                    )
                    skipped.extend(skip_p)
                    rejected.extend(rej_p)
                    errors.extend(err_p)
                    print(
                        f"\n{_C.GREEN}  US generate: "
                        f"{len(all_user_stories)} AC-based, "
                        f"{len(us_flat_p)} persona-based{_C.RESET}"
                    )
                elif us_strategy == "persona":
                    print(f"\n{_C.CYAN}── Fase 1/3: User Stories (persona-based) ──{_C.RESET}")
                    system_prompt_us = (
                        prompts_path / PromptFiles.US_PERSONA
                    ).read_text(encoding="utf-8")
                    effective_us_dir = out_path / OutputDirs.US_PERSONA
                    effective_us_dir.mkdir(parents=True, exist_ok=True)
                    us_by_req, all_user_stories, skipped, rejected, errors = (
                        _generate_us(
                            selected=selected,
                            system_prompt_us=system_prompt_us,
                            config=config,
                            args=args,
                            us_dir=effective_us_dir,
                            personas_context=personas_ctx,
                            log_level=log_level,
                        )
                    )
                else:
                    print(f"\n{_C.CYAN}── Fase 1/3: User Stories (AC-based) ──{_C.RESET}")
                    system_prompt_us = (
                        prompts_path / PromptFiles.US_AC
                    ).read_text(encoding="utf-8")
                    us_by_req, all_user_stories, skipped, rejected, errors = (
                        _generate_us(
                            selected=selected,
                            system_prompt_us=system_prompt_us,
                            config=config,
                            args=args,
                            us_dir=us_dir,
                            log_level=log_level,
                        )
                    )

                # Fase 2: genera TC indiretti (da US)
                if us_by_req:
                    effective_tc_dir = tc_dir
                    if us_strategy == "persona":
                        effective_tc_dir = out_path / OutputDirs.TC_FROM_US_PERSONA
                        effective_tc_dir.mkdir(parents=True, exist_ok=True)

                    label_tc = "AC-based" if us_strategy != "persona" else "persona-based"
                    print(f"\n{_C.CYAN}── Fase 2/3: Test Cases indiretti (da US {label_tc}) ──{_C.RESET}")
                    tc_total = len(us_by_req)
                    for tc_i, (req_code, req_us) in enumerate(
                        us_by_req.items(), 1
                    ):
                        print(
                            f"\n[pipeline] [{tc_i}/{tc_total}] "
                            f"TC indiretti per {req_code} "
                            f"({len(req_us)} user stories)..."
                        )
                        _vlog(f"{req_code}: {len(req_us)} user stories in input", log_level)
                        tc_result = process_us_to_tc(
                            user_stories=req_us,
                            system_prompt=system_prompt_tc,
                            config=config,
                            temperature=args.temperature,
                            max_tokens=args.max_tokens,
                            verbose=verbose,
                        )
                        _handle_tc_result(
                            tc_result, effective_tc_dir, errors,
                            all_test_cases, req_code, log_level,
                        )

                # Fase 2b: se "both", genera anche TC dalle US persona
                if us_strategy == "both" and us_by_req_p:
                    tc_dir_persona = out_path / OutputDirs.TC_FROM_US_PERSONA
                    tc_dir_persona.mkdir(parents=True, exist_ok=True)
                    all_test_cases_persona: list = []
                    print(f"\n{_C.CYAN}── Fase 2b/3: Test Cases indiretti (da US persona-based) ──{_C.RESET}")
                    tc_total_p = len(us_by_req_p)
                    for tc_i, (req_code, req_us) in enumerate(
                        us_by_req_p.items(), 1
                    ):
                        print(
                            f"\n[pipeline] [{tc_i}/{tc_total_p}] "
                            f"TC indiretti (persona) per {req_code} "
                            f"({len(req_us)} user stories)..."
                        )
                        _vlog(f"{req_code}: {len(req_us)} user stories in input", log_level)
                        tc_result = process_us_to_tc(
                            user_stories=req_us,
                            system_prompt=system_prompt_tc,
                            config=config,
                            temperature=args.temperature,
                            max_tokens=args.max_tokens,
                            verbose=verbose,
                        )
                        _handle_tc_result(
                            tc_result, tc_dir_persona, errors,
                            all_test_cases_persona, req_code, log_level,
                        )
                    print(
                        f"\n{_C.GREEN}  TC indiretti generati: "
                        f"{len(all_test_cases)} da US AC-based, "
                        f"{len(all_test_cases_persona)} da US persona-based{_C.RESET}"
                    )

                # Fase 3: genera TC diretti (da requisiti)
                print(f"\n{_C.CYAN}── Fase 3/3: Test Cases diretti (da requisiti) ──{_C.RESET}")
                direct_dir = out_path / OutputDirs.TC_FROM_REQ
                direct_dir.mkdir(parents=True, exist_ok=True)
                # Usa solo i requisiti elaborati con successo (non skipped/rejected)
                elaborated_codes = set(us_by_req.keys())
                direct_selected = [
                    r for r in selected
                    if r.get("code") in elaborated_codes
                ]
                if not direct_selected:
                    direct_selected = selected  # fallback: prova tutti

                _vlog(f"Requisiti selezionati per TC diretti: {len(direct_selected)}", log_level)

                for i, req in enumerate(direct_selected, 1):
                    code = req.get("code", f"REQ-{i}")
                    print(f"\n[pipeline] [{i}/{len(direct_selected)}] TC diretti per {code}...")
                    result = process_requirement_to_tc_direct(
                        req=req,
                        system_prompt=system_prompt_direct,
                        config=config,
                        temperature=args.temperature,
                        max_tokens=args.max_tokens,
                        verbose=verbose,
                    )
                    _handle_direct_tc_result(
                        result, direct_dir, code,
                        errors, skipped, rejected,
                        all_test_cases_direct,
                        log_level,
                    )

            # -----------------------------------------------------------
            # Solo User Stories
            # -----------------------------------------------------------
            elif gen_choice == 1:
                mode = _MODE_US_ONLY

                req_path = _ask_requirements_file(Path(args.requirements))
                if req_path is None:
                    continue
                requirements = json.loads(
                    req_path.read_text(encoding="utf-8")
                )
                print(f"Requisiti caricati: {len(requirements)}")

                # Scelta strategia US
                us_strategy = _ask_us_strategy()
                if us_strategy is None:
                    continue

                personas_ctx: str | None = None
                reqs_for_us = requirements
                if us_strategy in ("persona", "both"):
                    personas_ctx, reqs_for_us = extract_personas_context(requirements)
                    personas_list = json.loads(personas_ctx)
                    print(f"\n{_C.CYAN}Personas individuate ({len(personas_list)}):{_C.RESET}")
                    for p in personas_list:
                        print(f"  {_C.WHITE}-{_C.RESET} {p.get('code', '?')} | {p.get('title', 'N/A')}")
                    print(f"Requisiti da elaborare (esclusi PERSONAS): {len(reqs_for_us)}")
                if us_strategy == "ac":
                    print(f"Strategia: AC-based")
                elif us_strategy == "both":
                    print(f"Strategia: entrambe (AC + persona)")

                scope_result = _ask_scope(reqs_for_us)
                if scope_result is None:
                    continue
                selected, single_req_code = scope_result

                total = len(selected)
                did_work = True

                if us_strategy == "both":
                    # --- AC-based ---
                    print(f"\n{_C.CYAN}── User Stories (AC-based) ──{_C.RESET}")
                    system_prompt_us_ac = (
                        prompts_path / PromptFiles.US_AC
                    ).read_text(encoding="utf-8")
                    _, all_user_stories, skipped, rejected, errors = (
                        _generate_us(
                            selected=selected,
                            system_prompt_us=system_prompt_us_ac,
                            config=config,
                            args=args,
                            us_dir=us_dir,
                            log_level=log_level,
                        )
                    )
                    # --- Persona-based ---
                    print(f"\n{_C.CYAN}── User Stories (persona-based) ──{_C.RESET}")
                    system_prompt_us_persona = (
                        prompts_path / PromptFiles.US_PERSONA
                    ).read_text(encoding="utf-8")
                    us_dir_persona = out_path / OutputDirs.US_PERSONA
                    us_dir_persona.mkdir(parents=True, exist_ok=True)
                    _, us_flat_p, skip_p, rej_p, err_p = (
                        _generate_us(
                            selected=selected,
                            system_prompt_us=system_prompt_us_persona,
                            config=config,
                            args=args,
                            us_dir=us_dir_persona,
                            personas_context=personas_ctx,
                            log_level=log_level,
                        )
                    )
                    skipped.extend(skip_p)
                    rejected.extend(rej_p)
                    errors.extend(err_p)
                    all_user_stories.extend(us_flat_p)
                    print(
                        f"\n{_C.GREEN}  US generate: "
                        f"{len(all_user_stories) - len(us_flat_p)} AC-based, "
                        f"{len(us_flat_p)} persona-based{_C.RESET}"
                    )
                elif us_strategy == "persona":
                    print(f"\n{_C.CYAN}── User Stories (persona-based) ──{_C.RESET}")
                    system_prompt_us = (
                        prompts_path / PromptFiles.US_PERSONA
                    ).read_text(encoding="utf-8")
                    effective_us_dir = out_path / OutputDirs.US_PERSONA
                    effective_us_dir.mkdir(parents=True, exist_ok=True)
                    _, all_user_stories, skipped, rejected, errors = (
                        _generate_us(
                            selected=selected,
                            system_prompt_us=system_prompt_us,
                            config=config,
                            args=args,
                            us_dir=effective_us_dir,
                            personas_context=personas_ctx,
                            log_level=log_level,
                        )
                    )
                else:
                    print(f"\n{_C.CYAN}── User Stories (AC-based) ──{_C.RESET}")
                    system_prompt_us = (
                        prompts_path / PromptFiles.US_AC
                    ).read_text(encoding="utf-8")
                    _, all_user_stories, skipped, rejected, errors = (
                        _generate_us(
                            selected=selected,
                            system_prompt_us=system_prompt_us,
                            config=config,
                            args=args,
                            us_dir=us_dir,
                            log_level=log_level,
                        )
                    )

            # -----------------------------------------------------------
            # Solo TC indiretti (da User Stories esistenti)
            # -----------------------------------------------------------
            elif gen_choice == 2:
                mode = _MODE_TC_FROM_US
                us_by_req = _load_existing_us(us_dir)
                if not us_by_req:
                    print(
                        f"\n  {_C.YELLOW}Nessuna user story trovata in {us_dir}/. "
                        f"Genera prima le user stories.{_C.RESET}",
                        file=sys.stderr,
                    )
                    continue
                all_user_stories = [
                    us for group in us_by_req.values() for us in group
                ]
                print(
                    f"\nUser stories caricate da disco: "
                    f"{len(all_user_stories)} "
                    f"({len(us_by_req)} requisiti)"
                )

                system_prompt_tc = (
                    prompts_path / PromptFiles.TC_FROM_US
                ).read_text(encoding="utf-8")

                tc_result_list = _generate_tc(
                    us_by_req=us_by_req,
                    all_user_stories=all_user_stories,
                    system_prompt_tc=system_prompt_tc,
                    config=config,
                    args=args,
                    tc_dir=tc_dir,
                    errors=errors,
                    log_level=log_level,
                )

                if tc_result_list is not None:
                    did_work = True
                    all_test_cases = tc_result_list

            # -----------------------------------------------------------
            # Solo TC diretti (da requisiti)
            # -----------------------------------------------------------
            elif gen_choice == 3:
                mode = _MODE_TC_DIRECT
                verbose = log_level == _LOG_VERBOSE
                system_prompt_direct = (
                    prompts_path / PromptFiles.TC_FROM_REQ
                ).read_text(encoding="utf-8")

                req_path = _ask_requirements_file(Path(args.requirements))
                if req_path is None:
                    continue
                requirements_list: list[dict] = json.loads(
                    req_path.read_text(encoding="utf-8")
                )
                print(f"Requisiti caricati: {len(requirements_list)}")

                scope_result = _ask_scope(requirements_list)
                if scope_result is None:
                    continue
                selected, single_req_code = scope_result

                total = len(selected)
                did_work = True

                _vlog(f"Prompt TC diretti: {len(system_prompt_direct)} char", log_level)
                _vlog(f"Requisiti selezionati per TC diretti: {len(selected)}", log_level)

                direct_dir = out_path / OutputDirs.TC_FROM_REQ
                direct_dir.mkdir(parents=True, exist_ok=True)

                for i, req in enumerate(selected, 1):
                    code = req.get("code", f"REQ-{i}")
                    print(f"\n[pipeline] [{i}/{total}] TC diretti per {code}...")
                    result = process_requirement_to_tc_direct(
                        req=req,
                        system_prompt=system_prompt_direct,
                        config=config,
                        temperature=args.temperature,
                        max_tokens=args.max_tokens,
                        verbose=verbose,
                    )
                    _handle_direct_tc_result(
                        result, direct_dir, code,
                        errors, skipped, rejected,
                        all_test_cases,
                        log_level,
                    )

            # --- Salva errori / rejected / skipped ---
            if rejected:
                (out_path / "rejected_requirements.json").write_text(
                    json.dumps(rejected, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            if skipped:
                (out_path / "skipped_syntax.json").write_text(
                    json.dumps(skipped, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            if errors:
                (out_path / "errors.json").write_text(
                    json.dumps(errors, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

            # --- Report ---
            if did_work:
                _print_report(
                    mode=mode,
                    total=total,
                    skipped=skipped,
                    rejected=rejected,
                    errors=errors,
                    all_user_stories=all_user_stories,
                    all_test_cases=all_test_cases,
                    out_path=out_path,
                    all_test_cases_direct=(
                        all_test_cases_direct if mode == _MODE_FULL else None
                    ),
                )

        # ===============================================================
        # Valuta
        # ===============================================================
        elif main_choice == 1:
            _evaluate_coherence(args, config, out_path, prompts_path, log_level)

        # ===============================================================
        # Impostazioni
        # ===============================================================
        elif main_choice == 2:
            settings_choice = _ask_choice(
                f"{_C.YELLOW}Impostazioni ›{_C.RESET}",
                [
                    f"Modello LLM            {_C.DIM}attuale: {config.deployment}{_C.RESET}",
                    f"Livello log            {_C.DIM}attuale: {log_level}{_C.RESET}",
                    "Svuota cartella output",
                    "Indietro",
                ],
            )
            if settings_choice == 3:
                continue

            if settings_choice == 0:
                labels = [
                    f"{m}  {_C.GREEN}(attuale){_C.RESET}" if m == config.deployment else m
                    for m in available_models
                ]
                choice = _ask_choice(
                    f"Modello attuale: {_C.WHITE}{config.deployment}{_C.RESET}\n"
                    "Scegli il nuovo modello:",
                    labels + ["Indietro"],
                )
                if choice == len(labels):
                    continue
                new_model = available_models[choice]
                if new_model == config.deployment:
                    print(
                        f"\n  {_C.DIM}Il modello e gia "
                        f"{config.deployment}, nessuna modifica.{_C.RESET}"
                    )
                else:
                    config.deployment = new_model
                    print(
                        f"\n  {_C.GREEN}Modello cambiato: "
                        f"{config.deployment}{_C.RESET}"
                    )

            elif settings_choice == 1:
                log_level = _LOG_INFO if log_level == _LOG_VERBOSE else _LOG_VERBOSE
                print(f"\n  {_C.GREEN}Livello log: {log_level}{_C.RESET}")

            elif settings_choice == 2:
                _clean_output(out_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    args = _parse_args()

    try:
        config = load_config(
            env_file=args.env_file,
            deployment_override=args.deployment,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(
            f"{_C.RED}[teco-interactive] Errore configurazione: {exc}{_C.RESET}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        _run_interactive(args, config)
    except KeyboardInterrupt:
        print(f"\n\n{_C.DIM}Interrotto dall'utente.{_C.RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
