"""Parsing argomenti CLI con argparse."""

import argparse
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Configura e restituisce gli argomenti della CLI."""
    parser = argparse.ArgumentParser(
        prog="teco-cli",
        description="Invia file di testo ad Azure OpenAI con un prompt.",
    )

    # --- Prompt (mutuamente esclusivi) ---
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument(
        "--prompt",
        help="Prompt testuale da inviare all'LLM.",
    )
    prompt_group.add_argument(
        "--prompt-file",
        help="File contenente il prompt.",
    )

    # --- File di input ---
    parser.add_argument(
        "--files",
        nargs="+",
        required=True,
        help="Uno o piu file di testo da inviare.",
    )

    # --- Output ---
    parser.add_argument(
        "--output",
        required=True,
        help="File di output per la risposta.",
    )

    # --- System prompt (mutuamente esclusivi) ---
    sys_group = parser.add_mutually_exclusive_group()
    sys_group.add_argument(
        "--system-prompt",
        help="System prompt testuale.",
    )
    sys_group.add_argument(
        "--system-prompt-file",
        help="File contenente il system prompt.",
    )

    # --- Opzioni Azure / LLM ---
    parser.add_argument(
        "--deployment",
        default=None,
        help="Nome del deployment Azure OpenAI (default dal .env).",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Path a un file .env custom.",
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
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Mostra log dettagliato.",
    )

    args = parser.parse_args(argv)

    # --- Validazione ---
    for fp in args.files:
        if not Path(fp).is_file():
            parser.error(f"File non trovato: {fp}")

    if args.prompt_file:
        p = Path(args.prompt_file)
        if not p.is_file():
            parser.error(f"File prompt non trovato: {args.prompt_file}")
        args.prompt = p.read_text(encoding="utf-8").strip()

    if args.system_prompt_file:
        p = Path(args.system_prompt_file)
        if not p.is_file():
            parser.error(f"File system prompt non trovato: {args.system_prompt_file}")
        args.system_prompt = p.read_text(encoding="utf-8").strip()

    return args
