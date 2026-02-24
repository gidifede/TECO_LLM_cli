"""CLI dedicata per la pipeline requisiti → user stories → test cases."""

import argparse
import sys
from pathlib import Path

from .config import load_config
from .pipeline import run_pipeline


def parse_pipeline_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="teco-pipeline",
        description=(
            "Pipeline automatica: per ogni requisito genera user stories "
            "e poi test cases tramite Azure OpenAI."
        ),
    )

    parser.add_argument(
        "--requirements",
        required=True,
        help="Path al file requirements.json.",
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
        "--output-dir",
        required=True,
        help="Directory di output per i risultati.",
    )

    # Opzioni Azure / LLM
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
        "--limit",
        type=int,
        default=None,
        help="Elabora solo i primi N requisiti (utile per test).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Mostra log dettagliato.",
    )

    args = parser.parse_args(argv)

    # Validazione
    if not Path(args.requirements).is_file():
        parser.error(f"File requisiti non trovato: {args.requirements}")

    if args.prompts_dir is None:
        # Default: directory prompts dentro il package
        args.prompts_dir = str(Path(__file__).resolve().parent / "prompts")

    if not Path(args.prompts_dir).is_dir():
        parser.error(f"Directory prompts non trovata: {args.prompts_dir}")

    return args


def main() -> None:
    args = parse_pipeline_args()

    if args.verbose:
        print(f"[teco-pipeline] Requirements: {args.requirements}")
        print(f"[teco-pipeline] Prompts dir:  {args.prompts_dir}")
        print(f"[teco-pipeline] Output dir:   {args.output_dir}")

    try:
        config = load_config(
            env_file=args.env_file,
            deployment_override=args.deployment,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[teco-pipeline] Errore configurazione: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"[teco-pipeline] Endpoint:   {config.endpoint}")
        print(f"[teco-pipeline] Deployment: {config.deployment}")

    run_pipeline(
        requirements_path=args.requirements,
        prompts_dir=args.prompts_dir,
        output_dir=args.output_dir,
        config=config,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        verbose=args.verbose,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
