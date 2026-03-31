import os
import time
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import date
from ..database import get_db
from .. import models
from ..auth import get_current_user

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "uploads", "casts")

router = APIRouter(prefix="/api/casts", tags=["casts"])

MANAGER_ROLES = {models.UserRole.superadmin, models.UserRole.manager, models.UserRole.editor}


class CastCreate(BaseModel):
    stage_name: str
    rank: str = "C"
    hourly_rate: int = 1400
    help_hourly_rate: int = 1500
    alcohol_tolerance: str = "普通"
    main_time_slot: Optional[str] = None
    transport_need: bool = False
    nearest_station: Optional[str] = None
    notes: Optional[str] = None
    birthday: Optional[date] = None
    employment_start_date: Optional[date] = None
    last_rate_change_date: Optional[date] = None


class CastUpdate(BaseModel):
    stage_name: Optional[str] = None
    rank: Optional[str] = None
    hourly_rate: Optional[int] = None
    help_hourly_rate: Optional[int] = None
    alcohol_tolerance: Optional[str] = None
    main_time_slot: Optional[str] = None
    transport_need: Optional[bool] = None
    nearest_station: Optional[str] = None
    notes: Optional[str] = None
    birthday: Optional[date] = None
    employment_start_date: Optional[date] = None
    last_rate_change_date: Optional[date] = None


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
    photo_url: Optional[str]
    birthday: Optional[date]
    employment_start_date: Optional[date]
    last_rate_change_date: Optional[date]
    is_active: bool

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_cast(cls, cast: models.Cast):
        photo_url = f"/uploads/casts/{cast.photo_path}" if cast.photo_path else None
        return cls(
            id=cast.id,
            store_id=cast.store_id,
            stage_name=cast.stage_name,
            rank=cast.rank,
            hourly_rate=cast.hourly_rate,
            help_hourly_rate=cast.help_hourly_rate,
            alcohol_tolerance=cast.alcohol_tolerance,
            main_time_slot=cast.main_time_slot,
            transport_need=cast.transport_need,
            nearest_station=cast.nearest_station,
            notes=cast.notes,
            photo_url=photo_url,
            birthday=cast.birthday,
            employment_start_date=cast.employment_start_date,
            last_rate_change_date=cast.last_rate_change_date,
            is_active=cast.is_active,
        )


@router.get("/{store_id}", response_model=list[CastResponse])
def get_casts(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    casts = db.query(models.Cast).filter(
        models.Cast.store_id == store_id,
        models.Cast.is_active == True
    ).all()
    return [CastResponse.from_orm_cast(c) for c in casts]


@router.get("/{store_id}/{cast_id}", response_model=CastResponse)
def get_cast(
    store_id: int,
    cast_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cast = db.query(models.Cast).filter(
        models.Cast.id == cast_id,
        models.Cast.store_id == store_id,
    ).first()
    if not cast:
        raise HTTPException(status_code=404, detail="キャストが見つかりません")
    return CastResponse.from_orm_cast(cast)


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
    return CastResponse.from_orm_cast(cast)


@router.put("/{store_id}/{cast_id}", response_model=CastResponse)
def update_cast(
    store_id: int,
    cast_id: int,
    data: CastUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cast = db.query(models.Cast).filter(
        models.Cast.id == cast_id,
        models.Cast.store_id == store_id
    ).first()
    if not cast:
        raise HTTPException(status_code=404, detail="キャストが見つかりません")

    update_data = data.model_dump(exclude_none=True)

    # 時給変更は管理者・編集者のみ
    if "hourly_rate" in update_data or "help_hourly_rate" in update_data:
        if current_user.role not in MANAGER_ROLES:
            raise HTTPException(status_code=403, detail="時給変更は管理者・編集者のみ可能です")

    for field, value in update_data.items():
        setattr(cast, field, value)
    db.commit()
    db.refresh(cast)
    return CastResponse.from_orm_cast(cast)


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


@router.post("/{store_id}/{cast_id}/photo")
async def upload_cast_photo(
    store_id: int,
    cast_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cast = db.query(models.Cast).filter(
        models.Cast.id == cast_id,
        models.Cast.store_id == store_id,
    ).first()
    if not cast:
        raise HTTPException(status_code=404, detail="キャストが見つかりません")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise HTTPException(status_code=400, detail="jpg/png/webp/gif のみ対応しています")
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    filename = f"{cast_id}_{int(time.time())}{ext}"
    save_path = os.path.join(UPLOADS_DIR, filename)
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    cast.photo_path = filename
    db.commit()
    return {"photo_url": f"/uploads/casts/{filename}"}


@router.get("/{store_id}/{cast_id}/stats")
def get_cast_stats(
    store_id: int,
    cast_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cast = db.query(models.Cast).filter(
        models.Cast.id == cast_id,
        models.Cast.store_id == store_id,
    ).first()
    if not cast:
        raise HTTPException(status_code=404, detail="キャストが見つかりません")

    shifts = db.query(models.ConfirmedShift).filter(
        models.ConfirmedShift.cast_id == cast_id,
        models.ConfirmedShift.store_id == store_id,
    ).all()

    total_minutes = 0.0
    weekday_minutes: dict[int, list[float]] = defaultdict(list)
    monthly_counts: dict[str, int] = defaultdict(int)
    # 当欠率・遅刻率・日払い率用：月ごとに集計
    monthly_total_rows: dict[str, int] = defaultdict(int)
    monthly_absent_rows: dict[str, int] = defaultdict(int)
    monthly_late_rows: dict[str, int] = defaultdict(int)
    monthly_daily_pay_rows: dict[str, int] = defaultdict(int)

    # shift_data から集計（Excelインポート分）
    total_set_l = total_set_mg = total_set_shot = 0.0
    total_champagne_back = total_drink_back = 0
    total_drink_count = total_rt = total_nt = total_dist = 0
    daily_pay_count = 0

    for s in shifts:
        month_key = s.date.strftime("%Y-%m")
        # キャスト名が入力されている行（=シフトレコード全件）をカウント
        monthly_total_rows[month_key] += 1
        if s.is_late:
            monthly_late_rows[month_key] += 1
        if s.is_absent:
            monthly_absent_rows[month_key] += 1
            continue

        sd = s.shift_data or {}
        wh = sd.get("working_hours", 0) or 0
        if wh > 0:
            mins = wh * 60
        elif s.actual_start and s.actual_end:
            mins = (s.actual_end - s.actual_start).total_seconds() / 60
        else:
            mins = 0

        # 出勤/退勤の数値がある件数のみカウント（欠勤は既に除外済み）
        if mins > 0:
            monthly_counts[month_key] += 1

        if mins > 0:
            total_minutes += mins
            weekday_minutes[s.date.weekday()].append(mins)

        total_set_l += sd.get("set_l", 0) or 0
        total_set_mg += sd.get("set_mg", 0) or 0
        total_set_shot += sd.get("set_shot", 0) or 0
        total_champagne_back += sd.get("champagne_back", 0) or 0
        total_drink_back += sd.get("drink_back", 0) or 0
        total_drink_count += sd.get("drink_count", 0) or 0
        total_rt += sd.get("rt_count", 0) or 0
        total_nt += sd.get("nt_count", 0) or 0
        total_dist += sd.get("distribution_count", 0) or 0
        if sd.get("daily_payment", 0):
            daily_pay_count += 1
            if mins > 0:
                monthly_daily_pay_rows[month_key] += 1

    avg_monthly_shifts = (
        sum(monthly_counts.values()) / len(monthly_counts) if monthly_counts else 0
    )

    WEEKDAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]
    weekday_avg = {
        WEEKDAY_NAMES[wd]: round(sum(mins) / len(mins) / 60, 2)
        for wd, mins in weekday_minutes.items()
    }

    # セット数（40分/セット）
    total_sets = total_minutes / 40 if total_minutes > 0 else 0
    total_hours = total_minutes / 60
    # 実際に出勤した月（working_hours > 0 の記録がある月）のみカウント
    active_months = set(monthly_counts.keys())
    num_months = len(active_months) if active_months else 1
    avg_monthly_hours = round(total_hours / num_months, 1)
    total_shifts = sum(monthly_total_rows.values())
    absent_shifts = sum(monthly_absent_rows.values())
    effective_shifts = total_shifts - absent_shifts

    # 当欠率：出勤があった月のみ対象
    monthly_absent_rates = []
    for mk in active_months:
        total_rows = monthly_total_rows.get(mk, 0)
        absent_rows = monthly_absent_rows.get(mk, 0)
        if total_rows > 0:
            monthly_absent_rates.append(absent_rows / total_rows * 100)
    avg_absent_rate = round(sum(monthly_absent_rates) / len(monthly_absent_rates), 1) if monthly_absent_rates else 0

    # 遅刻率：出勤があった月のみ対象
    monthly_late_rates = []
    for mk in active_months:
        total_rows = monthly_total_rows.get(mk, 0)
        late_rows = monthly_late_rows.get(mk, 0)
        if total_rows > 0:
            monthly_late_rates.append(late_rows / total_rows * 100)
    avg_late_rate = round(sum(monthly_late_rates) / len(monthly_late_rates), 1) if monthly_late_rates else 0

    # 日払い率：月ごとに 日払い件数÷出勤退勤数値あり件数 を計算して平均
    monthly_daily_pay_rates = []
    for mk in monthly_counts:
        worked = monthly_counts[mk]
        paid = monthly_daily_pay_rows.get(mk, 0)
        if worked > 0:
            monthly_daily_pay_rates.append(paid / worked * 100)
    avg_daily_pay_rate = round(sum(monthly_daily_pay_rates) / len(monthly_daily_pay_rates), 1) if monthly_daily_pay_rates else 0

    def per_set(total: float) -> float:
        return round(total / total_sets, 2) if total_sets > 0 else 0

    def per_shift(total: float) -> float:
        return round(total / effective_shifts, 2) if effective_shifts > 0 else 0

    # 実質時給 = 基本時給 + 1セット(40分)あたりDバック
    d_back_per_set = round(total_drink_back / total_sets, 0) if total_sets > 0 else 0
    real_hourly = cast.hourly_rate + int(d_back_per_set)

    return {
        "hourly_rate": cast.hourly_rate,
        "help_hourly_rate": cast.help_hourly_rate,
        "real_hourly_rate": real_hourly,
        "total_shifts": total_shifts,
        "avg_monthly_shifts": round(avg_monthly_shifts, 1),
        "avg_monthly_hours": avg_monthly_hours,
        "weekday_avg_hours": weekday_avg,
        "absent_rate": avg_absent_rate,
        "late_rate": avg_late_rate,
        "per_set_drinks": per_set(total_set_l),
        "per_set_mg": per_set(total_set_mg),
        "per_set_shots": per_set(total_set_shot),
        "per_set_champagne_back": per_set(total_champagne_back),
        "per_set_drink_back": per_set(total_drink_back),
        "per_shift_rt": per_shift(total_rt),
        "per_shift_nt": per_shift(total_nt),
        "per_shift_distribution": per_shift(total_dist),
        "daily_pay_count": daily_pay_count,
        "daily_pay_ratio": avg_daily_pay_rate,
    }


@router.get("/{store_id}/{cast_id}/shifts")
def get_cast_shifts(
    store_id: int,
    cast_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    shifts = db.query(models.ConfirmedShift).filter(
        models.ConfirmedShift.cast_id == cast_id,
        models.ConfirmedShift.store_id == store_id,
    ).order_by(models.ConfirmedShift.date.desc()).limit(60).all()

    result = []
    for s in shifts:
        actual_hours = None
        if s.actual_start and s.actual_end:
            actual_hours = round((s.actual_end - s.actual_start).total_seconds() / 3600, 1)
        pay = s.daily_pay
        result.append({
            "id": s.id,
            "date": s.date.isoformat(),
            "planned_start": s.planned_start,
            "planned_end": s.planned_end,
            "actual_start": s.actual_start.isoformat() if s.actual_start else None,
            "actual_end": s.actual_end.isoformat() if s.actual_end else None,
            "actual_hours": actual_hours,
            "is_late": s.is_late,
            "is_absent": s.is_absent,
            "total_pay": pay.total_pay if pay else None,
            "drink_back": pay.drink_back if pay else None,
            "champagne_back": pay.champagne_back if pay else None,
            "honshimei_back": pay.honshimei_back if pay else None,
        })
    return result
