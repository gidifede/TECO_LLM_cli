"""Router: Dashboard (GET /)."""

from fastapi import APIRouter, Request

from ... import services
from ..dependencies import get_settings

router = APIRouter()


@router.get("/")
async def dashboard(request: Request):
    s = get_settings()
    data = services.get_dashboard_data(s.base_out)
    return s.templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "data": data, "active_page": "dashboard"},
    )
