"""Estrazione requisiti dalla conversazione usando il prompt requirements_latest."""

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
    # Trova il delimitatore JSON che appare prima nel testo
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


def extract_requirements(
    conversation_data: dict,
    requirements_prompt: str,
    config: AzureOpenAIConfig,
    temperature: float = 0.7,
    max_tokens: int = 16384,
    verbose: bool = False,
) -> dict:
    """Estrae requisiti dalla conversazione usando il prompt requirements_latest.

    Sostituisce {{chat_history}} e {{project_idea}} nel prompt e invia all'LLM.

    Args:
        conversation_data: dati della conversazione salvata (con campo chat_history)
        requirements_prompt: template del prompt requirements (con placeholder)
        config: configurazione Azure OpenAI
        temperature: temperatura per la generazione
        max_tokens: max token per risposta
        verbose: se True, stampa dettagli delle chiamate

    Returns:
        {"status": "ok", "requirements": [...], "extraction_tokens": int}
        {"status": "error", "error": "...", "raw_text": "..."|None}
    """
    chat_history = conversation_data.get("chat_history", "")
    project_idea = conversation_data.get("project_idea", "")

    # Sostituisci i placeholder nel prompt
    prompt = requirements_prompt.replace("{{chat_history}}", chat_history)
    prompt = prompt.replace("{{project_idea}}", project_idea)

    if verbose:
        print(f"  [req-extract] Invio a Azure OpenAI...")
        print(f"  [req-extract]   Prompt: {len(prompt)} char")
        print(f"  [req-extract]   chat_history: {len(chat_history)} char")

    try:
        t0 = time.time()
        llm_resp = call_azure_openai(
            config=config,
            user_content=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw_text = llm_resp.content
        elapsed = time.time() - t0

        if verbose:
            print(
                f"  [req-extract] Risposta ricevuta in {elapsed:.1f}s "
                f"({len(raw_text)} char)  —  "
                f"token: {llm_resp.prompt_tokens}+{llm_resp.completion_tokens}"
                f"={llm_resp.total_tokens}"
            )

        if llm_resp.truncated:
            return {
                "status": "error",
                "error": (
                    f"Risposta troncata (max_tokens={max_tokens} "
                    f"insufficienti). Aumentare --max-tokens."
                ),
                "raw_text": raw_text,
            }

        json_str = _extract_json(raw_text)
        requirements = json.loads(json_str)

        # Il prompt restituisce un array JSON di requisiti
        if not isinstance(requirements, list):
            return {
                "status": "error",
                "error": "Il formato restituito non è un array JSON di requisiti",
                "raw_text": raw_text,
            }

        return {
            "status": "ok",
            "requirements": requirements,
            "extraction_tokens": llm_resp.total_tokens,
        }

    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "error": f"Risposta non JSON valida - {exc}",
            "raw_text": raw_text,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "raw_text": None,
        }
