"""Entrypoint: python -m teco_cli"""

import sys
from pathlib import Path

from .cli import parse_args
from .config import load_config
from .files import assemble_content
from .llm import call_azure_openai


def main() -> None:
    args = parse_args()

    verbose = args.verbose

    if verbose:
        print(f"[teco-cli] File di input: {args.files}")
        if args.env_file:
            print(f"[teco-cli] .env custom: {args.env_file}")
        if args.deployment:
            print(f"[teco-cli] Deployment: {args.deployment}")

    # 1. Configurazione
    try:
        config = load_config(
            env_file=args.env_file,
            deployment_override=args.deployment,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[teco-cli] Errore configurazione: {exc}", file=sys.stderr)
        sys.exit(1)

    if verbose:
        print(f"[teco-cli] Endpoint: {config.endpoint}")
        print(f"[teco-cli] Deployment: {config.deployment}")
        print(f"[teco-cli] API version: {config.api_version}")

    # 2. Lettura file
    try:
        file_content = assemble_content(args.files)
    except (FileNotFoundError, UnicodeDecodeError) as exc:
        print(f"[teco-cli] Errore lettura file: {exc}", file=sys.stderr)
        sys.exit(1)

    if verbose:
        print(f"[teco-cli] Contenuto assemblato: {len(file_content)} caratteri")

    # 3. Composizione prompt utente
    user_content = f"{args.prompt}\n\n{file_content}"

    # 4. Chiamata LLM
    if verbose:
        print(f"[teco-cli] Invio richiesta ad Azure OpenAI...")

    try:
        llm_resp = call_azure_openai(
            config=config,
            user_content=user_content,
            system_prompt=getattr(args, "system_prompt", None),
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
    except Exception as exc:
        print(f"[teco-cli] Errore chiamata LLM: {exc}", file=sys.stderr)
        sys.exit(1)

    if llm_resp.truncated:
        print(
            f"[teco-cli] ATTENZIONE: risposta troncata (max_tokens={args.max_tokens} "
            f"insufficienti). Considera di aumentare --max-tokens.",
            file=sys.stderr,
        )

    # 5. Scrittura output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(llm_resp.content, encoding="utf-8")

    if verbose:
        print(f"[teco-cli] Risposta scritta in: {args.output} ({len(llm_resp.content)} caratteri)")
    else:
        print(f"Output salvato in: {args.output}")


if __name__ == "__main__":
    main()
