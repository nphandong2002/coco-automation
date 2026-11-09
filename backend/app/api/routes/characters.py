"""Character routes, always scoped by channel: /channels/{channel_id}/characters/..."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.character import (
    CharacterCreate,
    CharacterOut,
    CharacterUpdate,
    GrantCreate,
    RoleUpdate,
    VersionCreate,
    VersionOut,
)
from app.services import character_service as svc
from app.services.channel_service import get_channel

router = APIRouter(tags=["characters"])
base = "/channels/{channel_id}/characters"


@router.get("/characters", response_model=list[CharacterOut])
def list_all_characters(db: Session = Depends(get_db)):
    """All characters, each seen from its owner channel."""
    return svc.list_all_owned(db)


@router.get(base, response_model=list[CharacterOut])
def list_characters(channel_id: int, include_archived: bool = True, db: Session = Depends(get_db)):
    get_channel(db, channel_id)
    return svc.list_for_channel(db, channel_id, include_archived)


@router.post(base, response_model=CharacterOut, status_code=201)
def create_character(channel_id: int, data: CharacterCreate, db: Session = Depends(get_db)):
    link = svc.create_character(db, get_channel(db, channel_id), data)
    return svc.character_out(db, link)


@router.get(base + "/{character_id}", response_model=CharacterOut)
def get_character(channel_id: int, character_id: int, db: Session = Depends(get_db)):
    return svc.character_out(db, svc.get_link(db, channel_id, character_id))


@router.patch(base + "/{character_id}", response_model=CharacterOut)
def update_character(channel_id: int, character_id: int, data: CharacterUpdate,
                     db: Session = Depends(get_db)):
    link = svc.update_character(db, svc.get_link(db, channel_id, character_id), data)
    return svc.character_out(db, link)


@router.delete(base + "/{character_id}", status_code=204)
def delete_character(channel_id: int, character_id: int, db: Session = Depends(get_db)):
    svc.delete_character(db, svc.get_link(db, channel_id, character_id))


@router.put(base + "/{character_id}/role", response_model=CharacterOut)
def set_role(channel_id: int, character_id: int, data: RoleUpdate, db: Session = Depends(get_db)):
    link = svc.set_role(db, svc.get_link(db, channel_id, character_id), data.role)
    return svc.character_out(db, link)


@router.get(base + "/{character_id}/versions", response_model=list[VersionOut])
def list_versions(channel_id: int, character_id: int, db: Session = Depends(get_db)):
    return svc.list_versions(db, svc.get_link(db, channel_id, character_id))


@router.post(base + "/{character_id}/versions", response_model=CharacterOut, status_code=201)
def create_version(channel_id: int, character_id: int, data: VersionCreate,
                   db: Session = Depends(get_db)):
    link = svc.create_version(db, svc.get_link(db, channel_id, character_id), data)
    return svc.character_out(db, link)


@router.post(base + "/{character_id}/versions/{version_id}/activate", response_model=CharacterOut)
def activate_version(channel_id: int, character_id: int, version_id: int,
                     db: Session = Depends(get_db)):
    link = svc.activate_version(db, svc.get_link(db, channel_id, character_id), version_id)
    return svc.character_out(db, link)


@router.post(base + "/{character_id}/images", response_model=CharacterOut, status_code=201)
def upload_image(
    channel_id: int,
    character_id: int,
    slot: str = Form(..., description="avatar | full_body | reference | expression"),
    expression_name: str | None = Form(None),
    change_note: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    data = file.file.read()
    link = svc.upload_image(db, svc.get_link(db, channel_id, character_id), slot, data,
                            expression_name, change_note)
    return svc.character_out(db, link)


@router.delete(base + "/{character_id}/images", response_model=CharacterOut)
def remove_image(channel_id: int, character_id: int,
                 slot: str = Query(...), key: str = Query(""), db: Session = Depends(get_db)):
    link = svc.remove_image(db, svc.get_link(db, channel_id, character_id), slot, key)
    return svc.character_out(db, link)


@router.post(base + "/{character_id}/grants", response_model=CharacterOut, status_code=201)
def grant(channel_id: int, character_id: int, data: GrantCreate, db: Session = Depends(get_db)):
    link = svc.grant(db, svc.get_link(db, channel_id, character_id), data)
    return svc.character_out(db, link)


@router.delete(base + "/{character_id}/grants/{target_channel_id}", response_model=CharacterOut)
def revoke(channel_id: int, character_id: int, target_channel_id: int, db: Session = Depends(get_db)):
    link = svc.revoke(db, svc.get_link(db, channel_id, character_id), target_channel_id)
    return svc.character_out(db, link)
