"""Valutazione della qualità dei requisiti estratti."""

import json
import re
import time

from .config import AzureOpenAIConfig
from .llm import call_azure_openai


def _extract_json(text: str) -> str:
    """Estrae il blocco JSON dalla risposta LLM (potrebbe essere in un code block)."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    candidates: list[tuple[int, str, str]] = []
    for start, end in [("{", "}"), ("[", "]")]:
        i = text.find(start)
        if i != -1:
            candidates.append((i, start, end))
    candidates.sort()
    for i, start, end in candidates:
        depth = 0
        for j in range(i, len(text)):
            if text[j] == start:
                depth += 1
            elif text[j] == end:
                depth -= 1
            if depth == 0:
                return text[i : j + 1]
    return text.strip()


def evaluate_requirements(
    requirements: list[dict],
    scenario: dict,
    evaluator_prompt: str,
    config: AzureOpenAIConfig,
    temperature: float = 0.7,
    max_tokens: int = 16384,
    verbose: bool = False,
) -> dict:
    """Valuta la qualità dei requisiti estratti.

    Args:
        requirements: lista di requisiti estratti (array di dict)
        scenario: scenario con topic e project_idea
        evaluator_prompt: template del prompt evaluator
        config: configurazione Azure OpenAI
        temperature: temperatura per la generazione
        max_tokens: max token per risposta
        verbose: se True, stampa dettagli delle chiamate

    Returns:
        {"status": "ok", "evaluation": {...}, "eval_tokens": int}
        {"status": "error", "error": "...", "raw_text": "..."|None}
    """
    project_idea = scenario.get("project_idea", "")
    scenario_id = scenario.get("id", "unknown")
    topic = scenario.get("topic", "")

    requirements_json = json.dumps(requirements, indent=2, ensure_ascii=False)

    user_content = (
        f"## Scenario\n\n"
        f"**ID:** {scenario_id}\n"
        f"**Progetto:** {project_idea}\n\n"
        f"## Topic trattato\n\n"
        f"{topic}\n\n"
        f"## Requisiti da valutare ({len(requirements)} requisiti)\n\n"
        f"{requirements_json}\n\n"
        f"Valuta la qualità, quantità e maturità dei requisiti secondo la rubrica. "
        f"Rispondi con il JSON come specificato."
    )

    if verbose:
        print(f"  [eval] Invio a Azure OpenAI...")
        print(f"  [eval]   Prompt di sistema: {len(evaluator_prompt)} char")
        print(f"  [eval]   Payload utente:    {len(user_content)} char")
        print(f"  [eval]   Requisiti:         {len(requirements)}")

    try:
        t0 = time.time()
        llm_resp = call_azure_openai(
            config=config,
            user_content=user_content,
            system_prompt=evaluator_prompt,
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
                    f"Risposta troncata (max_tokens={max_tokens} "
                    f"insufficienti). Aumentare --max-tokens."
                ),
                "raw_text": raw_eval,
            }

        eval_json_str = _extract_json(raw_eval)
        evaluation = json.loads(eval_json_str)

        # Inietta scenario_id se mancante
        if isinstance(evaluation, dict) and "scenario_id" not in evaluation:
            evaluation["scenario_id"] = scenario_id

        return {
            "status": "ok",
            "evaluation": evaluation,
            "eval_tokens": llm_resp.total_tokens,
        }

    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "error": f"Risposta non JSON valida - {exc}",
            "raw_text": raw_eval,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "raw_text": None,
        }
