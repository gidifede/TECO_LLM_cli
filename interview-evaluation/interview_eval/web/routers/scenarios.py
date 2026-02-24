"""Router: CRUD Scenari."""

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ... import services
from ..dependencies import get_settings

router = APIRouter(prefix="/scenarios")


@router.get("")
async def scenario_list(request: Request):
    s = get_settings()
    scenarios = services.load_scenarios(s.scenarios_dir)
    return s.templates.TemplateResponse(
        "scenarios/list.html",
        {"request": request, "scenarios": scenarios, "active_page": "scenarios"},
    )


@router.get("/new")
async def scenario_new_form(request: Request):
    s = get_settings()
    return s.templates.TemplateResponse(
        "scenarios/form.html",
        {"request": request, "scenario": None, "active_page": "scenarios"},
    )


@router.post("")
async def scenario_create(
    request: Request,
    id: str = Form(...),
    name: str = Form(...),
    topic: str = Form(""),
    project_idea: str = Form(...),
):
    s = get_settings()
    s.scenarios_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "id": id.strip(),
        "name": name.strip(),
        "project_idea": project_idea.strip(),
        "topic": topic.strip(),
        "extracted_reqs": [],
    }

    file_path = s.scenarios_dir / f"{data['id']}.json"
    file_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return RedirectResponse("/scenarios", status_code=303)


@router.get("/{scenario_id}/edit")
async def scenario_edit_form(request: Request, scenario_id: str):
    s = get_settings()
    scenarios = services.load_scenarios(s.scenarios_dir)
    scenario = next((sc for sc in scenarios if sc.get("id") == scenario_id), None)
    if scenario is None:
        return RedirectResponse("/scenarios", status_code=303)

    return s.templates.TemplateResponse(
        "scenarios/form.html",
        {"request": request, "scenario": scenario, "active_page": "scenarios"},
    )


@router.post("/{scenario_id}")
async def scenario_update(
    request: Request,
    scenario_id: str,
    name: str = Form(...),
    topic: str = Form(""),
    project_idea: str = Form(...),
):
    s = get_settings()

    file_path = s.scenarios_dir / f"{scenario_id}.json"
    if not file_path.is_file():
        return RedirectResponse("/scenarios", status_code=303)

    data = {
        "id": scenario_id,
        "name": name.strip(),
        "project_idea": project_idea.strip(),
        "topic": topic.strip(),
        "extracted_reqs": [],
    }

    file_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return RedirectResponse("/scenarios", status_code=303)


@router.post("/{scenario_id}/delete")
async def scenario_delete(request: Request, scenario_id: str):
    s = get_settings()
    file_path = s.scenarios_dir / f"{scenario_id}.json"
    if file_path.is_file():
        file_path.unlink()
    return RedirectResponse("/scenarios", status_code=303)
