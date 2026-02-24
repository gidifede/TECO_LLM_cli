"""Shell interattiva per simulazione, estrazione requisiti e valutazione."""

import argparse
import shutil
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from . import services
from .comparison import generate_comparison_html
from .config import AzureOpenAIConfig, load_config
from .paths import OutputDirs


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


# ---------------------------------------------------------------------------
# Helper di input
# ---------------------------------------------------------------------------


def _ask_choice(prompt: str, options: list[str]) -> int:
    """Mostra un menu numerato e restituisce l'indice scelto (0-based)."""
    print(f"\n{_C.CYAN}{prompt}{_C.RESET}")
    for i, opt in enumerate(options):
        print(f"  {_C.WHITE}{i + 1}.{_C.RESET} {opt}")

    while True:
        raw = input(f"{_C.YELLOW}> {_C.RESET}").strip()
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


# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------


DEFAULT_SCENARIOS_DIR = "scenarios"
DEFAULT_OUTPUT_DIR = "./output_test"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="interview-evaluator",
        description=(
            "Shell interattiva per simulazione interviste, "
            "estrazione requisiti e valutazione qualita."
        ),
    )

    parser.add_argument(
        "--scenarios-dir",
        default=DEFAULT_SCENARIOS_DIR,
        help=f"Directory scenari (default: {DEFAULT_SCENARIOS_DIR}).",
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
        default=4096,
        help="Max token nella risposta (default: 4096).",
    )

    args = parser.parse_args(argv)
    args.output_dir = DEFAULT_OUTPUT_DIR
    return args


# ---------------------------------------------------------------------------
# Alias al service layer
# ---------------------------------------------------------------------------

_load_scenarios = services.load_scenarios
_load_interviewer_prompts = services.load_interviewer_prompts
_scan_conversations = services.scan_conversations
_scan_requirements = services.scan_requirements
_scan_evaluations = services.scan_evaluations
_run_path = services.run_path
_find_scenario_for_id = services.find_scenario_for_id


# ---------------------------------------------------------------------------
# Azioni principali
# ---------------------------------------------------------------------------


def _run_simulation(
    scenario: dict,
    interviewer_prompt: str,
    prompt_label: str,
    prompts_dir: Path,
    run: Path,
    config: AzureOpenAIConfig,
    args: argparse.Namespace,
    log_level: str,
    run_number: int | None = None,
) -> tuple[dict | None, int]:
    """Esegue la simulazione e salva il risultato (wrapper CLI)."""
    scenario_id = scenario.get("id", "unknown")
    scenario_name = scenario.get("name", "")
    topic = scenario.get("topic", "")

    print(f"\n{_C.CYAN}Avvio simulazione: {scenario_name} ({scenario_id}){_C.RESET}")
    print(f"{_C.DIM}Prompt: {prompt_label} | Modello: {config.deployment} | Temp: {args.temperature}{_C.RESET}")
    if topic:
        print(f"{_C.DIM}Topic guidato: {topic}{_C.RESET}")

    try:
        conv_data, num = services.run_simulation(
            scenario=scenario,
            interviewer_prompt=interviewer_prompt,
            prompt_label=prompt_label,
            prompts_dir=prompts_dir,
            run=run,
            config=config,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            run_number=run_number,
            verbose=(log_level == _LOG_VERBOSE),
        )
    except FileNotFoundError as exc:
        print(f"  {_C.RED}{exc}{_C.RESET}", file=sys.stderr)
        return None, 0

    if conv_data is None:
        return None, 0

    # Report console
    conv_file = run / OutputDirs.CONVERSATIONS / scenario_id / f"{num}_conversation.json"
    print(f"\n{_C.CYAN}{'='*50}")
    print(f"  Simulazione completata")
    print(f"{'='*50}{_C.RESET}")
    print(f"  Scenario:            {scenario_name}")
    print(f"  Prompt:              {prompt_label}")
    print(f"  Modello:             {config.deployment}")
    if topic:
        print(f"  Topic:               {topic}")
    print(f"  Turni:               {conv_data.get('total_turns', '?')}")
    print(f"  Token totali:        {conv_data.get('total_tokens', '?')}")
    completed = conv_data.get("completed_naturally", False)
    print(f"  Terminata naturalmente: {_C.GREEN if completed else _C.RED}"
          f"{completed}{_C.RESET}")
    print(f"  Run #:               {num}")
    print(f"  File salvato:        {_C.DIM}{conv_file}{_C.RESET}")
    print(f"{_C.CYAN}{'='*50}{_C.RESET}")

    return conv_data, num


def _run_extraction(
    conv_data: dict,
    prompts_dir: Path,
    run: Path,
    config: AzureOpenAIConfig,
    args: argparse.Namespace,
    log_level: str,
    run_number: int | None = None,
) -> dict | None:
    """Esegue l'estrazione requisiti da una conversazione salvata (wrapper CLI)."""
    scenario_id = conv_data.get("scenario_id", "unknown")

    print(f"\n{_C.CYAN}Avvio estrazione requisiti: {scenario_id}{_C.RESET}")
    print(f"{_C.DIM}Conversazione: {conv_data.get('total_turns', '?')} turni{_C.RESET}")

    try:
        output_data = services.run_extraction(
            conv_data=conv_data,
            prompts_dir=prompts_dir,
            run=run,
            config=config,
            temperature=args.temperature,
            run_number=run_number,
            verbose=(log_level == _LOG_VERBOSE),
        )
    except FileNotFoundError as exc:
        print(f"  {_C.RED}{exc}{_C.RESET}", file=sys.stderr)
        return None

    if output_data is None:
        print(f"\n  {_C.RED}Estrazione fallita.{_C.RESET}", file=sys.stderr)
        return None

    requirements = output_data.get("requirements", [])
    num = output_data.get("source_conversation", "").split("/")[-1].split("_")[0]
    req_file = run / OutputDirs.REQUIREMENTS / scenario_id / f"{num}_requirements.json"

    # Report console
    print(f"\n{_C.CYAN}{'='*50}")
    print(f"  Estrazione completata — {scenario_id}")
    print(f"{'='*50}{_C.RESET}")
    print(f"  Requisiti estratti:  {_C.WHITE}{len(requirements)}{_C.RESET}")
    print(f"  Token estrazione:    {output_data.get('extraction_tokens', 'N/A')}")

    dist: dict[str, int] = {}
    for req in requirements:
        cat = req.get("tipo", "ALTRO")
        dist[cat] = dist.get(cat, 0) + 1
    if dist:
        print(f"\n  {_C.WHITE}Distribuzione categorie:{_C.RESET}")
        for cat, count in sorted(dist.items()):
            bar = "#" * count
            print(f"    {cat:<20} {count:>2}  {_C.DIM}{bar}{_C.RESET}")

    print(f"\n  {_C.DIM}File salvato: {req_file}{_C.RESET}")
    print(f"{_C.CYAN}{'='*50}{_C.RESET}")

    return output_data


def _run_evaluation(
    requirements_data: dict,
    scenario: dict,
    prompts_dir: Path,
    run: Path,
    config: AzureOpenAIConfig,
    args: argparse.Namespace,
    log_level: str,
    run_number: int | None = None,
) -> dict | None:
    """Esegue la valutazione dei requisiti estratti (wrapper CLI)."""
    scenario_id = scenario.get("id", requirements_data.get("scenario_id", "unknown"))
    requirements = requirements_data.get("requirements", [])

    print(f"\n{_C.CYAN}Avvio valutazione requisiti: {scenario_id}{_C.RESET}")
    print(f"{_C.DIM}Requisiti da valutare: {len(requirements)}{_C.RESET}")

    try:
        evaluation = services.run_evaluation(
            requirements_data=requirements_data,
            scenario=scenario,
            prompts_dir=prompts_dir,
            run=run,
            config=config,
            temperature=args.temperature,
            run_number=run_number,
            verbose=(log_level == _LOG_VERBOSE),
        )
    except FileNotFoundError as exc:
        print(f"  {_C.RED}{exc}{_C.RESET}", file=sys.stderr)
        return None

    if evaluation is None:
        print(f"\n  {_C.RED}Valutazione fallita.{_C.RESET}", file=sys.stderr)
        return None

    # Determina il file di output per il report
    src_req = evaluation.get("source_requirements", "")
    num = src_req.split("/")[-1].split("_")[0] if "/" in src_req else "?"
    eval_file = run / OutputDirs.EVALUATIONS / scenario_id / f"{num}_evaluation.json"

    _print_evaluation_report(evaluation, scenario_id, eval_file)

    return evaluation


# ---------------------------------------------------------------------------
# Report console
# ---------------------------------------------------------------------------


def _score_color(score: float | int | str, scale: float = 5.0) -> str:
    """Restituisce il colore ANSI in base al punteggio (scala 1-5 o personalizzata)."""
    if not isinstance(score, (int, float)):
        return _C.WHITE
    ratio = score / scale
    if ratio >= 0.8:
        return _C.GREEN
    if ratio >= 0.5:
        return _C.YELLOW
    return _C.RED


def _print_evaluation_report(
    evaluation: dict,
    scenario_id: str,
    eval_file: Path,
) -> None:
    """Stampa il report di valutazione a console (formato quantity/quality/maturity)."""
    overall = evaluation.get("overall_score", "N/A")
    topic = evaluation.get("topic", "")

    print(f"\n{_C.CYAN}{'='*50}")
    print(f"  Valutazione — {scenario_id}")
    if topic:
        print(f"  Topic: {topic}")
    print(f"{'='*50}{_C.RESET}")

    # --- Overall score ---
    color = _score_color(overall)
    print(f"\n  {_C.BOLD}Overall score: {color}{overall}/5.0{_C.RESET}")

    # --- Tempi medi intervista (da lineage) ---
    lineage = evaluation.get("lineage", {})
    interview_info = lineage.get("interview") or {}
    avg_turn = interview_info.get("avg_turn_time")
    if avg_turn is not None:
        avg_iv = interview_info.get("avg_interviewer_time", 0)
        avg_sh = interview_info.get("avg_stakeholder_time", 0)
        print(f"\n  {_C.WHITE}Tempi medi intervista:{_C.RESET}")
        print(f"    Tempo medio per turno:     {avg_turn:.1f}s")
        print(f"    Interviewer:               {avg_iv:.1f}s")
        print(f"    Stakeholder:               {avg_sh:.1f}s")

    # --- Quantity ---
    qty = evaluation.get("quantity", {})
    if qty:
        print(f"\n  {_C.WHITE}Quantita:{_C.RESET}")
        print(f"    Requisiti totali:          {qty.get('total_requirements', '?')}")
        print(f"    Categorie distinte:        {qty.get('distinct_categories', '?')}")
        print(f"    Criteri accettazione:      {qty.get('total_acceptance_criteria', '?')}")

        by_cat = qty.get("by_category", {})
        if by_cat:
            print(f"    {_C.DIM}Distribuzione:{_C.RESET}")
            for cat, count in by_cat.items():
                if count > 0:
                    bar = "#" * count
                    print(f"      {cat:<20} {count:>2}  {_C.DIM}{bar}{_C.RESET}")

    # --- Quality ---
    qual = evaluation.get("quality", {})
    if qual:
        qs = qual.get("quality_score", "N/A")
        color = _score_color(qs)
        print(f"\n  {_C.WHITE}Qualita:{_C.RESET}  {color}{qs}/5.0{_C.RESET}")

        for key, label in [
            ("avg_specificita_titolo", "Specificita titoli"),
            ("avg_completezza_descrizione", "Completezza descrizioni"),
            ("avg_qualita_criteri", "Qualita criteri acc."),
            ("avg_pertinenza_topic", "Pertinenza al topic"),
        ]:
            val = qual.get(key, "?")
            c = _score_color(val) if isinstance(val, (int, float)) else _C.WHITE
            print(f"    {label:<28} {c}{val}/5.0{_C.RESET}")

    # --- Maturity ---
    mat = evaluation.get("maturity", {})
    if mat:
        ms = mat.get("maturity_score", "N/A")
        color = _score_color(ms)
        print(f"\n  {_C.WHITE}Maturita:{_C.RESET}  {color}{ms}/5.0{_C.RESET}")

        for key, label in [
            ("copertura_topic", "Copertura topic"),
            ("prontezza_backlog", "Prontezza backlog"),
            ("ambiguita", "Chiarezza (no ambiguita)"),
            ("duplicati", "Unicita (no duplicati)"),
        ]:
            sub = mat.get(key, {})
            val = sub.get("score", "?") if isinstance(sub, dict) else "?"
            c = _score_color(val) if isinstance(val, (int, float)) else _C.WHITE
            print(f"    {label:<28} {c}{val}/5.0{_C.RESET}")

        cov = mat.get("copertura_topic", {})
        missing = cov.get("aspetti_mancanti", []) if isinstance(cov, dict) else []
        if missing:
            print(f"\n    {_C.YELLOW}Aspetti mancanti dal topic:{_C.RESET}")
            for a in missing:
                print(f"      - {a}")

        dup = mat.get("duplicati", {})
        dupes = dup.get("coppie_duplicate", []) if isinstance(dup, dict) else []
        if dupes:
            print(f"\n    {_C.RED}Duplicati:{_C.RESET}")
            for d in dupes:
                print(f"      - {d}")

    # --- Strengths / Weaknesses ---
    strengths = evaluation.get("strengths", [])
    if strengths:
        print(f"\n  {_C.GREEN}Punti di forza:{_C.RESET}")
        for s in strengths:
            print(f"    + {s}")

    weaknesses = evaluation.get("weaknesses", [])
    if weaknesses:
        print(f"\n  {_C.RED}Debolezze:{_C.RESET}")
        for w in weaknesses:
            print(f"    - {w}")

    print(f"\n  {_C.DIM}File salvato: {eval_file}{_C.RESET}")
    print(f"{_C.CYAN}{'='*50}{_C.RESET}")


# ---------------------------------------------------------------------------
# Pulizia output
# ---------------------------------------------------------------------------


def _clean_output(base_out: Path) -> None:
    """Rimuove tutto il contenuto della directory di output."""
    base_out = base_out.resolve()
    if not base_out.is_dir():
        print(f"\n  {_C.DIM}Directory non trovata: {base_out}{_C.RESET}")
        return

    all_files = list(base_out.rglob("*"))
    file_count = sum(1 for f in all_files if f.is_file())

    if file_count == 0:
        print(f"\n  {_C.DIM}La directory di output e gia vuota: {base_out}{_C.RESET}")
        return

    # Mostra struttura primo livello
    print(f"\n{_C.YELLOW}Contenuto di {base_out}:{_C.RESET}")
    for item in sorted(base_out.iterdir()):
        if item.is_dir():
            sub_count = sum(1 for f in item.rglob("*") if f.is_file())
            print(f"  {item.name}/ ({sub_count} file)")
        else:
            print(f"  {item.name}")

    print(f"\nTotale: {file_count} file")

    confirm = _ask_choice(
        "Confermi la cancellazione?",
        ["Si, cancella tutto", "No, annulla"],
    )
    if confirm == 1:
        print(f"  {_C.DIM}Operazione annullata.{_C.RESET}")
        return

    for item in base_out.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    print(f"\n  {_C.GREEN}Pulizia completata: {file_count} file rimossi.{_C.RESET}")


# ---------------------------------------------------------------------------
# Helper: selezione interviewer prompt
# ---------------------------------------------------------------------------


def _select_interviewer(prompts_dir: Path) -> tuple[str, str] | None:
    """Chiede all'utente di scegliere un prompt interviewer.

    Returns:
        (prompt_label, prompt_content) oppure None se annullato.
    """
    available = _load_interviewer_prompts(prompts_dir)
    if not available:
        print(
            f"\n  {_C.RED}Nessun prompt interviewer trovato in "
            f"{prompts_dir / PromptDirs.INTERVIEWERS}/.{_C.RESET}",
            file=sys.stderr,
        )
        return None

    if len(available) == 1:
        label, content = available[0]
        print(f"{_C.DIM}Prompt interviewer: {label} (unico disponibile){_C.RESET}")
        return label, content

    labels = [name for name, _ in available]
    labels.append("Indietro")
    idx = _ask_choice("Seleziona prompt interviewer:", labels)
    if idx == len(available):
        return None

    return available[idx]


# ---------------------------------------------------------------------------
# Helper: selezione modello per step
# ---------------------------------------------------------------------------

_AVAILABLE_MODELS = services.AVAILABLE_MODELS


def _select_model(step_label: str) -> str | None:
    """Chiede all'utente di scegliere un modello per uno step specifico.

    Args:
        step_label: etichetta dello step (es. "Simulazione", "Estrazione").

    Returns:
        Il nome del modello scelto, oppure None se l'utente ha scelto "Indietro".
    """
    labels = list(_AVAILABLE_MODELS)
    labels.append("Indietro")
    idx = _ask_choice(f"Modello per {step_label}:", labels)
    if idx == len(_AVAILABLE_MODELS):
        return None
    return _AVAILABLE_MODELS[idx]


# ---------------------------------------------------------------------------
# Confronto valutazioni
# ---------------------------------------------------------------------------


def _run_comparison(base_out: Path) -> None:
    """Guida l'utente nella selezione di due valutazioni e genera l'HTML di confronto."""
    evaluations = _scan_evaluations(base_out)
    if len(evaluations) < 2:
        print(
            f"\n  {_C.YELLOW}Servono almeno 2 valutazioni per un confronto "
            f"(trovate: {len(evaluations)}).{_C.RESET}",
            file=sys.stderr,
        )
        return

    # --- Selezione valutazione A ---
    labels_a = []
    for fp, d, pl, md in evaluations:
        run_n = fp.stem.split("_")[0]
        scenario_id = d.get("scenario_id", fp.parent.name)
        overall = d.get("overall_score", "?")
        labels_a.append(
            f"{_C.DIM}[{pl}/{md}]{_C.RESET} "
            f"{scenario_id} #{run_n} \u2014 overall: {overall}"
        )
    labels_a.append("Indietro")
    idx_a = _ask_choice("Seleziona valutazione A:", labels_a)
    if idx_a == len(evaluations):
        return

    fp_a, eval_a, pl_a, md_a = evaluations[idx_a]
    run_n_a = fp_a.stem.split("_")[0]
    scenario_a = eval_a.get("scenario_id", fp_a.parent.name)
    label_a = f"[{pl_a}/{md_a}] {scenario_a} #{run_n_a}"

    # --- Selezione valutazione B (senza A) ---
    remaining = [e for i, e in enumerate(evaluations) if i != idx_a]
    labels_b = []
    for fp, d, pl, md in remaining:
        run_n = fp.stem.split("_")[0]
        scenario_id = d.get("scenario_id", fp.parent.name)
        overall = d.get("overall_score", "?")
        labels_b.append(
            f"{_C.DIM}[{pl}/{md}]{_C.RESET} "
            f"{scenario_id} #{run_n} \u2014 overall: {overall}"
        )
    labels_b.append("Indietro")
    idx_b = _ask_choice("Seleziona valutazione B:", labels_b)
    if idx_b == len(remaining):
        return

    fp_b, eval_b, pl_b, md_b = remaining[idx_b]
    run_n_b = fp_b.stem.split("_")[0]
    scenario_b = eval_b.get("scenario_id", fp_b.parent.name)
    label_b = f"[{pl_b}/{md_b}] {scenario_b} #{run_n_b}"

    # --- Genera HTML ---
    comp_dir = base_out / OutputDirs.COMPARISONS
    comp_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = comp_dir / f"{timestamp}.html"

    result = generate_comparison_html(
        eval_a=eval_a,
        eval_b=eval_b,
        label_a=label_a,
        label_b=label_b,
        output_path=output_path,
    )

    print(f"\n  {_C.GREEN}Confronto generato:{_C.RESET}")
    print(f"  {_C.DIM}{result}{_C.RESET}")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def _show_dashboard(base_out: Path, scenarios_dir: Path) -> None:
    """Mostra una tabella riassuntiva per ogni combinazione (prompt, modello)."""
    data = services.get_dashboard_data(base_out)

    if not data:
        print(f"\n  {_C.DIM}Nessuna run trovata in {base_out}/{_C.RESET}")
        return

    # Stampa tabelle
    print(f"\n{_C.CYAN}{'='*50}")
    print(f"  Stato run")
    print(f"{'='*50}{_C.RESET}")

    for (pl, md), scenarios in sorted(data.items()):
        print(f"\n  {_C.WHITE}{pl}{_C.RESET} / {_C.CYAN}{md}{_C.RESET}")

        # Calcola larghezza colonna scenario
        scenario_ids = sorted(scenarios.keys())
        max_scen = max(len(s) for s in scenario_ids) if scenario_ids else 8
        max_scen = max(max_scen, 8)  # minimo "Scenario"

        hdr = (
            f"  {_C.DIM}\u250c{'─' * (max_scen + 2)}"
            f"\u252c{'─' * 6}\u252c{'─' * 6}\u252c{'─' * 6}\u252c{'─' * 9}\u2510{_C.RESET}"
        )
        row_sep = (
            f"  {_C.DIM}\u251c{'─' * (max_scen + 2)}"
            f"\u253c{'─' * 6}\u253c{'─' * 6}\u253c{'─' * 6}\u253c{'─' * 9}\u2524{_C.RESET}"
        )
        footer = (
            f"  {_C.DIM}\u2514{'─' * (max_scen + 2)}"
            f"\u2534{'─' * 6}\u2534{'─' * 6}\u2534{'─' * 6}\u2534{'─' * 9}\u2518{_C.RESET}"
        )

        print(hdr)
        print(
            f"  {_C.DIM}\u2502{_C.RESET} {'Scenario':<{max_scen}} "
            f"{_C.DIM}\u2502{_C.RESET} Conv "
            f"{_C.DIM}\u2502{_C.RESET} Reqs "
            f"{_C.DIM}\u2502{_C.RESET} Eval "
            f"{_C.DIM}\u2502{_C.RESET} Score   "
            f"{_C.DIM}\u2502{_C.RESET}"
        )
        print(row_sep)

        for sid in scenario_ids:
            info = scenarios[sid]
            score_str = f"{info['score']:.1f}" if info["score"] is not None else " -  "
            sc = _score_color(info["score"]) if info["score"] is not None else _C.DIM
            print(
                f"  {_C.DIM}\u2502{_C.RESET} {sid:<{max_scen}} "
                f"{_C.DIM}\u2502{_C.RESET} {info['conv']:>4} "
                f"{_C.DIM}\u2502{_C.RESET} {info['reqs']:>4} "
                f"{_C.DIM}\u2502{_C.RESET} {info['evals']:>4} "
                f"{_C.DIM}\u2502{_C.RESET} {sc}{score_str:>7}{_C.RESET} "
                f"{_C.DIM}\u2502{_C.RESET}"
            )

        print(footer)


# ---------------------------------------------------------------------------
# Loop principale
# ---------------------------------------------------------------------------


def _run_interactive(args: argparse.Namespace, config: AzureOpenAIConfig) -> None:
    # Banner
    print(f"\n{_C.CYAN}{'='*50}")
    print(f"  Interview Evaluator")
    print(f"{'='*50}{_C.RESET}")
    print(f"{_C.DIM}Endpoint: {config.endpoint}{_C.RESET}")

    base_out = Path(args.output_dir)
    base_out.mkdir(parents=True, exist_ok=True)

    prompts_dir = Path(__file__).resolve().parent / "prompts"
    scenarios_dir = Path(args.scenarios_dir)

    log_level = _LOG_VERBOSE

    # === Loop principale ===
    while True:
        print(f"\n{_C.DIM}{'─'*50}{_C.RESET}")
        print(
            f"  {_C.YELLOW}Output:{_C.RESET} {base_out}  "
            f"{_C.DIM}|{_C.RESET}  "
            f"{_C.YELLOW}Log:{_C.RESET} {log_level}"
        )

        main_choice = _ask_choice(
            "Menu principale:",
            [
                "Nuova pipeline (Simula \u2192 Estrai \u2192 Valuta)",
                "Stato run",
                "Confronta valutazioni",
                "Step singolo",
                "Impostazioni",
                "Esci",
            ],
        )

        # --- Esci ---
        if main_choice == 5:
            print(f"\n{_C.CYAN}Arrivederci.{_C.RESET}")
            return

        # ===============================================================
        # Nuova pipeline (Simula → Estrai → Valuta)
        # ===============================================================
        if main_choice == 0:
            scenarios = _load_scenarios(scenarios_dir)
            if not scenarios:
                print(
                    f"\n  {_C.YELLOW}Nessuno scenario trovato in {scenarios_dir}/.{_C.RESET}",
                    file=sys.stderr,
                )
                continue

            sel = _select_interviewer(prompts_dir)
            if sel is None:
                continue
            prompt_label, interviewer_prompt = sel

            labels = [
                f"{s.get('id', '?')} \u2014 {s.get('name', 'N/A')}"
                for s in scenarios
            ]
            labels.append("Indietro")
            idx = _ask_choice("Seleziona scenario:", labels)
            if idx == len(scenarios):
                continue
            scenario = scenarios[idx]

            # Selezione modelli per ogni fase
            print(f"\n{_C.CYAN}Configurazione modelli per la pipeline:{_C.RESET}")
            sim_model = _select_model("simulazione")
            if sim_model is None:
                continue
            ext_model = _select_model("estrazione")
            if ext_model is None:
                continue
            eval_model = _select_model("valutazione")
            if eval_model is None:
                continue

            print(
                f"\n  {_C.DIM}Pipeline: {sim_model} \u2192 {ext_model} \u2192 {eval_model}{_C.RESET}"
            )

            sim_config = replace(config, deployment=sim_model)
            ext_config = replace(config, deployment=ext_model)
            eval_config = replace(config, deployment=eval_model)

            run = _run_path(base_out, prompt_label, sim_model)

            # Fase 1: Simulazione
            print(f"\n{_C.MAGENTA}\u2501\u2501 Fase 1/3: Simulazione ({sim_model}) \u2501\u2501{_C.RESET}")
            conv_data, run_num = _run_simulation(
                scenario=scenario,
                interviewer_prompt=interviewer_prompt,
                prompt_label=prompt_label,
                prompts_dir=prompts_dir,
                run=run,
                config=sim_config,
                args=args,
                log_level=log_level,
            )
            if conv_data is None:
                continue

            # Fase 2: Estrazione requisiti (stesso run_number)
            print(f"\n{_C.MAGENTA}\u2501\u2501 Fase 2/3: Estrazione ({ext_model}) \u2501\u2501{_C.RESET}")
            req_data = _run_extraction(
                conv_data=conv_data,
                prompts_dir=prompts_dir,
                run=run,
                config=ext_config,
                args=args,
                log_level=log_level,
                run_number=run_num,
            )
            if req_data is None:
                continue

            # Fase 3: Valutazione requisiti (stesso run_number)
            print(f"\n{_C.MAGENTA}\u2501\u2501 Fase 3/3: Valutazione ({eval_model}) \u2501\u2501{_C.RESET}")
            _run_evaluation(
                requirements_data=req_data,
                scenario=scenario,
                prompts_dir=prompts_dir,
                run=run,
                config=eval_config,
                args=args,
                log_level=log_level,
                run_number=run_num,
            )

        # ===============================================================
        # Stato run (Dashboard)
        # ===============================================================
        elif main_choice == 1:
            _show_dashboard(base_out, scenarios_dir)

        # ===============================================================
        # Confronta valutazioni
        # ===============================================================
        elif main_choice == 2:
            _run_comparison(base_out)

        # ===============================================================
        # Step singolo (sub-menu)
        # ===============================================================
        elif main_choice == 3:
            step_choice = _ask_choice(
                f"{_C.YELLOW}Step singolo >{_C.RESET}",
                [
                    "Simula intervista",
                    "Estrai requisiti",
                    "Valuta requisiti",
                    "Indietro",
                ],
            )
            if step_choice == 3:
                continue

            # --- Simula intervista ---
            if step_choice == 0:
                scenarios = _load_scenarios(scenarios_dir)
                if not scenarios:
                    print(
                        f"\n  {_C.YELLOW}Nessuno scenario trovato in {scenarios_dir}/. "
                        f"Crea almeno un file .json nella directory scenari.{_C.RESET}",
                        file=sys.stderr,
                    )
                    continue

                model = _select_model("simulazione")
                if model is None:
                    continue

                sel = _select_interviewer(prompts_dir)
                if sel is None:
                    continue
                prompt_label, interviewer_prompt = sel

                labels = [
                    f"{s.get('id', '?')} \u2014 {s.get('name', 'N/A')}"
                    for s in scenarios
                ]
                labels.append("Indietro")
                idx = _ask_choice("Seleziona scenario:", labels)
                if idx == len(scenarios):
                    continue

                step_config = replace(config, deployment=model)
                run = _run_path(base_out, prompt_label, model)

                _run_simulation(
                    scenario=scenarios[idx],
                    interviewer_prompt=interviewer_prompt,
                    prompt_label=prompt_label,
                    prompts_dir=prompts_dir,
                    run=run,
                    config=step_config,
                    args=args,
                    log_level=log_level,
                )[0]  # ignora run_number

            # --- Estrai requisiti ---
            elif step_choice == 1:
                conversations = _scan_conversations(base_out)
                if not conversations:
                    print(
                        f"\n  {_C.YELLOW}Nessuna conversazione trovata in {base_out}/. "
                        f"Esegui prima una simulazione.{_C.RESET}",
                        file=sys.stderr,
                    )
                    continue

                model = _select_model("estrazione")
                if model is None:
                    continue

                labels = []
                for fp, d, pl, md in conversations:
                    run_n = fp.stem.split("_")[0]
                    labels.append(
                        f"{_C.DIM}[{pl}/{md}]{_C.RESET} "
                        f"{d.get('scenario_id', '?')} #{run_n} \u2014 {d.get('total_turns', '?')} turni"
                    )
                labels.append("Indietro")
                idx = _ask_choice("Seleziona conversazione:", labels)
                if idx == len(conversations):
                    continue

                conv_file, conv_data, pl, md = conversations[idx]
                # {scenario_id}/ → conversations/ → {model}/
                run = conv_file.parent.parent.parent

                step_config = replace(config, deployment=model)
                _run_extraction(
                    conv_data=conv_data,
                    prompts_dir=prompts_dir,
                    run=run,
                    config=step_config,
                    args=args,
                    log_level=log_level,
                )

            # --- Valuta requisiti ---
            elif step_choice == 2:
                req_files = _scan_requirements(base_out)
                if not req_files:
                    print(
                        f"\n  {_C.YELLOW}Nessun file requisiti trovato in {base_out}/. "
                        f"Esegui prima un'estrazione.{_C.RESET}",
                        file=sys.stderr,
                    )
                    continue

                model = _select_model("valutazione")
                if model is None:
                    continue

                labels = []
                for fp, d, pl, md in req_files:
                    run_n = fp.stem.split("_")[0]
                    labels.append(
                        f"{_C.DIM}[{pl}/{md}]{_C.RESET} "
                        f"{d.get('scenario_id', '?')} #{run_n} \u2014 {len(d.get('requirements', []))} requisiti"
                    )
                labels.append("Indietro")
                idx = _ask_choice("Seleziona file requisiti:", labels)
                if idx == len(req_files):
                    continue

                req_file_path, req_data, pl, md = req_files[idx]
                # {scenario_id}/ → requirements/ → {model}/
                run = req_file_path.parent.parent.parent

                scenario = _find_scenario_for_id(
                    req_data.get("scenario_id", ""),
                    scenarios_dir,
                )
                if scenario is None:
                    print(
                        f"\n  {_C.RED}Scenario non trovato per i requisiti "
                        f"(scenario_id: {req_data.get('scenario_id', '?')}).{_C.RESET}",
                        file=sys.stderr,
                    )
                    continue

                step_config = replace(config, deployment=model)
                _run_evaluation(
                    requirements_data=req_data,
                    scenario=scenario,
                    prompts_dir=prompts_dir,
                    run=run,
                    config=step_config,
                    args=args,
                    log_level=log_level,
                )

        # ===============================================================
        # Impostazioni
        # ===============================================================
        elif main_choice == 4:
            settings_choice = _ask_choice(
                f"{_C.YELLOW}Impostazioni >{_C.RESET}",
                [
                    f"Livello log            {_C.DIM}attuale: {log_level}{_C.RESET}",
                    "Svuota cartella output",
                    "Indietro",
                ],
            )
            if settings_choice == 2:
                continue

            if settings_choice == 0:
                log_level = _LOG_INFO if log_level == _LOG_VERBOSE else _LOG_VERBOSE
                print(f"\n  {_C.GREEN}Livello log: {log_level}{_C.RESET}")

            elif settings_choice == 1:
                _clean_output(base_out)


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
            f"{_C.RED}[interview-evaluator] Errore configurazione: {exc}{_C.RESET}",
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
