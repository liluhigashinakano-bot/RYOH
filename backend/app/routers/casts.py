import os
import time
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from ..database import get_db
from .. import models
from ..auth import get_current_user

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "uploads", "casts")

router = APIRouter(prefix="/api/casts", tags=["casts"])

MANAGER_ROLES = {models.UserRole.superadmin, models.UserRole.manager, models.UserRole.editor}


def generate_cast_code(db: Session, store_id: int) -> str:
    """店舗IDに基づいてユニークなキャストコードを生成する（例: L001F0001）"""
    store = db.query(models.Store).filter(models.Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません")
    prefix = store.code  # 例: L001

    # この店舗の既存コードから最大番号を取得
    existing = db.query(models.Cast.cast_code).filter(
        models.Cast.cast_code.like(f"{prefix}F%"),
    ).all()
    max_num = 0
    for (code,) in existing:
        if code:
            try:
                num = int(code[len(prefix) + 1:])  # "L001F0042" → 42
                max_num = max(max_num, num)
            except ValueError:
                pass
    next_num = max_num + 1
    if next_num > 9999:
        raise HTTPException(status_code=400, detail="キャストIDの上限（9999）に達しました")
    return f"{prefix}F{next_num:04d}"


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
    is_active: Optional[bool] = None


class CastResponse(BaseModel):
    id: int
    store_id: int
    cast_code: Optional[str]
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
            cast_code=cast.cast_code,
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
    cast_code = generate_cast_code(db, store_id)
    cast = models.Cast(store_id=store_id, cast_code=cast_code, **data.model_dump())
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



# ─────────────────────────────────────────
# キャスト勤怠
# ─────────────────────────────────────────

class ClockInRequest(BaseModel):
    cast_id: int
    store_id: int
    actual_start: Optional[str] = None  # "HH:MM" JST、未指定なら現在時刻
    is_late: bool = False
    is_absent: bool = False


class AttendanceTimeUpdate(BaseModel):
    actual_start: Optional[str] = None  # "HH:MM" JST
    actual_end: Optional[str] = None    # "HH:MM" JST


@router.get("/attendance/working/{store_id}")
def get_attendance(store_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """本日勤務中のキャスト一覧（actual_start あり・actual_end なし）"""
    today = date.today()
    from sqlalchemy import or_
    # 当欠（is_absent=True）または出勤済み（actual_start あり）を取得
    shifts = (
        db.query(models.ConfirmedShift)
        .filter(
            models.ConfirmedShift.store_id == store_id,
            models.ConfirmedShift.date == today,
            or_(
                models.ConfirmedShift.actual_start.isnot(None),
                models.ConfirmedShift.is_absent == True,
            )
        )
        .order_by(models.ConfirmedShift.actual_start.nullslast())
        .all()
    )
    result = []
    for s in shifts:
        result.append({
            "shift_id": s.id,
            "cast_id": s.cast_id,
            "cast_name": s.cast.stage_name if s.cast else f"Cast{s.cast_id}",
            "actual_start": s.actual_start.isoformat() if s.actual_start else None,
            "actual_end": s.actual_end.isoformat() if s.actual_end else None,
            "is_late": bool(s.is_late),
            "is_absent": bool(s.is_absent),
        })
    return result


@router.post("/attendance/clock-in")
def clock_in(data: ClockInRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """出勤打刻: 本日のシフトに actual_start をセット。シフトがなければ当日分を新規作成"""
    today = date.today()
    from datetime import timedelta

    if data.actual_start:
        h, m = int(data.actual_start.split(':')[0]), int(data.actual_start.split(':')[1])
        # バー営業: 12時未満は翌日扱い
        d = today if h >= 12 else today + timedelta(days=1)
        now = datetime(d.year, d.month, d.day, h, m) - timedelta(hours=9)
    else:
        now = datetime.utcnow()

    # 既に出勤中なら何もしない
    already = db.query(models.ConfirmedShift).filter(
        models.ConfirmedShift.cast_id == data.cast_id,
        models.ConfirmedShift.store_id == data.store_id,
        models.ConfirmedShift.date == today,
        models.ConfirmedShift.actual_start.isnot(None),
        models.ConfirmedShift.actual_end.is_(None),
    ).first()
    if already:
        return {"shift_id": already.id, "message": "既に出勤中です"}

    # 本日のシフトを探す
    shift = db.query(models.ConfirmedShift).filter(
        models.ConfirmedShift.cast_id == data.cast_id,
        models.ConfirmedShift.store_id == data.store_id,
        models.ConfirmedShift.date == today,
    ).first()

    if data.is_absent:
        # 当欠: actual_start なし、is_absent=True
        if shift:
            shift.is_absent = True
            shift.actual_start = None
            shift.actual_end = None
        else:
            shift = models.ConfirmedShift(
                cast_id=data.cast_id,
                store_id=data.store_id,
                date=today,
                is_absent=True,
            )
            db.add(shift)
        db.commit()
        db.refresh(shift)
        return {"shift_id": shift.id, "message": "当欠で登録しました"}

    if shift:
        shift.actual_start = now
        shift.actual_end = None
        shift.is_late = data.is_late
        shift.is_absent = False
    else:
        shift = models.ConfirmedShift(
            cast_id=data.cast_id,
            store_id=data.store_id,
            date=today,
            actual_start=now,
            is_late=data.is_late,
        )
        db.add(shift)

    db.commit()
    db.refresh(shift)
    return {"shift_id": shift.id, "message": "出勤しました"}


class ClockOutRequest(BaseModel):
    actual_end: Optional[str] = None  # "HH:MM" JST、未指定なら現在時刻


@router.post("/attendance/{shift_id}/clock-out")
def clock_out(shift_id: int, data: ClockOutRequest = ClockOutRequest(), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """退勤打刻"""
    from datetime import timedelta
    shift = db.query(models.ConfirmedShift).filter(models.ConfirmedShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="シフトが見つかりません")
    if data.actual_end:
        h, m = int(data.actual_end.split(':')[0]), int(data.actual_end.split(':')[1])
        d = shift.date if h >= 12 else shift.date + timedelta(days=1)
        shift.actual_end = datetime(d.year, d.month, d.day, h, m) - timedelta(hours=9)
    else:
        shift.actual_end = datetime.utcnow()
    db.commit()
    return {"message": "退勤しました"}


@router.patch("/attendance/{shift_id}/time")
def update_attendance_time(shift_id: int, data: AttendanceTimeUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """出退勤時刻を修正（HH:MM JST で受け取り UTC に変換して保存）"""
    shift = db.query(models.ConfirmedShift).filter(models.ConfirmedShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="シフトが見つかりません")

    def hhmm_jst_to_utc(hhmm: str, base_date: date) -> datetime:
        h, m = int(hhmm.split(':')[0]), int(hhmm.split(':')[1])
        # バー営業は深夜をまたぐため、時刻が12時未満なら翌日扱い
        from datetime import timedelta
        d = base_date if h >= 12 else base_date + timedelta(days=1)
        jst_dt = datetime(d.year, d.month, d.day, h, m)
        return jst_dt - timedelta(hours=9)

    if data.actual_start:
        shift.actual_start = hhmm_jst_to_utc(data.actual_start, shift.date)
    if data.actual_end:
        shift.actual_end = hhmm_jst_to_utc(data.actual_end, shift.date)

    db.commit()
    return {"message": "時刻を更新しました"}


@router.post("/attendance/{shift_id}/remove")
def delete_attendance(shift_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """出勤記録を削除（actual_start/actual_end をクリア）"""
    shift = db.query(models.ConfirmedShift).filter(models.ConfirmedShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="シフトが見つかりません")
    # シフト自体は残してタイムスタンプのみクリア
    shift.actual_start = None
    shift.actual_end = None
    db.commit()
    return {"message": "出勤記録を削除しました"}


# ─────────────────────────────────────────
# 社員/アルバイト勤怠
# ─────────────────────────────────────────

class StaffClockInRequest(BaseModel):
    store_id: int
    name: str
    actual_start: Optional[str] = None  # "HH:MM" JST
    is_late: bool = False
    is_absent: bool = False


class StaffTimeUpdate(BaseModel):
    actual_start: Optional[str] = None  # "HH:MM" JST
    actual_end: Optional[str] = None    # "HH:MM" JST


def _hhmm_to_utc(hhmm: str, base_date) -> datetime:
    """HH:MM JST (バー営業対応) → UTC datetime"""
    from datetime import timedelta
    h, m = int(hhmm.split(':')[0]), int(hhmm.split(':')[1])
    d = base_date if h >= 12 else base_date + timedelta(days=1)
    return datetime(d.year, d.month, d.day, h, m) - timedelta(hours=9)


@router.get("/staff-attendance/today/{store_id}")
def get_staff_attendance(store_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """本日の社員/アルバイト勤怠一覧"""
    today = date.today()
    records = db.query(models.StaffAttendance).filter(
        models.StaffAttendance.store_id == store_id,
        models.StaffAttendance.date == today,
    ).order_by(models.StaffAttendance.created_at).all()

    def _fmt(dt):
        if not dt:
            return None
        jst = dt
        # actual_start/end はUTC保存なのでJSTに変換
        from datetime import timedelta
        jst = dt + timedelta(hours=9)
        h = jst.hour
        disp_h = h + 24 if h < 12 else h
        return f"{disp_h:02d}:{jst.minute:02d}"

    return [
        {
            "id": r.id,
            "name": r.name,
            "actual_start": r.actual_start.isoformat() if r.actual_start else None,
            "actual_end": r.actual_end.isoformat() if r.actual_end else None,
            "is_late": bool(r.is_late),
            "is_absent": bool(r.is_absent),
        }
        for r in records
    ]


@router.post("/staff-attendance/clock-in")
def staff_clock_in(data: StaffClockInRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """社員/アルバイト出勤打刻"""
    today = date.today()

    if data.is_absent:
        record = models.StaffAttendance(
            store_id=data.store_id,
            date=today,
            name=data.name,
            is_absent=True,
            is_late=False,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {"id": record.id, "message": "当欠で登録しました"}

    start_dt = _hhmm_to_utc(data.actual_start, today) if data.actual_start else datetime.utcnow()
    record = models.StaffAttendance(
        store_id=data.store_id,
        date=today,
        name=data.name,
        actual_start=start_dt,
        is_late=data.is_late,
        is_absent=False,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "message": "出勤しました"}


class StaffClockOutRequest(BaseModel):
    actual_end: Optional[str] = None  # "HH:MM" JST


@router.post("/staff-attendance/{record_id}/clock-out")
def staff_clock_out(record_id: int, data: StaffClockOutRequest = StaffClockOutRequest(), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """社員/アルバイト退勤打刻"""
    record = db.query(models.StaffAttendance).filter(models.StaffAttendance.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="記録が見つかりません")
    if data.actual_end:
        record.actual_end = _hhmm_to_utc(data.actual_end, record.date)
    else:
        record.actual_end = datetime.utcnow()
    db.commit()
    return {"message": "退勤しました"}


@router.patch("/staff-attendance/{record_id}/time")
def update_staff_time(record_id: int, data: StaffTimeUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """社員/アルバイト出退勤時刻修正"""
    record = db.query(models.StaffAttendance).filter(models.StaffAttendance.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="記録が見つかりません")
    if data.actual_start is not None:
        record.actual_start = _hhmm_to_utc(data.actual_start, record.date)
    if data.actual_end is not None:
        record.actual_end = _hhmm_to_utc(data.actual_end, record.date)
    db.commit()
    return {"message": "時刻を更新しました"}


@router.delete("/staff-attendance/{record_id}")
def delete_staff_attendance(record_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """社員/アルバイト勤怠記録を削除"""
    record = db.query(models.StaffAttendance).filter(models.StaffAttendance.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="記録が見つかりません")
    db.delete(record)
    db.commit()
    return {"message": "削除しました"}
