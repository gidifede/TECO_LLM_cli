"""Orchestratore conversazione multi-turn tra interviewer e stakeholder simulato."""

import json
import re
import time
from dataclasses import dataclass, field

from .config import AzureOpenAIConfig
from .llm import call_azure_openai_chat


@dataclass
class ConversationTurn:
    turn_number: int
    interviewer_raw: str
    interviewer_message: str
    interviewer_suggestions: list[str]
    is_last_message: bool
    stakeholder_response: str
    interviewer_tokens: int
    stakeholder_tokens: int
    interviewer_elapsed: float = 0.0
    stakeholder_elapsed: float = 0.0


@dataclass
class ConversationLog:
    scenario_id: str
    scenario_name: str
    project_idea: str
    topic: str = ""
    turns: list[ConversationTurn] = field(default_factory=list)
    total_turns: int = 0
    total_tokens: int = 0
    interviewer_model: str = ""
    stakeholder_model: str = ""
    completed_naturally: bool = False

    def _format_chat_history(self) -> str:
        """Formatta la conversazione come chat_history per requirements_latest."""
        lines = []
        for turn in self.turns:
            lines.append(f"- sender='agent' text='{turn.interviewer_message}'")
            if turn.stakeholder_response:
                lines.append(f"- sender='user' text='{turn.stakeholder_response}'")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serializza il log in un dizionario JSON-serializzabile."""
        iv_times = [t.interviewer_elapsed for t in self.turns]
        sh_times = [t.stakeholder_elapsed for t in self.turns if t.stakeholder_elapsed > 0]
        avg_iv = sum(iv_times) / len(iv_times) if iv_times else 0.0
        avg_sh = sum(sh_times) / len(sh_times) if sh_times else 0.0

        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "project_idea": self.project_idea,
            "topic": self.topic,
            "interviewer_model": self.interviewer_model,
            "stakeholder_model": self.stakeholder_model,
            "total_turns": self.total_turns,
            "total_tokens": self.total_tokens,
            "completed_naturally": self.completed_naturally,
            "avg_interviewer_time": round(avg_iv, 2),
            "avg_stakeholder_time": round(avg_sh, 2),
            "avg_turn_time": round(avg_iv + avg_sh, 2),
            "chat_history": self._format_chat_history(),
            "turns": [
                {
                    "turn_number": t.turn_number,
                    "interviewer_message": t.interviewer_message,
                    "interviewer_suggestions": t.interviewer_suggestions,
                    "is_last_message": t.is_last_message,
                    "stakeholder_response": t.stakeholder_response,
                    "interviewer_tokens": t.interviewer_tokens,
                    "stakeholder_tokens": t.stakeholder_tokens,
                    "interviewer_elapsed": round(t.interviewer_elapsed, 2),
                    "stakeholder_elapsed": round(t.stakeholder_elapsed, 2),
                }
                for t in self.turns
            ],
        }


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


def _parse_interviewer_response(raw: str) -> dict:
    """Parsa la risposta JSON dell'interviewer.

    Restituisce dict con chiavi: message, suggestions, is_last_message.
    In caso di errore di parsing, restituisce il testo come messaggio.
    """
    try:
        json_str = _extract_json(raw)
        data = json.loads(json_str)
        return {
            "message": data.get("message", raw),
            "suggestions": data.get("suggestions", []),
            "is_last_message": data.get("is_last_message", False),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "message": raw,
            "suggestions": [],
            "is_last_message": False,
        }


def _prepare_interviewer_prompt(
    template: str,
    project_idea: str,
    extracted_reqs: str,
) -> str:
    """Sostituisce i placeholder nel prompt dell'interviewer."""
    prompt = template.replace("{{$project_idea}}", project_idea)
    prompt = prompt.replace("{{$extracted_reqs}}", extracted_reqs)
    return prompt


def simulate_interview(
    scenario: dict,
    interviewer_prompt: str,
    stakeholder_prompt: str,
    config: AzureOpenAIConfig,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    max_turns: int = 50,
    verbose: bool = False,
) -> ConversationLog:
    """Simula un'intervista completa tra interviewer e stakeholder.

    Args:
        scenario: dizionario con id, name, project_idea, extracted_reqs
        interviewer_prompt: template del prompt interviewer (con placeholder)
        stakeholder_prompt: template del prompt stakeholder (con placeholder)
        config: configurazione Azure OpenAI
        temperature: temperatura per la generazione
        max_tokens: max token per risposta
        max_turns: limite di sicurezza per il numero di turni
        verbose: se True, stampa dettagli delle chiamate

    Returns:
        ConversationLog con tutti i turni della conversazione
    """
    project_idea = scenario.get("project_idea", "")
    topic = scenario.get("topic", "")
    extracted_reqs = scenario.get("extracted_reqs", [])
    extracted_reqs_str = (
        json.dumps(extracted_reqs, indent=2, ensure_ascii=False)
        if extracted_reqs
        else ""
    )

    # Prepara i prompt con i dati dello scenario
    interviewer_system = _prepare_interviewer_prompt(
        interviewer_prompt, project_idea, extracted_reqs_str
    )
    stakeholder_system = stakeholder_prompt.replace("{project_idea}", project_idea)
    stakeholder_system = stakeholder_system.replace(
        "{extracted_reqs}", extracted_reqs_str
    )
    stakeholder_system = stakeholder_system.replace("{topic}", topic)

    log = ConversationLog(
        scenario_id=scenario.get("id", "unknown"),
        scenario_name=scenario.get("name", ""),
        project_idea=project_idea,
        topic=topic,
        interviewer_model=config.deployment,
        stakeholder_model=config.deployment,
    )

    # History separate per interviewer e stakeholder
    interviewer_history: list[dict[str, str]] = [
        {"role": "system", "content": interviewer_system}
    ]
    stakeholder_history: list[dict[str, str]] = [
        {"role": "system", "content": stakeholder_system}
    ]

    total_tokens = 0

    for turn_num in range(1, max_turns + 1):
        if verbose:
            print(f"\n  --- Turno {turn_num} ---")

        # === 1. Chiamata all'interviewer ===
        if verbose:
            print(f"  [interviewer] Invio ({len(interviewer_history)} messaggi)...")

        t0 = time.time()
        interviewer_resp = call_azure_openai_chat(
            config=config,
            messages=interviewer_history,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        elapsed_iv = time.time() - t0
        interviewer_tokens = interviewer_resp.total_tokens

        if verbose:
            print(
                f"  [interviewer] Risposta in {elapsed_iv:.1f}s "
                f"({len(interviewer_resp.content)} char, "
                f"{interviewer_tokens} token)"
            )

        # Parsa la risposta JSON dell'interviewer
        parsed = _parse_interviewer_response(interviewer_resp.content)
        message = parsed["message"]
        suggestions = parsed["suggestions"]
        is_last = parsed["is_last_message"]

        if verbose:
            print(f"  [interviewer] message: {message[:120]}...")
            print(f"  [interviewer] is_last_message: {is_last}")
            if suggestions:
                print(f"  [interviewer] suggestions: {suggestions}")

        # Aggiungi la risposta dell'interviewer alla sua history
        interviewer_history.append(
            {"role": "assistant", "content": interviewer_resp.content}
        )

        # Se è l'ultimo messaggio, salva il turno e termina
        if is_last:
            turn = ConversationTurn(
                turn_number=turn_num,
                interviewer_raw=interviewer_resp.content,
                interviewer_message=message,
                interviewer_suggestions=suggestions,
                is_last_message=True,
                stakeholder_response="",
                interviewer_tokens=interviewer_tokens,
                stakeholder_tokens=0,
                interviewer_elapsed=elapsed_iv,
                stakeholder_elapsed=0.0,
            )
            log.turns.append(turn)
            total_tokens += interviewer_tokens
            log.completed_naturally = True
            break

        # === 2. Chiamata allo stakeholder ===
        # Prepara il messaggio utente per lo stakeholder (domanda + suggestions)
        stakeholder_user_msg = message
        if suggestions:
            suggestions_text = "\n".join(f"- {s}" for s in suggestions)
            stakeholder_user_msg += (
                f"\n\n[Suggerimenti proposti dall'intervistatore:]\n{suggestions_text}"
            )

        stakeholder_history.append(
            {"role": "user", "content": stakeholder_user_msg}
        )

        if verbose:
            print(f"  [stakeholder] Invio ({len(stakeholder_history)} messaggi)...")

        t0 = time.time()
        stakeholder_resp = call_azure_openai_chat(
            config=config,
            messages=stakeholder_history,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        elapsed_sh = time.time() - t0
        stakeholder_tokens = stakeholder_resp.total_tokens

        if verbose:
            print(
                f"  [stakeholder] Risposta in {elapsed_sh:.1f}s "
                f"({len(stakeholder_resp.content)} char, "
                f"{stakeholder_tokens} token)"
            )
            print(f"  [stakeholder] {stakeholder_resp.content[:120]}...")

        # Aggiungi la risposta dello stakeholder alla sua history
        stakeholder_history.append(
            {"role": "assistant", "content": stakeholder_resp.content}
        )

        # Aggiungi la risposta dello stakeholder alla history dell'interviewer
        # (per l'interviewer, la risposta dello stakeholder è un messaggio "user")
        interviewer_history.append(
            {"role": "user", "content": stakeholder_resp.content}
        )

        # Salva il turno
        turn = ConversationTurn(
            turn_number=turn_num,
            interviewer_raw=interviewer_resp.content,
            interviewer_message=message,
            interviewer_suggestions=suggestions,
            is_last_message=False,
            stakeholder_response=stakeholder_resp.content,
            interviewer_tokens=interviewer_tokens,
            stakeholder_tokens=stakeholder_tokens,
            interviewer_elapsed=elapsed_iv,
            stakeholder_elapsed=elapsed_sh,
        )
        log.turns.append(turn)
        total_tokens += interviewer_tokens + stakeholder_tokens

    log.total_turns = len(log.turns)
    log.total_tokens = total_tokens
    return log
