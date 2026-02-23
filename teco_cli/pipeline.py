"""Pipeline: requirements.json → user stories → test cases.

Per ogni requisito:
0. Validazione sintattica (Python) — skip se campi obbligatori mancanti
1. Invia il singolo requisito + prompt_user_stories → validazione semantica LLM
   - Se status=rejected → registra e passa al prossimo
   - Se status=ok → ottiene user stories JSON
2. Invia le user stories + prompt_test_cases → ottiene test cases JSON
"""

import json
import re
import sys
import time
from pathlib import Path

from .config import AzureOpenAIConfig
from .llm import call_azure_openai

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
    user_content = (
        f"Valida e trasforma il seguente requisito in user stories:\n\n{req_json}"
    )

    if verbose:
        print(f"  [step 1] Invio a Azure OpenAI per validazione + user stories...")

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
            print(f"  [step 1] Risposta ricevuta in {elapsed:.1f}s ({len(raw_us)} char)")

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
) -> dict:
    """Lista di user stories → test cases (chiamata LLM).

    Restituisce:
      {"status": "ok",       "test_cases": [...]}
      {"status": "rejected", "reasons": [...]}
      {"status": "error",    "error": "...", "raw_text": "..."|None}
    """
    user_content = (
        f"Genera i test cases per le seguenti user stories:\n\n"
        f"{json.dumps(user_stories, indent=2, ensure_ascii=False)}"
    )

    if verbose:
        print(f"  [step 2] Invio a Azure OpenAI per test cases...")

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
            print(f"  [step 2] Risposta ricevuta in {elapsed:.1f}s ({len(raw_tc)} char)")

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
        print(f"  [direct] Invio a Azure OpenAI per test cases diretti...")

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
            print(f"  [direct] Risposta ricevuta in {elapsed:.1f}s ({len(raw_tc)} char)")

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
    indirect_tc: list[dict],
    direct_tc: list[dict],
    system_prompt: str,
    config: AzureOpenAIConfig,
    temperature: float,
    max_tokens: int,
    verbose: bool,
) -> dict:
    """Valuta la coerenza dei test cases rispetto al requisito originale.

    Entrambi i set (indirect_tc e direct_tc) sono obbligatori e non vuoti.

    Restituisce:
      {"status": "ok",       "evaluation": {...}}
      {"status": "rejected", "reasons": [...], "raw_response": dict}
      {"status": "error",    "error": "...", "raw_text": "..."|None}
    """
    code = requirement.get("code", "UNKNOWN")

    # Assembla il payload JSON per il prompt
    payload = {
        "requirement": {
            "code": requirement.get("code", ""),
            "title": requirement.get("title", ""),
            "description": requirement.get("description", ""),
            "category": requirement.get("category", ""),
            "priority": requirement.get("priority", ""),
            "acceptance_criteria": requirement.get("acceptance_criteria", []),
        },
        "indirect_tc": indirect_tc,
        "direct_tc": direct_tc,
    }

    user_content = (
        f"Valuta la coerenza dei seguenti test cases rispetto al requisito:\n\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}"
    )

    if verbose:
        print(f"  [eval] Invio a Azure OpenAI per valutazione coerenza...")

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
            print(f"  [eval] Risposta ricevuta in {elapsed:.1f}s ({len(raw_eval)} char)")

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
    total = len(requirements)
    print(f"[pipeline] Requisiti da elaborare: {total}")

    prompts_path = Path(prompts_dir)
    prompt_us_file = prompts_path / "prompt_user_stories.md"
    prompt_tc_file = prompts_path / "prompt_test_cases.md"

    if not prompt_us_file.is_file():
        print(f"[pipeline] Prompt non trovato: {prompt_us_file}", file=sys.stderr)
        sys.exit(1)
    if not prompt_tc_file.is_file():
        print(f"[pipeline] Prompt non trovato: {prompt_tc_file}", file=sys.stderr)
        sys.exit(1)

    system_prompt_us = prompt_us_file.read_text(encoding="utf-8")
    system_prompt_tc = prompt_tc_file.read_text(encoding="utf-8")

    # --- Directory di output ---
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    us_dir = out_path / "user_stories"
    tc_dir = out_path / "test_cases_from_us"
    us_dir.mkdir(exist_ok=True)
    tc_dir.mkdir(exist_ok=True)

    # --- Risultati aggregati ---
    all_user_stories: list = []
    all_test_cases: list = []
    errors: list[dict] = []
    rejected: list[dict] = []
    skipped_syntax: list[dict] = []

    for i, req in enumerate(requirements, 1):
        code = req.get("code", f"REQ-{i}")
        print(f"\n[pipeline] [{i}/{total}] Elaborazione {code}...")

        # === Step 1: Requisito → User Stories ===
        us_result = process_requirement_to_us(
            req=req,
            system_prompt=system_prompt_us,
            config=config,
            temperature=temperature,
            max_tokens=max_tokens,
            verbose=verbose,
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
