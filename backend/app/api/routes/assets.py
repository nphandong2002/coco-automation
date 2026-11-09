from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enums import AssetKind, LicenseType
from app.schemas.asset import AssetOut, AssetUpdate, BackgroundGenerate
from app.services import asset_service as svc
from app.services.channel_service import get_channel

router = APIRouter(tags=["assets"])


@router.get("/assets", response_model=list[AssetOut])
def list_assets(scope: str = Query("all", description="all | shared | channel | usable"),
                channel_id: int | None = None, kind: AssetKind | None = None, q: str | None = None,
                db: Session = Depends(get_db)):
    return svc.list_assets(db, scope=scope, channel_id=channel_id, kind=kind, q=q)


@router.get("/channels/{channel_id}/assets", response_model=list[AssetOut])
def usable_assets(channel_id: int, kind: AssetKind | None = None, db: Session = Depends(get_db)):
    """Assets the channel may use: its own + the shared library."""
    get_channel(db, channel_id)
    return svc.list_assets(db, scope="usable", channel_id=channel_id, kind=kind)


@router.post("/assets", response_model=AssetOut, status_code=201)
def upload_asset(
    file: UploadFile = File(...),
    license_type: LicenseType = Form(...),
    license_source: str = Form(""),
    attribution: str = Form(""),
    name: str = Form(""),
    tags: str = Form("", description="phân tách bằng dấu phẩy"),
    channel_id: int | None = Form(None, description="bỏ trống = thư viện dùng chung"),
    db: Session = Depends(get_db),
):
    return svc.create_from_upload(db, file, channel_id=channel_id, name=name, license_type=license_type,
                                  license_source=license_source, attribution=attribution,
                                  tags=[t for t in tags.split(",") if t.strip()])


@router.post("/assets/generate-background", response_model=AssetOut, status_code=201)
def generate_background(data: BackgroundGenerate, db: Session = Depends(get_db)):
    return svc.generate_background(db, data)


@router.get("/assets/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    a = svc.get_asset(db, asset_id)
    return svc.asset_out(a)


@router.get("/assets/{asset_id}/usages")
def asset_usages(asset_id: int, db: Session = Depends(get_db)):
    return svc.usages(db, svc.get_asset(db, asset_id))


@router.patch("/assets/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: int, data: AssetUpdate, db: Session = Depends(get_db)):
    return svc.update_asset(db, svc.get_asset(db, asset_id), data)


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    svc.delete_asset(db, svc.get_asset(db, asset_id))
