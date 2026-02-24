"""Router: API JSON per polling job status."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import jobs

router = APIRouter(prefix="/api")


@router.get("/jobs/{job_id}")
async def job_status(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        return JSONResponse({"error": "Job non trovato"}, status_code=404)

    return {
        "id": job.id,
        "status": job.status,
        "current_step": job.current_step,
        "progress": job.progress,
        "result": job.result,
        "error": job.error,
    }
