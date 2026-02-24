"""Router: Confronto valutazioni."""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import services
from ...comparison import generate_comparison_html
from ...paths import OutputDirs
from ..dependencies import get_settings

router = APIRouter(prefix="/comparisons")


def _list_existing(base_out: Path) -> list[tuple[str, str]]:
    """Restituisce [(nome_file, data_modifica)] dei confronti gia generati."""
    comp_dir = base_out / OutputDirs.COMPARISONS
    if not comp_dir.is_dir():
        return []
    results = []
    for f in sorted(comp_dir.glob("*.html"), reverse=True):
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        results.append((f.name, mtime))
    return results


@router.get("")
async def comparisons_form(request: Request):
    s = get_settings()
    evaluations = services.scan_evaluations(s.base_out)
    existing = _list_existing(s.base_out)
    return s.templates.TemplateResponse(
        "comparisons/select.html",
        {
            "request": request,
            "evaluations": evaluations,
            "existing_comparisons": existing,
            "active_page": "comparisons",
        },
    )


@router.post("")
async def comparisons_generate(
    request: Request,
    eval_a_idx: int = Form(...),
    eval_b_idx: int = Form(...),
):
    s = get_settings()
    evaluations = services.scan_evaluations(s.base_out)

    if (
        eval_a_idx < 0
        or eval_a_idx >= len(evaluations)
        or eval_b_idx < 0
        or eval_b_idx >= len(evaluations)
        or eval_a_idx == eval_b_idx
    ):
        return RedirectResponse("/comparisons", status_code=303)

    fp_a, eval_a, pl_a, md_a = evaluations[eval_a_idx]
    fp_b, eval_b, pl_b, md_b = evaluations[eval_b_idx]

    run_n_a = fp_a.stem.split("_")[0]
    run_n_b = fp_b.stem.split("_")[0]
    scenario_a = eval_a.get("scenario_id", fp_a.parent.name)
    scenario_b = eval_b.get("scenario_id", fp_b.parent.name)
    label_a = f"[{pl_a}/{md_a}] {scenario_a} #{run_n_a}"
    label_b = f"[{pl_b}/{md_b}] {scenario_b} #{run_n_b}"

    comp_dir = s.base_out / OutputDirs.COMPARISONS
    comp_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = comp_dir / f"{timestamp}.html"

    generate_comparison_html(
        eval_a=eval_a,
        eval_b=eval_b,
        label_a=label_a,
        label_b=label_b,
        output_path=output_path,
    )

    return RedirectResponse(f"/comparisons/view/{output_path.name}", status_code=303)


@router.get("/view/{filename}")
async def comparisons_view(filename: str):
    s = get_settings()
    file_path = s.base_out / OutputDirs.COMPARISONS / filename
    if not file_path.is_file():
        return HTMLResponse("<h1>File non trovato</h1>", status_code=404)
    return HTMLResponse(file_path.read_text(encoding="utf-8"))
