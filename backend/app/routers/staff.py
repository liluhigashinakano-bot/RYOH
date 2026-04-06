from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional
from pydantic import BaseModel
from datetime import date, timedelta

from ..database import get_db
from .. import models
from .auth import get_current_user

router = APIRouter(prefix="/api/staff", tags=["staff"])

POSITIONS = ["シニアMG", "エリアMG", "マスタークルー", "クルー①", "クルー②", "準社員"]


class StaffCreate(BaseModel):
    name: str
    employee_type: str  # "staff" | "part_time"
    position: Optional[str] = None
    hourly_rate: Optional[int] = None
    store_ids: List[int] = []
    notes: Optional[str] = None


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    position: Optional[str] = None
    hourly_rate: Optional[int] = None
    store_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


def staff_to_dict(s: models.StaffMember):
    return {
        "id": s.id,
        "name": s.name,
        "employee_type": s.employee_type,
        "position": s.position,
        "hourly_rate": s.hourly_rate,
        "store_ids": s.store_ids or [],
        "is_active": s.is_active,
        "notes": s.notes,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def calc_stats(name: str, store_ids: List[int], db: Session):
    """StaffAttendanceからの出勤統計を計算"""
    # 過去6ヶ月
    since = date.today() - timedelta(days=180)
    records = db.query(models.StaffAttendance).filter(
        models.StaffAttendance.name == name,
        models.StaffAttendance.store_id.in_(store_ids) if store_ids else True,
        models.StaffAttendance.date >= since,
    ).all()

    if not records:
        return None

    total = len(records)
    absent = sum(1 for r in records if r.is_absent)
    late = sum(1 for r in records if r.is_late)

    # 実働時間計算
    hours_list = []
    for r in records:
        if r.actual_start and r.actual_end and not r.is_absent:
            h = (r.actual_end - r.actual_start).total_seconds() / 3600
            hours_list.append(round(h, 1))

    avg_hours = round(sum(hours_list) / len(hours_list), 1) if hours_list else None

    # 月別出勤回数（平均）
    from collections import defaultdict
    monthly: dict = defaultdict(int)
    for r in records:
        if not r.is_absent:
            key = f"{r.date.year}-{r.date.month}"
            monthly[key] += 1
    avg_monthly = round(sum(monthly.values()) / len(monthly), 1) if monthly else 0

    return {
        "total_shifts": total,
        "absent_count": absent,
        "late_count": late,
        "absent_rate": round(absent / total * 100, 1) if total else 0,
        "late_rate": round(late / total * 100, 1) if total else 0,
        "avg_monthly_shifts": avg_monthly,
        "avg_actual_hours": avg_hours,
    }


@router.get("")
def list_staff(
    employee_type: Optional[str] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(models.StaffMember).filter(models.StaffMember.is_active == True)
    if employee_type:
        q = q.filter(models.StaffMember.employee_type == employee_type)
    members = q.order_by(models.StaffMember.name).all()

    result = []
    for m in members:
        d = staff_to_dict(m)
        if store_id and store_id not in (m.store_ids or []):
            continue
        result.append(d)
    return result


@router.post("")
def create_staff(
    body: StaffCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    m = models.StaffMember(
        name=body.name,
        employee_type=body.employee_type,
        position=body.position,
        hourly_rate=body.hourly_rate,
        store_ids=body.store_ids,
        notes=body.notes,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return staff_to_dict(m)


@router.get("/{staff_id}")
def get_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    m = db.query(models.StaffMember).filter(models.StaffMember.id == staff_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    d = staff_to_dict(m)
    d["stats"] = calc_stats(m.name, m.store_ids or [], db)
    return d


@router.put("/{staff_id}")
def update_staff(
    staff_id: int,
    body: StaffUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    m = db.query(models.StaffMember).filter(models.StaffMember.id == staff_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(m, field, val)
    db.commit()
    db.refresh(m)
    return staff_to_dict(m)


@router.delete("/{staff_id}")
def delete_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    m = db.query(models.StaffMember).filter(models.StaffMember.id == staff_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    m.is_active = False
    db.commit()
    return {"ok": True}
