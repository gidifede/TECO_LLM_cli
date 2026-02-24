"""Caricamento configurazione Azure OpenAI da .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class AzureOpenAIConfig:
    api_key: str
    endpoint: str
    api_version: str
    deployment: str


def _find_local_env() -> Path | None:
    """Cerca il .env nella root del progetto TECO_LLM_cli."""
    cli_dir = Path(__file__).resolve().parent.parent  # TECO_LLM_cli/
    local = cli_dir / ".env"
    if local.is_file():
        return local
    return None


def load_config(
    env_file: str | None = None,
    deployment_override: str | None = None,
) -> AzureOpenAIConfig:
    """Carica la configurazione Azure OpenAI.

    Ordine di ricerca del .env:
    1. Parametro esplicito ``env_file``
    2. Variabile d'ambiente ``DOTENV_PATH``
    3. Path relativo al progetto fratello
    """
    env_path: Path | None = None

    if env_file:
        env_path = Path(env_file)
    elif os.getenv("DOTENV_PATH"):
        env_path = Path(os.environ["DOTENV_PATH"])
    else:
        env_path = _find_local_env()

    if env_path and env_path.is_file():
        load_dotenv(env_path, override=True)
    elif env_path:
        raise FileNotFoundError(f"File .env non trovato: {env_path}")

    api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    deployment = deployment_override or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.2")

    if not api_key:
        raise ValueError("AZURE_OPENAI_API_KEY non configurata")
    if not endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT non configurato")

    return AzureOpenAIConfig(
        api_key=api_key,
        endpoint=endpoint,
        api_version=api_version,
        deployment=deployment,
    )
