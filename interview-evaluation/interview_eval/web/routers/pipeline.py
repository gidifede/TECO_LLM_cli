"""Router: Pipeline (Simula -> Estrai -> Valuta)."""

from dataclasses import replace

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ... import services
from ..dependencies import get_settings
from .. import jobs

router = APIRouter(prefix="/pipeline")


@router.get("")
async def pipeline_form(request: Request):
    s = get_settings()
    scenarios_raw = services.load_scenarios(s.scenarios_dir)
    interviewers = services.load_interviewer_prompts(s.prompts_dir)
    models = services.AVAILABLE_MODELS

    return s.templates.TemplateResponse(
        "pipeline/new.html",
        {
            "request": request,
            "scenarios": scenarios_raw,
            "interviewers": interviewers,
            "models": models,
            "active_page": "pipeline",
        },
    )


@router.post("")
async def pipeline_start(
    request: Request,
    scenario_id: str = Form(...),
    interviewer: str = Form(...),
    sim_model: str = Form(...),
    ext_model: str = Form(...),
    eval_model: str = Form(...),
):
    s = get_settings()

    # Trova scenario e prompt interviewer
    scenarios = services.load_scenarios(s.scenarios_dir)
    scenario = next((sc for sc in scenarios if sc.get("id") == scenario_id), None)
    if scenario is None:
        return RedirectResponse("/pipeline", status_code=303)

    interviewers = services.load_interviewer_prompts(s.prompts_dir)
    interviewer_content = ""
    for label, content in interviewers:
        if label == interviewer:
            interviewer_content = content
            break
    if not interviewer_content:
        return RedirectResponse("/pipeline", status_code=303)

    # Crea job
    job_id = jobs.create_job()

    sim_config = replace(s.config, deployment=sim_model)
    ext_config = replace(s.config, deployment=ext_model)
    eval_config = replace(s.config, deployment=eval_model)

    jobs.run_pipeline_job(
        job_id=job_id,
        scenario=scenario,
        interviewer_prompt=interviewer_content,
        prompt_label=interviewer,
        prompts_dir=s.prompts_dir,
        base_out=s.base_out,
        sim_config=sim_config,
        ext_config=ext_config,
        eval_config=eval_config,
        temperature=0.7,
        max_tokens=4096,
        scenarios_dir=s.scenarios_dir,
    )

    return RedirectResponse(f"/pipeline/{job_id}", status_code=303)


@router.get("/{job_id}")
async def pipeline_status(request: Request, job_id: str):
    s = get_settings()
    job = jobs.get_job(job_id)
    if job is None:
        return RedirectResponse("/pipeline", status_code=303)

    step_idx_map = {"step_1": 0, "step_2": 1, "step_3": 2}
    step_idx = step_idx_map.get(job.status)

    return s.templates.TemplateResponse(
        "pipeline/status.html",
        {
            "request": request,
            "job": job,
            "step_idx": step_idx,
            "active_page": "pipeline",
        },
    )
