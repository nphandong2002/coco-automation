"""Content projects, ideas and templates. Project routes are scoped by channel."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enums import ContentType, IdeaStatus, ProductionStatus
from app.schemas.content import (
    ContentCreate,
    ContentOut,
    ContentUpdate,
    IdeaGenerate,
    IdeaOut,
    MetadataOut,
    RenderRequest,
    TemplateIn,
    TemplateOut,
    TemplateUpdate,
    ValidationReport,
)
from app.schemas.production import JobOut
from app.services import content_service as svc
from app.services import idea_service, render_service, template_service
from app.services.channel_service import get_channel

router = APIRouter(tags=["content"])
base = "/channels/{channel_id}/content"


# ----------------------------------------------------------------- projects
@router.get("/content", response_model=list[ContentOut])
def list_all(channel_id: int | None = None, status: ProductionStatus | None = None,
             content_type: ContentType | None = None, q: str | None = None, db: Session = Depends(get_db)):
    return svc.list_projects(db, channel_id=channel_id, status=status,
                             content_type=content_type.value if content_type else None, q=q)


@router.get(base, response_model=list[ContentOut])
def list_for_channel(channel_id: int, status: ProductionStatus | None = None, db: Session = Depends(get_db)):
    get_channel(db, channel_id)
    return svc.list_projects(db, channel_id=channel_id, status=status)


@router.post(base, response_model=ContentOut, status_code=201)
def create(channel_id: int, data: ContentCreate, db: Session = Depends(get_db)):
    p = svc.create_project(db, get_channel(db, channel_id), data)
    return svc.project_out(db, p)


@router.get(base + "/{project_id}", response_model=ContentOut)
def get(channel_id: int, project_id: int, db: Session = Depends(get_db)):
    return svc.project_out(db, svc.get_project(db, channel_id, project_id))


@router.patch(base + "/{project_id}", response_model=ContentOut)
def update(channel_id: int, project_id: int, data: ContentUpdate, db: Session = Depends(get_db)):
    p = svc.update_project(db, svc.get_project(db, channel_id, project_id), data)
    return svc.project_out(db, p)


@router.delete(base + "/{project_id}", status_code=204)
def delete(channel_id: int, project_id: int, db: Session = Depends(get_db)):
    svc.delete_project(db, svc.get_project(db, channel_id, project_id))


@router.get(base + "/{project_id}/validate", response_model=ValidationReport)
def validate(channel_id: int, project_id: int, db: Session = Depends(get_db)):
    return svc.validate_for_render(db, svc.get_project(db, channel_id, project_id))


@router.post(base + "/{project_id}/ready", response_model=ContentOut)
def mark_ready(channel_id: int, project_id: int, db: Session = Depends(get_db)):
    return svc.project_out(db, svc.mark_ready(db, svc.get_project(db, channel_id, project_id)))


@router.post(base + "/{project_id}/character/sync-version", response_model=ContentOut)
def sync_character(channel_id: int, project_id: int, db: Session = Depends(get_db)):
    p = svc.sync_character_version(db, svc.get_project(db, channel_id, project_id))
    return svc.project_out(db, p)


@router.post(base + "/{project_id}/metadata/generate", response_model=MetadataOut)
def generate_metadata(channel_id: int, project_id: int, apply: bool = True, db: Session = Depends(get_db)):
    return svc.generate_metadata(db, svc.get_project(db, channel_id, project_id), apply)


@router.post(base + "/{project_id}/thumbnail/generate", response_model=ContentOut)
def generate_thumbnail(channel_id: int, project_id: int, db: Session = Depends(get_db)):
    p = svc.generate_thumbnail(db, svc.get_project(db, channel_id, project_id))
    return svc.project_out(db, p)


@router.post(base + "/{project_id}/thumbnail", response_model=ContentOut)
def upload_thumbnail(channel_id: int, project_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    p = svc.upload_thumbnail(db, svc.get_project(db, channel_id, project_id), file.file.read())
    return svc.project_out(db, p)


@router.delete(base + "/{project_id}/thumbnail", response_model=ContentOut)
def remove_thumbnail(channel_id: int, project_id: int, db: Session = Depends(get_db)):
    p = svc.get_project(db, channel_id, project_id)
    p.thumbnail_path = None
    db.commit()
    return svc.project_out(db, p)


@router.post(base + "/{project_id}/render", response_model=JobOut, status_code=201)
def render(channel_id: int, project_id: int, data: RenderRequest, db: Session = Depends(get_db)):
    job = render_service.enqueue(db, svc.get_project(db, channel_id, project_id), data)
    return render_service.job_out(db, job)


@router.get(base + "/{project_id}/jobs", response_model=list[JobOut])
def project_jobs(channel_id: int, project_id: int, db: Session = Depends(get_db)):
    svc.get_project(db, channel_id, project_id)
    return render_service.list_jobs(db, channel_id=channel_id, project_id=project_id, limit=50)


class SaveAsTemplate(BaseModel):
    name: str = Field(min_length=2, max_length=150)


@router.post(base + "/{project_id}/save-template", response_model=TemplateOut, status_code=201)
def save_as_template(channel_id: int, project_id: int, data: SaveAsTemplate, db: Session = Depends(get_db)):
    return template_service.template_from_project(db, svc.get_project(db, channel_id, project_id), data.name)


# ----------------------------------------------------------------- ideas
@router.get("/channels/{channel_id}/ideas", response_model=list[IdeaOut])
def list_ideas(channel_id: int, status: IdeaStatus | None = None, db: Session = Depends(get_db)):
    get_channel(db, channel_id)
    return idea_service.list_ideas(db, channel_id, status)


@router.post("/channels/{channel_id}/ideas/generate", response_model=list[IdeaOut], status_code=201)
def generate_ideas(channel_id: int, data: IdeaGenerate, db: Session = Depends(get_db)):
    return idea_service.generate(db, get_channel(db, channel_id), data.count, data.content_type)


@router.post("/channels/{channel_id}/ideas/{idea_id}/accept", response_model=ContentOut, status_code=201)
def accept_idea(channel_id: int, idea_id: int, db: Session = Depends(get_db)):
    ch = get_channel(db, channel_id)
    idea = idea_service.get_idea(db, channel_id, idea_id)
    p = svc.create_project(db, ch, idea_service.to_project_payload(db, ch, idea))
    return svc.project_out(db, p)


@router.post("/channels/{channel_id}/ideas/{idea_id}/reject", response_model=IdeaOut)
def reject_idea(channel_id: int, idea_id: int, db: Session = Depends(get_db)):
    return idea_service.set_status(db, idea_service.get_idea(db, channel_id, idea_id), IdeaStatus.REJECTED)


@router.delete("/channels/{channel_id}/ideas/{idea_id}", status_code=204)
def delete_idea(channel_id: int, idea_id: int, db: Session = Depends(get_db)):
    idea_service.delete_idea(db, idea_service.get_idea(db, channel_id, idea_id))


# ----------------------------------------------------------------- templates
@router.get("/templates", response_model=list[TemplateOut])
def list_templates(channel_id: int | None = Query(None), db: Session = Depends(get_db)):
    return template_service.list_templates(db, channel_id)


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(data: TemplateIn, db: Session = Depends(get_db)):
    return template_service.create_template(db, data)


@router.patch("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: int, data: TemplateUpdate, db: Session = Depends(get_db)):
    return template_service.update_template(db, template_service.get_template(db, template_id), data)


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: int, db: Session = Depends(get_db)):
    template_service.delete_template(db, template_service.get_template(db, template_id))
