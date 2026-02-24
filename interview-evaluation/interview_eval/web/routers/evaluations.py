"""Router: Dettaglio valutazione."""

import json
from pathlib import Path

from fastapi import APIRouter, Request

from ... import services
from ..dependencies import get_settings

router = APIRouter(prefix="/evaluations")


@router.get("/detail")
async def evaluation_detail(request: Request, path: str = ""):
    """Mostra il dettaglio di una valutazione.

    Il parametro ``path`` puo essere:
    - Un path relativo alla directory di output (es. prompt/model/evaluations/scenario_id)
    - Una directory scenario: mostra l'ultima valutazione disponibile
    """
    s = get_settings()
    evaluation = None
    eval_label = path

    if not path:
        return s.templates.TemplateResponse(
            "evaluations/detail.html",
            {"request": request, "evaluation": None, "eval_label": ""},
        )

    target = s.base_out / path

    # Se e una directory, cerca l'ultimo file di valutazione
    if target.is_dir():
        eval_files = sorted(target.glob("*_evaluation.json"))
        if eval_files:
            target = eval_files[-1]
        else:
            return s.templates.TemplateResponse(
                "evaluations/detail.html",
                {"request": request, "evaluation": None, "eval_label": path},
            )

    # Se e un file, caricalo direttamente
    if target.is_file():
        try:
            evaluation = json.loads(target.read_text(encoding="utf-8"))
            eval_label = f"{target.parent.name} / {target.stem}"
        except (json.JSONDecodeError, OSError):
            evaluation = None

    return s.templates.TemplateResponse(
        "evaluations/detail.html",
        {"request": request, "evaluation": evaluation, "eval_label": eval_label},
    )
