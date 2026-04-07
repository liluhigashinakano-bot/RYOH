from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from ..database import get_db
from .. import models
from ..auth import get_current_user

router = APIRouter(prefix="/api/app-settings", tags=["app-settings"])

# ──────────────────────────────────────────
# デフォルトインセンティブ（固定ドリンク種別）
# ──────────────────────────────────────────
DEFAULT_INCENTIVES = [
    {"drink_type": "drink_l",   "label": "Lドリンク"},
    {"drink_type": "drink_mg",  "label": "MGドリンク"},
    {"drink_type": "drink_s",   "label": "Sドリンク"},
    {"drink_type": "shot_cast", "label": "キャストショット"},
    {"drink_type": "champagne", "label": "シャンパン"},
]
DEFAULT_DRINK_TYPES = {d["drink_type"] for d in DEFAULT_INCENTIVES}


# ──────────────────────────────────────────
# Pydantic スキーマ
# ──────────────────────────────────────────
class MenuItemIn(BaseModel):
    store_id: int
    label: str
    price: int = 0
    cast_required: bool = True
    has_incentive: bool = False
    is_active: bool = True
    sort_order: int = 0


class MenuItemUpdate(BaseModel):
    label: Optional[str] = None
    price: Optional[int] = None
    cast_required: Optional[bool] = None
    has_incentive: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class IncentiveItemIn(BaseModel):
    drink_type: str
    incentive_mode: str = "percent"   # 'percent' | 'fixed'
    rate: int = 10
    fixed_amount: Optional[int] = None


class IncentiveBulkUpdate(BaseModel):
    store_id: int
    items: List[IncentiveItemIn]


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
            "has_incentive": m.has_incentive or False,
            "is_active": m.is_active,
            "sort_order": m.sort_order,
        }
        for m in items
    ]


@router.post("/menu")
def create_menu_item(body: MenuItemIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = models.MenuItemConfig(
        store_id=body.store_id,
        label=body.label,
        price=body.price,
        cast_required=body.cast_required,
        has_incentive=body.has_incentive,
        is_active=body.is_active,
        sort_order=body.sort_order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    # インセンティブありの場合、IncentiveConfigにデフォルト設定を作成
    if body.has_incentive:
        drink_type = f"menu_{item.id}"
        existing = db.query(models.IncentiveConfig).filter(
            models.IncentiveConfig.store_id == body.store_id,
            models.IncentiveConfig.drink_type == drink_type,
        ).first()
        if not existing:
            db.add(models.IncentiveConfig(
                store_id=body.store_id,
                drink_type=drink_type,
                incentive_mode="percent",
                rate=10,
            ))
            db.commit()
    return {
        "id": item.id, "label": item.label, "price": item.price,
        "cast_required": item.cast_required, "has_incentive": item.has_incentive,
        "is_active": item.is_active, "store_id": item.store_id, "sort_order": item.sort_order,
    }


@router.put("/menu/{item_id}")
def update_menu_item(item_id: int, body: MenuItemUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.MenuItemConfig).filter(models.MenuItemConfig.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    db.commit()

    # has_incentiveがTrueに変わった場合、IncentiveConfigを自動作成
    if body.has_incentive is True:
        drink_type = f"menu_{item_id}"
        existing = db.query(models.IncentiveConfig).filter(
            models.IncentiveConfig.store_id == item.store_id,
            models.IncentiveConfig.drink_type == drink_type,
        ).first()
        if not existing:
            db.add(models.IncentiveConfig(
                store_id=item.store_id,
                drink_type=drink_type,
                incentive_mode="percent",
                rate=10,
            ))
            db.commit()
    return {"ok": True}


@router.delete("/menu/{item_id}")
def delete_menu_item(item_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.MenuItemConfig).filter(models.MenuItemConfig.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    # 関連するIncentiveConfigも削除
    db.query(models.IncentiveConfig).filter(
        models.IncentiveConfig.drink_type == f"menu_{item_id}"
    ).delete()
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
    config_map = {c.drink_type: c for c in configs}

    result = []

    # 固定ドリンク種別
    for d in DEFAULT_INCENTIVES:
        cfg = config_map.get(d["drink_type"])
        result.append({
            "drink_type": d["drink_type"],
            "label": d["label"],
            "incentive_mode": cfg.incentive_mode if cfg else "percent",
            "rate": cfg.rate if cfg else 10,
            "fixed_amount": cfg.fixed_amount if cfg else None,
            "is_custom": False,
        })

    # カスタムメニュー（has_incentive=True）
    custom_menus = db.query(models.MenuItemConfig).filter(
        models.MenuItemConfig.store_id == store_id,
        models.MenuItemConfig.has_incentive == True,
        models.MenuItemConfig.is_active == True,
    ).all()
    for m in custom_menus:
        drink_type = f"menu_{m.id}"
        cfg = config_map.get(drink_type)
        result.append({
            "drink_type": drink_type,
            "label": m.label,
            "incentive_mode": cfg.incentive_mode if cfg else "percent",
            "rate": cfg.rate if cfg else 10,
            "fixed_amount": cfg.fixed_amount if cfg else None,
            "is_custom": True,
            "menu_price": m.price,
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
            existing.incentive_mode = item.incentive_mode
            existing.rate = item.rate
            existing.fixed_amount = item.fixed_amount
        else:
            db.add(models.IncentiveConfig(
                store_id=body.store_id,
                drink_type=item.drink_type,
                incentive_mode=item.incentive_mode,
                rate=item.rate,
                fixed_amount=item.fixed_amount,
            ))
    db.commit()
    return {"ok": True}
