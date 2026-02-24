"""Gestione job in background per operazioni LLM (pipeline e step singoli)."""

from __future__ import annotations

import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock

from ..config import AzureOpenAIConfig
from .. import services


@dataclass
class Job:
    id: str
    status: str = "pending"          # pending | running | step_1 | step_2 | step_3 | completed | error
    current_step: str = ""
    progress: list[str] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)


_jobs: dict[str, Job] = {}
_lock = Lock()
_executor = ThreadPoolExecutor(max_workers=2)


def create_job() -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = Job(id=job_id)
    return job_id


def get_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def _update(job: Job, **kwargs) -> None:
    with _lock:
        for k, v in kwargs.items():
            setattr(job, k, v)


def run_pipeline_job(
    job_id: str,
    scenario: dict,
    interviewer_prompt: str,
    prompt_label: str,
    prompts_dir: Path,
    base_out: Path,
    sim_config: AzureOpenAIConfig,
    ext_config: AzureOpenAIConfig,
    eval_config: AzureOpenAIConfig,
    temperature: float,
    max_tokens: int,
    scenarios_dir: Path,
) -> None:
    """Esegue la pipeline completa in background."""

    def _work() -> None:
        job = get_job(job_id)
        if job is None:
            return
        try:
            run = services.run_path(base_out, prompt_label, sim_config.deployment)

            # Step 1: Simulazione
            _update(job, status="step_1", current_step="Simulazione in corso...")
            job.progress.append(f"Avvio simulazione con {sim_config.deployment}")
            conv_data, run_num = services.run_simulation(
                scenario=scenario,
                interviewer_prompt=interviewer_prompt,
                prompt_label=prompt_label,
                prompts_dir=prompts_dir,
                run=run,
                config=sim_config,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if conv_data is None:
                _update(job, status="error", error="Simulazione fallita")
                return
            job.progress.append(
                f"Simulazione completata: {conv_data.get('total_turns', '?')} turni"
            )

            # Step 2: Estrazione
            _update(job, status="step_2", current_step="Estrazione requisiti...")
            job.progress.append(f"Avvio estrazione con {ext_config.deployment}")
            req_data = services.run_extraction(
                conv_data=conv_data,
                prompts_dir=prompts_dir,
                run=run,
                config=ext_config,
                temperature=temperature,
                run_number=run_num,
            )
            if req_data is None:
                _update(job, status="error", error="Estrazione fallita")
                return
            n_reqs = len(req_data.get("requirements", []))
            job.progress.append(f"Estrazione completata: {n_reqs} requisiti")

            # Step 3: Valutazione
            _update(job, status="step_3", current_step="Valutazione requisiti...")
            job.progress.append(f"Avvio valutazione con {eval_config.deployment}")

            scenario_full = services.find_scenario_for_id(
                scenario.get("id", "unknown"), scenarios_dir, fallback_data=scenario
            ) or scenario

            evaluation = services.run_evaluation(
                requirements_data=req_data,
                scenario=scenario_full,
                prompts_dir=prompts_dir,
                run=run,
                config=eval_config,
                temperature=temperature,
                run_number=run_num,
            )
            if evaluation is None:
                _update(job, status="error", error="Valutazione fallita")
                return

            overall = evaluation.get("overall_score", "?")
            job.progress.append(f"Valutazione completata: overall {overall}/5.0")

            _update(
                job,
                status="completed",
                current_step="Pipeline completata",
                result={
                    "evaluation": evaluation,
                    "prompt_label": prompt_label,
                    "sim_model": sim_config.deployment,
                    "ext_model": ext_config.deployment,
                    "eval_model": eval_config.deployment,
                    "scenario_id": scenario.get("id", "unknown"),
                    "run_number": run_num,
                },
            )

        except Exception:
            _update(job, status="error", error=traceback.format_exc())

    _executor.submit(_work)


def run_step_job(
    job_id: str,
    step_type: str,
    prompts_dir: Path,
    base_out: Path,
    config: AzureOpenAIConfig,
    temperature: float,
    max_tokens: int = 4096,
    scenarios_dir: Path | None = None,
    # step-specific
    scenario: dict | None = None,
    interviewer_prompt: str | None = None,
    prompt_label: str | None = None,
    conv_data: dict | None = None,
    conv_run: Path | None = None,
    req_data: dict | None = None,
    req_run: Path | None = None,
) -> None:
    """Esegue uno step singolo in background."""

    def _work() -> None:
        job = get_job(job_id)
        if job is None:
            return
        try:
            if step_type == "simulate":
                assert scenario and interviewer_prompt and prompt_label
                run = services.run_path(base_out, prompt_label, config.deployment)
                _update(job, status="running", current_step="Simulazione in corso...")
                job.progress.append(f"Avvio simulazione con {config.deployment}")
                conv_data_out, run_num = services.run_simulation(
                    scenario=scenario,
                    interviewer_prompt=interviewer_prompt,
                    prompt_label=prompt_label,
                    prompts_dir=prompts_dir,
                    run=run,
                    config=config,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if conv_data_out is None:
                    _update(job, status="error", error="Simulazione fallita")
                    return
                job.progress.append(
                    f"Completata: {conv_data_out.get('total_turns', '?')} turni"
                )
                _update(
                    job,
                    status="completed",
                    current_step="Simulazione completata",
                    result={"conversation": conv_data_out, "run_number": run_num},
                )

            elif step_type == "extract":
                assert conv_data and conv_run is not None
                _update(job, status="running", current_step="Estrazione requisiti...")
                job.progress.append(f"Avvio estrazione con {config.deployment}")
                output_data = services.run_extraction(
                    conv_data=conv_data,
                    prompts_dir=prompts_dir,
                    run=conv_run,
                    config=config,
                    temperature=temperature,
                )
                if output_data is None:
                    _update(job, status="error", error="Estrazione fallita")
                    return
                n_reqs = len(output_data.get("requirements", []))
                job.progress.append(f"Completata: {n_reqs} requisiti estratti")
                _update(
                    job,
                    status="completed",
                    current_step="Estrazione completata",
                    result={"requirements_data": output_data},
                )

            elif step_type == "evaluate":
                assert req_data and req_run is not None and scenarios_dir
                scenario_id = req_data.get("scenario_id", "unknown")
                scenario_full = services.find_scenario_for_id(
                    scenario_id, scenarios_dir
                )
                if scenario_full is None:
                    _update(
                        job,
                        status="error",
                        error=f"Scenario non trovato: {scenario_id}",
                    )
                    return
                _update(job, status="running", current_step="Valutazione requisiti...")
                job.progress.append(f"Avvio valutazione con {config.deployment}")
                evaluation = services.run_evaluation(
                    requirements_data=req_data,
                    scenario=scenario_full,
                    prompts_dir=prompts_dir,
                    run=req_run,
                    config=config,
                    temperature=temperature,
                )
                if evaluation is None:
                    _update(job, status="error", error="Valutazione fallita")
                    return
                overall = evaluation.get("overall_score", "?")
                job.progress.append(f"Completata: overall {overall}/5.0")
                _update(
                    job,
                    status="completed",
                    current_step="Valutazione completata",
                    result={"evaluation": evaluation},
                )
            else:
                _update(job, status="error", error=f"Step sconosciuto: {step_type}")

        except Exception:
            _update(job, status="error", error=traceback.format_exc())

    _executor.submit(_work)
