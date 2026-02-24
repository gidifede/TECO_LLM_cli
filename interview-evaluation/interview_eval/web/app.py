"""FastAPI app factory e entry point per la web app."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import load_config
from .dependencies import init_settings

_WEB_DIR = Path(__file__).resolve().parent


def create_app(
    env_file: str | None = None,
    deployment: str | None = None,
    scenarios_dir: str = "scenarios",
    output_dir: str = "./output_test",
) -> FastAPI:
    app = FastAPI(title="Interview Evaluator")

    # Static files e templates
    static_dir = _WEB_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    templates = Jinja2Templates(directory=str(_WEB_DIR / "templates"))

    # Resolve paths
    base_out = Path(output_dir).resolve()
    base_out.mkdir(parents=True, exist_ok=True)
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    scenarios_path = Path(scenarios_dir).resolve()

    # Config Azure OpenAI
    config = load_config(env_file=env_file, deployment_override=deployment)

    # Init singleton
    init_settings(
        config=config,
        base_out=base_out,
        prompts_dir=prompts_dir,
        scenarios_dir=scenarios_path,
        templates=templates,
    )

    # Include routers
    from .routers import dashboard, pipeline, steps, scenarios, comparisons, evaluations, api

    app.include_router(dashboard.router)
    app.include_router(pipeline.router)
    app.include_router(steps.router)
    app.include_router(scenarios.router)
    app.include_router(comparisons.router)
    app.include_router(evaluations.router)
    app.include_router(api.router)

    return app


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="interview-evaluator-web",
        description="Web interface per Interview Evaluator.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000, help="Porta (default: 8000).")
    parser.add_argument("--env-file", default=None, help="Path a un file .env custom.")
    parser.add_argument("--deployment", default=None, help="Nome del deployment Azure OpenAI.")
    parser.add_argument("--scenarios-dir", default="scenarios", help="Directory scenari.")
    parser.add_argument("--output-dir", default="./output_test", help="Directory output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    try:
        app = create_app(
            env_file=args.env_file,
            deployment=args.deployment,
            scenarios_dir=args.scenarios_dir,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[interview-evaluator-web] Errore configurazione: {exc}", file=sys.stderr)
        sys.exit(1)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
