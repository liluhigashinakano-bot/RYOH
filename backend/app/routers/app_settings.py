from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from ..database import get_db
from .. import models
from ..auth import get_current_user

router = APIRouter(prefix="/api/app-settings", tags=["app-settings"])

# ──────────────────────────────────────────
# デフォルトインセンティブ率
# ──────────────────────────────────────────
DEFAULT_INCENTIVES = [
    {"drink_type": "drink_l",   "label": "Lドリンク",       "rate": 10},
    {"drink_type": "drink_mg",  "label": "MGドリンク",      "rate": 10},
    {"drink_type": "drink_s",   "label": "Sドリンク",       "rate": 10},
    {"drink_type": "shot_cast", "label": "キャストショット", "rate": 10},
    {"drink_type": "champagne", "label": "シャンパン",       "rate": 10},
]

DRINK_LABELS = {d["drink_type"]: d["label"] for d in DEFAULT_INCENTIVES}


# ──────────────────────────────────────────
# Pydantic スキーマ
# ──────────────────────────────────────────
class MenuItemIn(BaseModel):
    store_id: int
    label: str
    price: int = 0
    cast_required: bool = True
    is_active: bool = True
    sort_order: int = 0


class MenuItemUpdate(BaseModel):
    label: Optional[str] = None
    price: Optional[int] = None
    cast_required: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class IncentiveIn(BaseModel):
    store_id: int
    drink_type: str
    rate: int


class IncentiveBulkUpdate(BaseModel):
    store_id: int
    items: List[IncentiveIn]


# ──────────────────────────────────────────
# メニュー設定 CRUD
# ──────────────────────────────────────────
@router.get("/menu")
def get_menu_items(store_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    items = db.query(models.MenuItemConfig).filter(
        models.MenuItemConfig.store_id == store_id
    ).order_by(models.MenuItemConfig.sort_order, models.MenuItemConfig.id).all()
    return [
        {
            "id": m.id,
            "store_id": m.store_id,
            "label": m.label,
            "price": m.price,
            "cast_required": m.cast_required,
            "is_active": m.is_active,
            "sort_order": m.sort_order,
        }
        for m in items
    ]


@router.post("/menu")
def create_menu_item(body: MenuItemIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = models.MenuItemConfig(**body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "label": item.label, "price": item.price,
            "cast_required": item.cast_required, "is_active": item.is_active,
            "store_id": item.store_id, "sort_order": item.sort_order}


@router.put("/menu/{item_id}")
def update_menu_item(item_id: int, body: MenuItemUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.MenuItemConfig).filter(models.MenuItemConfig.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/menu/{item_id}")
def delete_menu_item(item_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.MenuItemConfig).filter(models.MenuItemConfig.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────
# インセンティブ設定
# ──────────────────────────────────────────
@router.get("/incentives")
def get_incentives(store_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    configs = db.query(models.IncentiveConfig).filter(
        models.IncentiveConfig.store_id == store_id
    ).all()
    config_map = {c.drink_type: c.rate for c in configs}

    result = []
    for d in DEFAULT_INCENTIVES:
        result.append({
            "drink_type": d["drink_type"],
            "label": d["label"],
            "rate": config_map.get(d["drink_type"], d["rate"]),
        })
    return result


@router.put("/incentives")
def update_incentives(body: IncentiveBulkUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    for item in body.items:
        existing = db.query(models.IncentiveConfig).filter(
            models.IncentiveConfig.store_id == body.store_id,
            models.IncentiveConfig.drink_type == item.drink_type,
        ).first()
        if existing:
            existing.rate = item.rate
        else:
            db.add(models.IncentiveConfig(
                store_id=body.store_id,
                drink_type=item.drink_type,
                rate=item.rate,
            ))
    db.commit()
    return {"ok": True}
