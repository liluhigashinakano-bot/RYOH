from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from ..database import get_db
from .. import models
from ..auth import get_current_user, require_superadmin

router = APIRouter(prefix="/api/stores", tags=["stores"])


class StoreCreate(BaseModel):
    name: str
    code: str
    set_price: int = 0
    extension_price: int = 0
    address: Optional[str] = None
    phone: Optional[str] = None


class StoreUpdate(BaseModel):
    name: Optional[str] = None
    set_price: Optional[int] = None
    extension_price: Optional[int] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


class StoreResponse(BaseModel):
    id: int
    name: str
    code: str
    set_price: int
    extension_price: int
    address: Optional[str]
    phone: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


@router.get("", response_model=list[StoreResponse])
def get_stores(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role == models.UserRole.superadmin:
        return db.query(models.Store).filter(models.Store.is_active == True).all()
    if current_user.store_id:
        return db.query(models.Store).filter(
            models.Store.id == current_user.store_id,
            models.Store.is_active == True
        ).all()
    return []


@router.post("", response_model=StoreResponse)
def create_store(
    data: StoreCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superadmin),
):
    existing = db.query(models.Store).filter(models.Store.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="このコードは既に使用されています")
    store = models.Store(**data.model_dump())
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@router.put("/{store_id}", response_model=StoreResponse)
def update_store(
    store_id: int,
    data: StoreUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superadmin),
):
    store = db.query(models.Store).filter(models.Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(store, field, value)
    db.commit()
    db.refresh(store)
    return store


@router.delete("/{store_id}")
def delete_store(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superadmin),
):
    store = db.query(models.Store).filter(models.Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません")
    store.is_active = False
    db.commit()
    return {"message": "店舗を削除しました"}
