"""Schedule template router."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services import template_service

router = APIRouter(prefix="/api/templates", tags=["templates"])


class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    template_data: dict | list
    category: str = "general"


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template_data: Optional[dict | list] = None
    category: Optional[str] = None


class TemplateApply(BaseModel):
    start_date: str


@router.get("")
async def list_templates(category: Optional[str] = Query(None)):
    """List all schedule templates."""
    return await template_service.list_templates(category)


@router.get("/{template_id}")
async def get_template(template_id: int):
    """Get a template by ID."""
    result = await template_service.get_template(template_id)
    if not result:
        raise HTTPException(404, "Template not found")
    return result


@router.post("")
async def create_template(body: TemplateCreate):
    """Create a new schedule template."""
    return await template_service.create_template(body.model_dump())


@router.put("/{template_id}")
async def update_template(template_id: int, body: TemplateUpdate):
    """Update a template."""
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    result = await template_service.update_template(template_id, data)
    if not result:
        raise HTTPException(404, "Template not found")
    return result


@router.delete("/{template_id}")
async def delete_template(template_id: int):
    """Delete a template."""
    ok = await template_service.delete_template(template_id)
    if not ok:
        raise HTTPException(404, "Template not found")
    return {"ok": True}


@router.post("/{template_id}/apply")
async def apply_template(template_id: int, body: TemplateApply):
    """Apply a template to create schedules from the given start date."""
    created = await template_service.apply_template(template_id, body.start_date)
    if not created:
        raise HTTPException(404, "Template not found or empty")
    return {"created": created, "count": len(created)}
