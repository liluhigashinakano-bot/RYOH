from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import date
from ..database import get_db
from .. import models
from ..auth import get_current_user

router = APIRouter(prefix="/api/next-visits", tags=["next-visits"])


class NextVisitCreate(BaseModel):
    store_id: int
    customer_id: int
    ticket_id: Optional[int] = None
    visit_date: date
    visit_time: Optional[str] = None  # "20:00" or null
    cast_id: Optional[int] = None
    note: Optional[str] = None


class NextVisitUpdate(BaseModel):
    visit_date: Optional[date] = None
    visit_time: Optional[str] = None
    cast_id: Optional[int] = None
    note: Optional[str] = None
    is_done: Optional[bool] = None


def _to_response(nv: models.NextVisit) -> dict:
    return {
        "id": nv.id,
        "store_id": nv.store_id,
        "customer_id": nv.customer_id,
        "customer_name": nv.customer.name if nv.customer else None,
        "ticket_id": nv.ticket_id,
        "visit_date": nv.visit_date.isoformat() if nv.visit_date else None,
        "visit_time": nv.visit_time,
        "cast_id": nv.cast_id,
        "cast_name": nv.cast.stage_name if nv.cast else None,
        "note": nv.note,
        "is_done": nv.is_done,
        "created_at": nv.created_at.isoformat() if nv.created_at else None,
    }


@router.post("")
def create_next_visit(
    data: NextVisitCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    nv = models.NextVisit(**data.model_dump())
    db.add(nv)
    db.commit()
    db.refresh(nv)
    return _to_response(nv)


@router.get("")
def get_next_visits(
    store_id: int = Query(...),
    visit_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.NextVisit).filter(
        models.NextVisit.store_id == store_id,
        models.NextVisit.is_done == False,
    )
    if visit_date:
        q = q.filter(models.NextVisit.visit_date == visit_date)
    visits = q.order_by(models.NextVisit.visit_date, models.NextVisit.visit_time).all()
    return [_to_response(v) for v in visits]


@router.get("/customer/{customer_id}")
def get_customer_next_visits(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    visits = db.query(models.NextVisit).filter(
        models.NextVisit.customer_id == customer_id,
        models.NextVisit.is_done == False,
    ).order_by(models.NextVisit.visit_date).all()
    return [_to_response(v) for v in visits]


@router.put("/{nv_id}")
def update_next_visit(
    nv_id: int,
    data: NextVisitUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    nv = db.query(models.NextVisit).filter(models.NextVisit.id == nv_id).first()
    if not nv:
        raise HTTPException(status_code=404, detail="来店予定が見つかりません")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(nv, field, value)
    db.commit()
    db.refresh(nv)
    return _to_response(nv)


@router.delete("/{nv_id}")
def delete_next_visit(
    nv_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    nv = db.query(models.NextVisit).filter(models.NextVisit.id == nv_id).first()
    if not nv:
        raise HTTPException(status_code=404, detail="来店予定が見つかりません")
    db.delete(nv)
    db.commit()
    return {"message": "削除しました"}
