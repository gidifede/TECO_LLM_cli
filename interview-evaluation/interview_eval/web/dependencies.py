"""Configurazione condivisa e dependency injection per la web app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from ..config import AzureOpenAIConfig


@dataclass
class AppSettings:
    """Stato globale dell'applicazione, inizializzato al boot."""

    config: AzureOpenAIConfig
    base_out: Path
    prompts_dir: Path
    scenarios_dir: Path
    templates: Jinja2Templates


# Singleton — popolato da create_app()
_settings: AppSettings | None = None


def init_settings(
    config: AzureOpenAIConfig,
    base_out: Path,
    prompts_dir: Path,
    scenarios_dir: Path,
    templates: Jinja2Templates,
) -> None:
    global _settings
    _settings = AppSettings(
        config=config,
        base_out=base_out,
        prompts_dir=prompts_dir,
        scenarios_dir=scenarios_dir,
        templates=templates,
    )


def get_settings() -> AppSettings:
    assert _settings is not None, "AppSettings non inizializzato — chiama init_settings() prima."
    return _settings


def templates_ctx(request: Request, **extra) -> dict:
    """Contesto base per tutti i template Jinja2."""
    return {"request": request, **extra}
