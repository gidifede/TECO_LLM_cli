"""Pipeline: requirements.json → user stories → test cases.

Per ogni requisito:
0. Validazione sintattica (Python) — skip se campi obbligatori mancanti
1. Invia il singolo requisito + prompt US (ac_based / persona_based) → validazione semantica LLM
   - Se status=rejected → registra e passa al prossimo
   - Se status=ok → ottiene user stories JSON
2. Invia le user stories + prompt TC (from_user_stories) → ottiene test cases JSON
"""

import json
import re
import sys
import time
from pathlib import Path

from .config import AzureOpenAIConfig
from .llm import call_azure_openai
from .paths import PromptFiles, OutputDirs

MIN_DESCRIPTION_LENGTH = 20


def _extract_json(text: str) -> str:
    """Estrae il blocco JSON dalla risposta LLM (potrebbe essere in un code block)."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    for start, end in [("{", "}"), ("[", "]")]:
        i = text.find(start)
        if i == -1:
            continue
        depth = 0
        for j in range(i, len(text)):
            if text[j] == start:
                depth += 1
            elif text[j] == end:
                depth -= 1
            if depth == 0:
                return text[i : j + 1]
    return text.strip()


def _serialize_requirement(req: dict) -> str:
    """Serializza un singolo requisito in JSON leggibile per il prompt."""
    fields = {
        "code": req.get("code", ""),
        "title": req.get("title", ""),
        "description": req.get("description", ""),
        "category": req.get("category", ""),
        "priority": req.get("priority", ""),
        "acceptance_criteria": req.get("acceptance_criteria", []),
    }
    return json.dumps(fields, indent=2, ensure_ascii=False)


def extract_personas_context(requirements: list[dict]) -> tuple[str, list[dict]]:
    """Separa i requisiti PERSONAS dal resto e serializza il contesto personas.

    Restituisce:
      (personas_json, non_persona_reqs)
      - personas_json: stringa JSON con l'array delle personas
      - non_persona_reqs: lista dei requisiti filtrati (senza PERSONAS)
    """
    personas: list[dict] = []
    non_persona_reqs: list[dict] = []

    for req in requirements:
        if req.get("category", "").upper() == "PERSONAS":
            personas.append({
                "code": req.get("code", ""),
                "title": req.get("title", ""),
                "description": req.get("description", ""),
                "acceptance_criteria": req.get("acceptance_criteria", []),
            })
        else:
            non_persona_reqs.append(req)

    personas_json = json.dumps(personas, indent=2, ensure_ascii=False)
    return personas_json, non_persona_reqs


def _validate_syntax(req: dict) -> list[str]:
    """Validazione sintattica: controlla campi obbligatori.

    Restituisce lista di problemi trovati (vuota = OK).
    """
    problems: list[str] = []

    code = req.get("code", "").strip()
    if not code:
        problems.append("Campo 'code' mancante o vuoto")

    description = req.get("description", "").strip()
    if not description:
        problems.append("Campo 'description' mancante o vuoto")
    elif len(description) < MIN_DESCRIPTION_LENGTH:
        problems.append(
            f"Campo 'description' troppo corto ({len(description)} caratteri, "
            f"minimo {MIN_DESCRIPTION_LENGTH})"
        )

    criteria = req.get("acceptance_criteria", [])
    if not criteria or not isinstance(criteria, list) or len(criteria) == 0:
        problems.append("Campo 'acceptance_criteria' mancante o vuoto")

    title = req.get("title", "").strip()
    if not title:
        problems.append("Campo 'title' mancante o vuoto")

    return problems


# ---------------------------------------------------------------------------
# Funzioni pubbliche riutilizzabili (usate da run_pipeline e interactive)
# ---------------------------------------------------------------------------


def process_requirement_to_us(
    req: dict,
    system_prompt: str,
    config: AzureOpenAIConfig,
    temperature: float,
    max_tokens: int,
    verbose: bool,
    personas_context: str | None = None,
) -> dict:
    """Singolo requisito → user stories (validazione sintattica + semantica + LLM).

    Restituisce:
      {"status": "ok",       "user_stories": [...]}
      {"status": "rejected", "reasons": [...], "raw_response": dict}
      {"status": "error",    "error": "...", "raw_text": "..."|None}
      {"status": "skipped",  "problems": [...]}
    """
    code = req.get("code", "UNKNOWN")

    # Validazione sintattica
    syntax_problems = _validate_syntax(req)
    if syntax_problems:
        return {"status": "skipped", "problems": syntax_problems}

    # Chiamata LLM
    req_json = _serialize_requirement(req)
    if personas_context is not None:
        user_content = (
            f"## Contesto — Personas del progetto\n\n"
            f"{personas_context}\n\n"
            f"## Requisito da trasformare\n\n"
            f"Valida e trasforma il seguente requisito in user stories:\n\n{req_json}"
        )
    else:
        user_content = (
            f"Valida e trasforma il seguente requisito in user stories:\n\n{req_json}"
        )

    if verbose:
        print(f"  [step 1] Invio a Azure OpenAI...")
        print(f"  [step 1]   Prompt di sistema: {len(system_prompt)} char")
        print(f"  [step 1]   Payload utente:    {len(user_content)} char")

    try:
        t0 = time.time()
        llm_resp = call_azure_openai(
            config=config,
            user_content=user_content,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw_us = llm_resp.content
        elapsed = time.time() - t0

        if verbose:
            print(
                f"  [step 1] Risposta ricevuta in {elapsed:.1f}s ({len(raw_us)} char)"
                f"  —  token: {llm_resp.prompt_tokens}+{llm_resp.completion_tokens}"
                f"={llm_resp.total_tokens}"
            )

        if llm_resp.truncated:
            return {
                "status": "error",
                "error": (
                    f"{code} step 1: risposta troncata (max_tokens={max_tokens} "
                    f"insufficienti). Aumentare --max-tokens."
                ),
                "raw_text": raw_us,
            }

        us_json_str = _extract_json(raw_us)
        response = json.loads(us_json_str)

        # Gestione status wrapper
        status = response.get("status", "ok") if isinstance(response, dict) else "ok"

        if status == "rejected":
            reasons = response.get("reasons", ["Motivo non specificato"])
            return {
                "status": "rejected",
                "reasons": reasons,
                "raw_response": response,
            }

        # status == "ok": estrai le user stories
        if isinstance(response, dict) and "user_stories" in response:
            user_stories = response["user_stories"]
        elif isinstance(response, list):
            user_stories = response
        else:
            user_stories = [response]

        return {"status": "ok", "user_stories": user_stories}

    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "error": f"{code} step 1: risposta non JSON valida - {exc}",
            "raw_text": raw_us,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": f"{code} step 1: {exc}",
            "raw_text": None,
        }


def process_us_to_tc(
    user_stories: list[dict],
    system_prompt: str,
    config: AzureOpenAIConfig,
    temperature: float,
    max_tokens: int,
    verbose: bool,
    requirement_ac: list[str] | None = None,
) -> dict:
    """Lista di user stories → test cases (chiamata LLM).

    Se ``requirement_ac`` è fornito, viene aggiunto al messaggio utente
    come contesto di tracciabilità per il campo ``traced_criteria``.

    Restituisce:
      {"status": "ok",       "test_cases": [...]}
      {"status": "rejected", "reasons": [...]}
      {"status": "error",    "error": "...", "raw_text": "..."|None}
    """
    user_content = (
        f"Genera i test cases per le seguenti user stories:\n\n"
        f"{json.dumps(user_stories, indent=2, ensure_ascii=False)}"
    )

    if requirement_ac:
        ac_lines = "\n".join(
            f"AC-{i}: {ac}" for i, ac in enumerate(requirement_ac, 1)
        )
        user_content += (
            f"\n\n## Acceptance criteria del requisito originale\n\n"
            f"{ac_lines}"
        )

    if verbose:
        print(f"  [step 2] Invio a Azure OpenAI...")
        print(f"  [step 2]   Prompt di sistema: {len(system_prompt)} char")
        print(f"  [step 2]   Payload utente:    {len(user_content)} char")

    try:
        t0 = time.time()
        llm_resp = call_azure_openai(
            config=config,
            user_content=user_content,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw_tc = llm_resp.content
        elapsed = time.time() - t0

        if verbose:
            print(
                f"  [step 2] Risposta ricevuta in {elapsed:.1f}s ({len(raw_tc)} char)"
                f"  —  token: {llm_resp.prompt_tokens}+{llm_resp.completion_tokens}"
                f"={llm_resp.total_tokens}"
            )

        if llm_resp.truncated:
            return {
                "status": "error",
                "error": (
                    f"step 2: risposta troncata (max_tokens={max_tokens} "
                    f"insufficienti). Aumentare --max-tokens."
                ),
                "raw_text": raw_tc,
            }

        tc_json_str = _extract_json(raw_tc)
        response = json.loads(tc_json_str)

        # Gestione wrapper status (nuovo formato)
        if isinstance(response, dict):
            status = response.get("status", "ok")
            if status == "rejected":
                reasons = response.get("reasons", ["Motivo non specificato"])
                return {"status": "rejected", "reasons": reasons}
            # status == "ok": estrai results
            test_cases = response.get("results", response.get("test_cases", []))
        elif isinstance(response, list):
            # Retrocompatibilita: il modello ha restituito direttamente la lista
            test_cases = response
        else:
            test_cases = [response]

        return {"status": "ok", "test_cases": test_cases}

    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "error": f"step 2: risposta non JSON valida - {exc}",
            "raw_text": raw_tc,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": f"step 2: {exc}",
            "raw_text": None,
        }


def process_requirement_to_tc_direct(
    req: dict,
    system_prompt: str,
    config: AzureOpenAIConfig,
    temperature: float,
    max_tokens: int,
    verbose: bool,
) -> dict:
    """Singolo requisito → test cases diretti (validazione + LLM, senza user stories).

    Restituisce:
      {"status": "ok",       "test_cases": [...]}
      {"status": "rejected", "reasons": [...]}
      {"status": "skipped",  "problems": [...]}
      {"status": "error",    "error": "...", "raw_text": "..."|None}
    """
    code = req.get("code", "UNKNOWN")

    # Validazione sintattica
    syntax_problems = _validate_syntax(req)
    if syntax_problems:
        return {"status": "skipped", "problems": syntax_problems}

    # Chiamata LLM
    req_json = _serialize_requirement(req)
    user_content = (
        f"Valida il seguente requisito e genera i test cases:\n\n{req_json}"
    )

    if verbose:
        print(f"  [direct] Invio a Azure OpenAI...")
        print(f"  [direct]   Prompt di sistema: {len(system_prompt)} char")
        print(f"  [direct]   Payload utente:    {len(user_content)} char")

    try:
        t0 = time.time()
        llm_resp = call_azure_openai(
            config=config,
            user_content=user_content,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw_tc = llm_resp.content
        elapsed = time.time() - t0

        if verbose:
            print(
                f"  [direct] Risposta ricevuta in {elapsed:.1f}s ({len(raw_tc)} char)"
                f"  —  token: {llm_resp.prompt_tokens}+{llm_resp.completion_tokens}"
                f"={llm_resp.total_tokens}"
            )

        if llm_resp.truncated:
            return {
                "status": "error",
                "error": (
                    f"{code} direct: risposta troncata (max_tokens={max_tokens} "
                    f"insufficienti). Aumentare --max-tokens."
                ),
                "raw_text": raw_tc,
            }

        tc_json_str = _extract_json(raw_tc)
        response = json.loads(tc_json_str)

        # Gestione wrapper status
        if isinstance(response, dict):
            status = response.get("status", "ok")
            if status == "rejected":
                reasons = response.get("reasons", ["Motivo non specificato"])
                return {"status": "rejected", "reasons": reasons}
            # status == "ok": estrai test_cases
            test_cases = response.get("test_cases", [])
            return {"status": "ok", "test_cases": test_cases}
        elif isinstance(response, list):
            return {"status": "ok", "test_cases": response}
        else:
            return {"status": "ok", "test_cases": [response]}

    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "error": f"{code} direct: risposta non JSON valida - {exc}",
            "raw_text": raw_tc,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": f"{code} direct: {exc}",
            "raw_text": None,
        }


def evaluate_test_cases(
    requirement: dict,
    tc_sets: dict[str, list[dict]],
    chain_metadata: dict[str, dict],
    system_prompt: str,
    config: AzureOpenAIConfig,
    temperature: float,
    max_tokens: int,
    verbose: bool,
) -> dict:
    """Valuta la coerenza dei test cases rispetto al requisito originale.

    Accetta da 2 a 3 set di test cases (chiavi: "direct", "indirect_ac",
    "indirect_persona"). Ogni set deve essere non vuoto.

    Parametri:
      tc_sets: {"direct": [...], "indirect_ac": [...], ...}
      chain_metadata: {"direct": {"label": "...", "naming": "..."}, ...}

    Restituisce:
      {"status": "ok",       "evaluation": {...}}
      {"status": "rejected", "reasons": [...], "raw_response": dict}
      {"status": "error",    "error": "...", "raw_text": "..."|None}
    """
    code = requirement.get("code", "UNKNOWN")

    # Assembla il payload JSON per il prompt
    tc_sets_payload = {}
    for key, tc_list in tc_sets.items():
        meta = chain_metadata.get(key, {})
        tc_sets_payload[key] = {
            "label": meta.get("label", key),
            "naming_convention": meta.get("naming", ""),
            "test_cases": tc_list,
        }

    payload = {
        "requirement": {
            "code": requirement.get("code", ""),
            "title": requirement.get("title", ""),
            "description": requirement.get("description", ""),
            "category": requirement.get("category", ""),
            "priority": requirement.get("priority", ""),
            "acceptance_criteria": requirement.get("acceptance_criteria", []),
        },
        "tc_sets": tc_sets_payload,
    }

    user_content = (
        f"Valuta la coerenza dei seguenti test cases rispetto al requisito.\n"
        f"I set da valutare sono {len(tc_sets)}.\n\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}"
    )

    if verbose:
        print(f"  [eval] Invio a Azure OpenAI...")
        print(f"  [eval]   Prompt di sistema: {len(system_prompt)} char")
        print(f"  [eval]   Payload utente:    {len(user_content)} char")

    try:
        t0 = time.time()
        llm_resp = call_azure_openai(
            config=config,
            user_content=user_content,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw_eval = llm_resp.content
        elapsed = time.time() - t0

        if verbose:
            print(
                f"  [eval] Risposta ricevuta in {elapsed:.1f}s ({len(raw_eval)} char)"
                f"  —  token: {llm_resp.prompt_tokens}+{llm_resp.completion_tokens}"
                f"={llm_resp.total_tokens}"
            )

        if llm_resp.truncated:
            return {
                "status": "error",
                "error": (
                    f"{code} eval: risposta troncata (max_tokens={max_tokens} "
                    f"insufficienti). Aumentare --max-tokens."
                ),
                "raw_text": raw_eval,
            }

        eval_json_str = _extract_json(raw_eval)
        evaluation = json.loads(eval_json_str)

        # Gestione status rejected (validazione input lato LLM)
        if isinstance(evaluation, dict) and evaluation.get("status") == "rejected":
            reasons = evaluation.get("reasons", ["Motivo non specificato"])
            return {
                "status": "rejected",
                "reasons": reasons,
                "raw_response": evaluation,
            }

        return {"status": "ok", "evaluation": evaluation}

    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "error": f"{code} eval: risposta non JSON valida - {exc}",
            "raw_text": raw_eval,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": f"{code} eval: {exc}",
            "raw_text": None,
        }


# ---------------------------------------------------------------------------
# Pipeline batch (orchestratore)
# ---------------------------------------------------------------------------


def run_pipeline(
    requirements_path: str,
    prompts_dir: str,
    output_dir: str,
    config: AzureOpenAIConfig,
    temperature: float = 0.7,
    max_tokens: int = 16384,
    verbose: bool = False,
    limit: int | None = None,
    strategy: str = "ac",
) -> None:
    """Esegue la pipeline completa: requisiti → user stories → test cases."""

    # --- Carica i file ---
    req_path = Path(requirements_path)
    if not req_path.is_file():
        print(f"[pipeline] File requisiti non trovato: {requirements_path}", file=sys.stderr)
        sys.exit(1)

    all_requirements: list[dict] = json.loads(req_path.read_text(encoding="utf-8"))
    if limit is not None:
        requirements = all_requirements[:limit]
        print(f"[pipeline] Caricati {len(all_requirements)} requisiti, elaborazione limitata ai primi {limit}")
    else:
        requirements = all_requirements

    # --- Strategia: estrai personas se necessario ---
    personas_ctx: str | None = None
    if strategy in ("persona", "both"):
        personas_ctx, requirements = extract_personas_context(requirements)
        personas_list = json.loads(personas_ctx)
        print(f"[pipeline] Personas individuate: {len(personas_list)}")
        for p in personas_list:
            print(f"  - {p.get('code', '?')} | {p.get('title', 'N/A')}")
        print(f"[pipeline] Requisiti da elaborare (senza PERSONAS): {len(requirements)}")
        if verbose:
            print(f"[pipeline] Contesto personas JSON:\n{personas_ctx}")

    if strategy == "both":
        print(f"[pipeline] Strategia: entrambe (AC + persona)")
    elif strategy == "persona":
        print(f"[pipeline] Strategia: persona-based")
    else:
        print(f"[pipeline] Strategia: AC-based")

    total = len(requirements)
    print(f"[pipeline] Requisiti da elaborare: {total}")

    prompts_path = Path(prompts_dir)
    prompt_tc_file = prompts_path / PromptFiles.TC_FROM_US
    if not prompt_tc_file.is_file():
        print(f"[pipeline] Prompt non trovato: {prompt_tc_file}", file=sys.stderr)
        sys.exit(1)
    system_prompt_tc = prompt_tc_file.read_text(encoding="utf-8")

    # Determina i passaggi US da eseguire
    # Tupla: (label, prompt_us, us_dir_name, tc_dir_name, personas_ctx)
    if strategy == "both":
        us_passes = [
            ("ac", PromptFiles.US_AC, OutputDirs.US_AC, OutputDirs.TC_FROM_US_AC, None),
            ("persona", PromptFiles.US_PERSONA, OutputDirs.US_PERSONA, OutputDirs.TC_FROM_US_PERSONA, personas_ctx),
        ]
    elif strategy == "persona":
        us_passes = [
            ("persona", PromptFiles.US_PERSONA, OutputDirs.US_PERSONA, OutputDirs.TC_FROM_US_PERSONA, personas_ctx),
        ]
    else:
        us_passes = [
            ("ac", PromptFiles.US_AC, OutputDirs.US_AC, OutputDirs.TC_FROM_US_AC, None),
        ]

    # Verifica che i prompt esistano
    for _, prompt_name, _, _, _ in us_passes:
        prompt_file = prompts_path / prompt_name
        if not prompt_file.is_file():
            print(f"[pipeline] Prompt non trovato: {prompt_file}", file=sys.stderr)
            sys.exit(1)

    # --- Directory di output ---
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # --- Risultati aggregati ---
    all_user_stories: list = []
    all_test_cases: list = []
    errors: list[dict] = []
    rejected: list[dict] = []
    skipped_syntax: list[dict] = []

    for pass_label, prompt_name, us_dir_name, tc_dir_name, pass_personas_ctx in us_passes:
        system_prompt_us = (prompts_path / prompt_name).read_text(encoding="utf-8")
        us_dir = out_path / us_dir_name
        tc_dir = out_path / tc_dir_name
        us_dir.mkdir(parents=True, exist_ok=True)
        tc_dir.mkdir(parents=True, exist_ok=True)

        if len(us_passes) > 1:
            print(f"\n{'='*60}")
            print(f"[pipeline] === Passaggio US: {pass_label} ===")
            print(f"{'='*60}")

        for i, req in enumerate(requirements, 1):
            code = req.get("code", f"REQ-{i}")
            print(f"\n[pipeline] [{i}/{total}] Elaborazione {code} ({pass_label})...")

            # === Step 1: Requisito → User Stories ===
            us_result = process_requirement_to_us(
                req=req,
                system_prompt=system_prompt_us,
                config=config,
                temperature=temperature,
                max_tokens=max_tokens,
                verbose=verbose,
                personas_context=pass_personas_ctx,
            )

            if us_result["status"] == "skipped":
                print(f"  [validazione] SKIP - problemi sintattici:")
                for p in us_result["problems"]:
                    print(f"    - {p}")
                skipped_syntax.append({
                    "requirement_id": code,
                    "problems": us_result["problems"],
                })
                continue

            if us_result["status"] == "rejected":
                print(f"  [step 1] REJECTED dal modello:")
                for r in us_result["reasons"]:
                    print(f"    - {r}")
                raw_response = us_result["raw_response"]
                rejected.append({
                    "requirement_id": raw_response.get("requirement_id", code),
                    "reasons": us_result["reasons"],
                })
                rej_file = us_dir / f"{code}_REJECTED.json"
                rej_file.write_text(
                    json.dumps(raw_response, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                continue

            if us_result["status"] == "error":
                print(f"  [step 1] ERRORE: {us_result['error']}", file=sys.stderr)
                if us_result.get("raw_text"):
                    raw_file = us_dir / f"{code}_user_stories_RAW.txt"
                    raw_file.write_text(us_result["raw_text"], encoding="utf-8")
                errors.append({"code": code, "step": "user_stories", "error": us_result["error"]})
                continue

            # status == "ok"
            user_stories = us_result["user_stories"]
            us_file = us_dir / f"{code}_user_stories.json"
            us_file.write_text(
                json.dumps(user_stories, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            if isinstance(user_stories, list):
                all_user_stories.extend(user_stories)
            else:
                all_user_stories.append(user_stories)

            us_count = len(user_stories) if isinstance(user_stories, list) else 1
            print(f"  [step 1] OK - {us_count} user stories generate")

            # === Step 2: User Stories → Test Cases ===
            tc_result = process_us_to_tc(
                user_stories=user_stories,
                system_prompt=system_prompt_tc,
                config=config,
                temperature=temperature,
                max_tokens=max_tokens,
                verbose=verbose,
                requirement_ac=req.get("acceptance_criteria"),
            )

            if tc_result["status"] == "rejected":
                print(f"  [step 2] REJECTED dal modello:")
                for r in tc_result["reasons"]:
                    print(f"    - {r}")
                errors.append({"code": code, "step": "test_cases", "error": f"Rejected: {'; '.join(tc_result['reasons'])}"})
                continue

            if tc_result["status"] == "error":
                print(f"  [step 2] ERRORE: {tc_result['error']}", file=sys.stderr)
                if tc_result.get("raw_text"):
                    raw_file = tc_dir / f"{code}_test_cases_RAW.txt"
                    raw_file.write_text(tc_result["raw_text"], encoding="utf-8")
                errors.append({"code": code, "step": "test_cases", "error": tc_result["error"]})
                continue

            # status == "ok"
            test_cases = tc_result["test_cases"]
            tc_file = tc_dir / f"{code}_test_cases.json"
            tc_file.write_text(
                json.dumps(test_cases, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            if isinstance(test_cases, list):
                all_test_cases.extend(test_cases)
            else:
                all_test_cases.append(test_cases)

            tc_count = sum(
                len(item.get("test_cases", []))
                for item in (test_cases if isinstance(test_cases, list) else [test_cases])
            )
            print(f"  [step 2] OK - {tc_count} test cases generati")

    if rejected:
        rej_file = out_path / "rejected_requirements.json"
        rej_file.write_text(
            json.dumps(rejected, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    if skipped_syntax:
        skip_file = out_path / "skipped_syntax.json"
        skip_file.write_text(
            json.dumps(skipped_syntax, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    if errors:
        err_file = out_path / "errors.json"
        err_file.write_text(
            json.dumps(errors, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # --- Report finale ---
    elaborated = total - len(skipped_syntax) - len(rejected)
    print(f"\n{'='*60}")
    print(f"[pipeline] Pipeline completata")
    print(f"  Requisiti totali:          {total}")
    print(f"  Skip sintattici:           {len(skipped_syntax)}")
    print(f"  Rifiutati (semantica LLM): {len(rejected)}")
    print(f"  Elaborati con successo:    {elaborated - len(errors)}")
    print(f"  Errori tecnici:            {len(errors)}")
    print(f"  User stories totali:       {len(all_user_stories)}")
    print(f"  Test cases totali:         {len(all_test_cases)}")
    print(f"\n  Output:")
    print(f"    {us_dir}/ (user stories)")
    print(f"    {tc_dir}/ (test cases)")

    if skipped_syntax:
        print(f"\n  Requisiti skippati (sintassi):")
        for s in skipped_syntax:
            print(f"    {s['requirement_id']}: {', '.join(s['problems'])}")

    if rejected:
        print(f"\n  Requisiti rifiutati (semantica):")
        for r in rejected:
            print(f"    {r['requirement_id']}: {'; '.join(r['reasons'])}")

    if errors:
        print(f"\n  Errori tecnici:")
        for err in errors:
            print(f"    {err['code']} ({err['step']}): {err['error']}")

    print(f"{'='*60}")
