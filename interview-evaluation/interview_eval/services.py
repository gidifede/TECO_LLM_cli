"""Service layer condiviso: logica di business senza dipendenze di presentazione.

Tutte le funzioni restituiscono dati strutturati; nessun print() o codice ANSI.
Usato sia dalla CLI (interactive.py) sia dalla web app (web/).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .chat_simulator import simulate_interview
from .config import AzureOpenAIConfig
from .evaluation import evaluate_requirements
from .paths import OutputDirs, PromptDirs, PromptFiles
from .requirements_extraction import extract_requirements

# ---------------------------------------------------------------------------
# Modelli disponibili (condivisi tra CLI e web)
# ---------------------------------------------------------------------------

AVAILABLE_MODELS: list[str] = [
    "gpt-4.1",
    "gpt-5.1",
    "gpt-5.2",
    "gpt-5.1-chat",
    "gpt-5-mini",
]

# ---------------------------------------------------------------------------
# Caricamento dati
# ---------------------------------------------------------------------------


def load_scenarios(scenarios_dir: Path) -> list[dict]:
    """Carica tutti i file JSON dalla directory scenari."""
    scenarios: list[dict] = []
    if not scenarios_dir.is_dir():
        return scenarios
    for f in sorted(scenarios_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_file"] = str(f)
            scenarios.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return scenarios


def load_interviewer_prompts(prompts_dir: Path) -> list[tuple[str, str]]:
    """Elenca i prompt interviewer disponibili.

    Returns:
        Lista di (label, contenuto) -- label e il nome file senza estensione.
    """
    interviewers_dir = prompts_dir / PromptDirs.INTERVIEWERS
    if not interviewers_dir.is_dir():
        return []
    prompts: list[tuple[str, str]] = []
    for f in sorted(interviewers_dir.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
            prompts.append((f.stem, content))
        except OSError:
            continue
    return prompts


def load_prompts(prompts_dir: Path) -> tuple[str, str, str]:
    """Carica stakeholder, requirements ed evaluator. Solleva errore se mancanti."""
    stakeholder_file = prompts_dir / PromptFiles.STAKEHOLDER
    requirements_file = prompts_dir / PromptFiles.REQUIREMENTS
    evaluator_file = prompts_dir / PromptFiles.EVALUATOR

    for f in [stakeholder_file, requirements_file, evaluator_file]:
        if not f.is_file():
            raise FileNotFoundError(f"Prompt non trovato: {f}")

    return (
        stakeholder_file.read_text(encoding="utf-8"),
        requirements_file.read_text(encoding="utf-8"),
        evaluator_file.read_text(encoding="utf-8"),
    )


# ---------------------------------------------------------------------------
# Scansione artefatti
# ---------------------------------------------------------------------------


def scan_conversations(base_out: Path) -> list[tuple[Path, dict, str, str]]:
    """Scansiona tutte le conversazioni nella gerarchia output.

    Returns:
        Lista di (file_path, data, prompt_label, model).
    """
    results: list[tuple[Path, dict, str, str]] = []
    if not base_out.is_dir():
        return results
    for conv_file in sorted(
        base_out.rglob(f"{OutputDirs.CONVERSATIONS}/*/*_conversation.json")
    ):
        try:
            data = json.loads(conv_file.read_text(encoding="utf-8"))
            scenario_dir = conv_file.parent
            conv_dir = scenario_dir.parent
            model_dir = conv_dir.parent
            prompt_dir = model_dir.parent
            results.append((conv_file, data, prompt_dir.name, model_dir.name))
        except (json.JSONDecodeError, OSError):
            continue
    return results


def scan_requirements(base_out: Path) -> list[tuple[Path, dict, str, str]]:
    """Scansiona tutti i file requisiti nella gerarchia output.

    Returns:
        Lista di (file_path, data, prompt_label, model).
    """
    results: list[tuple[Path, dict, str, str]] = []
    if not base_out.is_dir():
        return results
    for req_file in sorted(
        base_out.rglob(f"{OutputDirs.REQUIREMENTS}/*/*_requirements.json")
    ):
        try:
            data = json.loads(req_file.read_text(encoding="utf-8"))
            scenario_dir = req_file.parent
            req_dir = scenario_dir.parent
            model_dir = req_dir.parent
            prompt_dir = model_dir.parent
            results.append((req_file, data, prompt_dir.name, model_dir.name))
        except (json.JSONDecodeError, OSError):
            continue
    return results


def scan_evaluations(base_out: Path) -> list[tuple[Path, dict, str, str]]:
    """Scansiona tutti i file valutazione nella gerarchia output.

    Returns:
        Lista di (file_path, data, prompt_label, model).
    """
    results: list[tuple[Path, dict, str, str]] = []
    if not base_out.is_dir():
        return results
    for eval_file in sorted(
        base_out.rglob(f"{OutputDirs.EVALUATIONS}/*/*_evaluation.json")
    ):
        try:
            data = json.loads(eval_file.read_text(encoding="utf-8"))
            scenario_dir = eval_file.parent
            eval_dir = scenario_dir.parent
            model_dir = eval_dir.parent
            prompt_dir = model_dir.parent
            results.append((eval_file, data, prompt_dir.name, model_dir.name))
        except (json.JSONDecodeError, OSError):
            continue
    return results


def find_scenario_for_id(
    scenario_id: str,
    scenarios_dir: Path,
    fallback_data: dict | None = None,
) -> dict | None:
    """Trova lo scenario corrispondente a un ID."""
    scenarios = load_scenarios(scenarios_dir)
    for s in scenarios:
        if s.get("id") == scenario_id:
            return s
    if fallback_data and fallback_data.get("project_idea"):
        return {
            "id": scenario_id,
            "name": fallback_data.get("scenario_name", ""),
            "project_idea": fallback_data["project_idea"],
            "topic": fallback_data.get("topic", ""),
            "extracted_reqs": [],
        }
    return None


# ---------------------------------------------------------------------------
# Path e directory
# ---------------------------------------------------------------------------


def run_path(base_out: Path, prompt_label: str, model: str) -> Path:
    """Costruisce il path di output per una run: base_out/{prompt_label}/{model}/."""
    return base_out / prompt_label / model


def ensure_run_dirs(run: Path) -> None:
    """Crea le sottodirectory di output per una run."""
    for subdir in OutputDirs.all_subdirs():
        (run / subdir).mkdir(parents=True, exist_ok=True)


def next_number(directory: Path, suffix: str) -> int:
    """Trova il prossimo numero incrementale per file {N}_{suffix}.json."""
    if not directory.is_dir():
        return 1
    max_n = 0
    for f in directory.glob(f"*_{suffix}.json"):
        parts = f.stem.split("_", 1)
        if parts[0].isdigit():
            max_n = max(max_n, int(parts[0]))
    return max_n + 1


# ---------------------------------------------------------------------------
# Orchestrazione (senza output console)
# ---------------------------------------------------------------------------


def run_simulation(
    scenario: dict,
    interviewer_prompt: str,
    prompt_label: str,
    prompts_dir: Path,
    run: Path,
    config: AzureOpenAIConfig,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    run_number: int | None = None,
    verbose: bool = False,
) -> tuple[dict | None, int]:
    """Esegue la simulazione e salva il risultato.

    Returns:
        (conv_data, run_number) oppure (None, 0) in caso di errore.
    """
    stakeholder_prompt, _, _ = load_prompts(prompts_dir)

    scenario_id = scenario.get("id", "unknown")

    ensure_run_dirs(run)
    conv_scenario_dir = run / OutputDirs.CONVERSATIONS / scenario_id
    conv_scenario_dir.mkdir(parents=True, exist_ok=True)
    num = run_number if run_number is not None else next_number(
        conv_scenario_dir, "conversation"
    )

    conv_log = simulate_interview(
        scenario=scenario,
        interviewer_prompt=interviewer_prompt,
        stakeholder_prompt=stakeholder_prompt,
        config=config,
        temperature=temperature,
        max_tokens=max_tokens,
        max_turns=50,
        verbose=verbose,
    )

    conv_data = conv_log.to_dict()
    conv_data["interviewer_prompt"] = prompt_label

    conv_file = conv_scenario_dir / f"{num}_conversation.json"
    conv_file.write_text(
        json.dumps(conv_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return conv_data, num


def run_extraction(
    conv_data: dict,
    prompts_dir: Path,
    run: Path,
    config: AzureOpenAIConfig,
    temperature: float = 0.7,
    run_number: int | None = None,
    verbose: bool = False,
) -> dict | None:
    """Esegue l'estrazione requisiti da una conversazione salvata.

    Returns:
        output_data dict oppure None in caso di errore.
    """
    _, requirements_prompt, _ = load_prompts(prompts_dir)

    scenario_id = conv_data.get("scenario_id", "unknown")

    ensure_run_dirs(run)
    req_scenario_dir = run / OutputDirs.REQUIREMENTS / scenario_id
    req_scenario_dir.mkdir(parents=True, exist_ok=True)
    num = run_number if run_number is not None else next_number(
        req_scenario_dir, "requirements"
    )

    result = extract_requirements(
        conversation_data=conv_data,
        requirements_prompt=requirements_prompt,
        config=config,
        temperature=temperature,
        max_tokens=16384,
        verbose=verbose,
    )

    if result["status"] == "error":
        if result.get("raw_text"):
            raw_file = req_scenario_dir / f"{num}_requirements_RAW.txt"
            raw_file.write_text(result["raw_text"], encoding="utf-8")
        return None

    requirements = result["requirements"]

    output_data = {
        "scenario_id": scenario_id,
        "source_conversation": f"{scenario_id}/{num}_conversation.json",
        "extraction_model": config.deployment,
        "extraction_tokens": result.get("extraction_tokens", 0),
        "interview": {
            "interviewer_prompt": conv_data.get("interviewer_prompt"),
            "interviewer_model": conv_data.get("interviewer_model"),
            "stakeholder_model": conv_data.get("stakeholder_model"),
            "total_turns": conv_data.get("total_turns"),
            "total_tokens": conv_data.get("total_tokens"),
            "completed_naturally": conv_data.get("completed_naturally"),
            "avg_turn_time": conv_data.get("avg_turn_time"),
            "avg_interviewer_time": conv_data.get("avg_interviewer_time"),
            "avg_stakeholder_time": conv_data.get("avg_stakeholder_time"),
        },
        "requirements": requirements,
    }

    req_file = req_scenario_dir / f"{num}_requirements.json"
    req_file.write_text(
        json.dumps(output_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return output_data


def run_evaluation(
    requirements_data: dict,
    scenario: dict,
    prompts_dir: Path,
    run: Path,
    config: AzureOpenAIConfig,
    temperature: float = 0.7,
    run_number: int | None = None,
    verbose: bool = False,
) -> dict | None:
    """Esegue la valutazione dei requisiti estratti.

    Returns:
        evaluation dict oppure None in caso di errore.
    """
    _, _, evaluator_prompt = load_prompts(prompts_dir)

    requirements = requirements_data.get("requirements", [])
    scenario_id = scenario.get(
        "id", requirements_data.get("scenario_id", "unknown")
    )

    ensure_run_dirs(run)
    eval_scenario_dir = run / OutputDirs.EVALUATIONS / scenario_id
    eval_scenario_dir.mkdir(parents=True, exist_ok=True)
    num = run_number if run_number is not None else next_number(
        eval_scenario_dir, "evaluation"
    )

    result = evaluate_requirements(
        requirements=requirements,
        scenario=scenario,
        evaluator_prompt=evaluator_prompt,
        config=config,
        temperature=temperature,
        max_tokens=16384,
        verbose=verbose,
    )

    if result["status"] == "error":
        if result.get("raw_text"):
            raw_file = eval_scenario_dir / f"{num}_evaluation_RAW.txt"
            raw_file.write_text(result["raw_text"], encoding="utf-8")
        return None

    evaluation = result["evaluation"]

    evaluation["evaluation_model"] = config.deployment
    evaluation["source_requirements"] = f"{scenario_id}/{num}_requirements.json"
    evaluation["lineage"] = {
        "source_conversation": requirements_data.get("source_conversation"),
        "extraction_model": requirements_data.get("extraction_model"),
        "interview": requirements_data.get("interview"),
    }

    eval_file = eval_scenario_dir / f"{num}_evaluation.json"
    eval_file.write_text(
        json.dumps(evaluation, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return evaluation


# ---------------------------------------------------------------------------
# Dashboard data
# ---------------------------------------------------------------------------


def get_dashboard_data(
    base_out: Path,
) -> dict[tuple[str, str], dict[str, dict]]:
    """Aggrega dati per la dashboard per (prompt_label, model, scenario).

    Returns:
        {(prompt, model): {scenario_id: {"conv": N, "reqs": N, "evals": N, "score": float|None}}}
    """
    conversations = scan_conversations(base_out)
    requirements = scan_requirements(base_out)
    evaluations = scan_evaluations(base_out)

    data: dict[tuple[str, str], dict[str, dict]] = defaultdict(
        lambda: defaultdict(
            lambda: {"conv": 0, "reqs": 0, "evals": 0, "score": None}
        )
    )

    for fp, _, pl, md in conversations:
        scenario_id = fp.parent.name
        data[(pl, md)][scenario_id]["conv"] += 1

    for fp, _, pl, md in requirements:
        scenario_id = fp.parent.name
        data[(pl, md)][scenario_id]["reqs"] += 1

    for fp, d, pl, md in evaluations:
        scenario_id = fp.parent.name
        entry = data[(pl, md)][scenario_id]
        entry["evals"] += 1
        score = d.get("overall_score")
        if isinstance(score, (int, float)):
            entry["score"] = score

    return dict(data)
