from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from ..database import get_db
from .. import models
from ..auth import get_current_user

router = APIRouter(prefix="/api/casts", tags=["casts"])


class CastCreate(BaseModel):
    stage_name: str
    real_name: Optional[str] = None
    rank: str = "C"
    hourly_rate: int = 1400
    help_hourly_rate: int = 1500
    alcohol_tolerance: str = "普通"
    main_time_slot: Optional[str] = None
    transport_need: bool = False
    nearest_station: Optional[str] = None
    notes: Optional[str] = None


class CastResponse(BaseModel):
    id: int
    store_id: int
    stage_name: str
    rank: str
    hourly_rate: int
    help_hourly_rate: int
    alcohol_tolerance: Optional[str]
    main_time_slot: Optional[str]
    transport_need: bool
    nearest_station: Optional[str]
    notes: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/{store_id}", response_model=list[CastResponse])
def get_casts(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return db.query(models.Cast).filter(
        models.Cast.store_id == store_id,
        models.Cast.is_active == True
    ).all()


@router.post("/{store_id}", response_model=CastResponse)
def create_cast(
    store_id: int,
    data: CastCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cast = models.Cast(store_id=store_id, **data.model_dump())
    db.add(cast)
    db.commit()
    db.refresh(cast)
    return cast


@router.put("/{store_id}/{cast_id}", response_model=CastResponse)
def update_cast(
    store_id: int,
    cast_id: int,
    data: CastCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cast = db.query(models.Cast).filter(
        models.Cast.id == cast_id,
        models.Cast.store_id == store_id
    ).first()
    if not cast:
        raise HTTPException(status_code=404, detail="キャストが見つかりません")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(cast, field, value)
    db.commit()
    db.refresh(cast)
    return cast


@router.delete("/{store_id}/{cast_id}")
def delete_cast(
    store_id: int,
    cast_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cast = db.query(models.Cast).filter(
        models.Cast.id == cast_id,
        models.Cast.store_id == store_id
    ).first()
    if not cast:
        raise HTTPException(status_code=404, detail="キャストが見つかりません")
    cast.is_active = False
    db.commit()
    return {"message": "キャストを削除しました"}
