"""Router: Step singoli (simulate, extract, evaluate)."""

from dataclasses import replace

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ... import services
from ..dependencies import get_settings
from .. import jobs

router = APIRouter(prefix="/steps")


@router.get("/simulate")
async def simulate_form(request: Request):
    s = get_settings()
    return s.templates.TemplateResponse(
        "steps/simulate.html",
        {
            "request": request,
            "scenarios": services.load_scenarios(s.scenarios_dir),
            "interviewers": services.load_interviewer_prompts(s.prompts_dir),
            "models": services.AVAILABLE_MODELS,
            "active_page": "steps",
        },
    )


@router.post("/simulate")
async def simulate_start(
    request: Request,
    scenario_id: str = Form(...),
    interviewer: str = Form(...),
    model: str = Form(...),
):
    s = get_settings()

    scenarios = services.load_scenarios(s.scenarios_dir)
    scenario = next((sc for sc in scenarios if sc.get("id") == scenario_id), None)
    if scenario is None:
        return RedirectResponse("/steps/simulate", status_code=303)

    interviewers = services.load_interviewer_prompts(s.prompts_dir)
    interviewer_content = ""
    for label, content in interviewers:
        if label == interviewer:
            interviewer_content = content
            break
    if not interviewer_content:
        return RedirectResponse("/steps/simulate", status_code=303)

    job_id = jobs.create_job()
    step_config = replace(s.config, deployment=model)

    jobs.run_step_job(
        job_id=job_id,
        step_type="simulate",
        prompts_dir=s.prompts_dir,
        base_out=s.base_out,
        config=step_config,
        temperature=0.7,
        scenario=scenario,
        interviewer_prompt=interviewer_content,
        prompt_label=interviewer,
    )

    return RedirectResponse(f"/pipeline/{job_id}", status_code=303)


@router.get("/extract")
async def extract_form(request: Request):
    s = get_settings()
    return s.templates.TemplateResponse(
        "steps/extract.html",
        {
            "request": request,
            "conversations": services.scan_conversations(s.base_out),
            "models": services.AVAILABLE_MODELS,
            "active_page": "steps",
        },
    )


@router.post("/extract")
async def extract_start(
    request: Request,
    conv_idx: int = Form(...),
    model: str = Form(...),
):
    s = get_settings()
    conversations = services.scan_conversations(s.base_out)

    if conv_idx < 0 or conv_idx >= len(conversations):
        return RedirectResponse("/steps/extract", status_code=303)

    conv_file, conv_data, pl, md = conversations[conv_idx]
    run = conv_file.parent.parent.parent  # scenario_dir -> conversations -> model_dir

    job_id = jobs.create_job()
    step_config = replace(s.config, deployment=model)

    jobs.run_step_job(
        job_id=job_id,
        step_type="extract",
        prompts_dir=s.prompts_dir,
        base_out=s.base_out,
        config=step_config,
        temperature=0.7,
        conv_data=conv_data,
        conv_run=run,
    )

    return RedirectResponse(f"/pipeline/{job_id}", status_code=303)


@router.get("/evaluate")
async def evaluate_form(request: Request):
    s = get_settings()
    return s.templates.TemplateResponse(
        "steps/evaluate.html",
        {
            "request": request,
            "requirements": services.scan_requirements(s.base_out),
            "models": services.AVAILABLE_MODELS,
            "active_page": "steps",
        },
    )


@router.post("/evaluate")
async def evaluate_start(
    request: Request,
    req_idx: int = Form(...),
    model: str = Form(...),
):
    s = get_settings()
    req_files = services.scan_requirements(s.base_out)

    if req_idx < 0 or req_idx >= len(req_files):
        return RedirectResponse("/steps/evaluate", status_code=303)

    req_file_path, req_data, pl, md = req_files[req_idx]
    run = req_file_path.parent.parent.parent

    job_id = jobs.create_job()
    step_config = replace(s.config, deployment=model)

    jobs.run_step_job(
        job_id=job_id,
        step_type="evaluate",
        prompts_dir=s.prompts_dir,
        base_out=s.base_out,
        config=step_config,
        temperature=0.7,
        scenarios_dir=s.scenarios_dir,
        req_data=req_data,
        req_run=run,
    )

    return RedirectResponse(f"/pipeline/{job_id}", status_code=303)
