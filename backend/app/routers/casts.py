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

MANAGER_ROLES = {models.UserRole.administrator, models.UserRole.superadmin, models.UserRole.manager, models.UserRole.editor}


def _bar_hhmm_to_utc(hhmm: str, base_date: date) -> datetime:
    """バー営業表記 HH:MM (JST, 0-35時) を UTC datetime に変換。
    - 12-23時: 同日扱い
    - 24-35時: 翌日扱い（hour は -24 して 0-11 に正規化）
    - 0-11時: 翌日AM扱い（営業跨ぎ）
    """
    from datetime import timedelta
    h, m = int(hhmm.split(':')[0]), int(hhmm.split(':')[1])
    if h >= 24:
        h -= 24
        d = base_date + timedelta(days=1)
    elif h < 12:
        d = base_date + timedelta(days=1)
    else:
        d = base_date
    return datetime(d.year, d.month, d.day, h, m) - timedelta(hours=9)


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
    is_retired: bool = False
    retired_at: Optional[date] = None
    taiken_status: Optional[str] = None
    help_from_store_name: Optional[str] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_cast(cls, cast: models.Cast, store_name_map: dict = None):
        photo_url = f"/uploads/casts/{cast.photo_path}" if cast.photo_path else None
        # ヘルプキャストの所属店舗名を解決
        help_store_name = None
        if cast.stage_name and cast.stage_name.startswith("[ヘルプ]") and cast.notes:
            import re
            m = re.search(r"from store (\d+)", cast.notes)
            if m and store_name_map:
                help_store_name = store_name_map.get(int(m.group(1)))
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
            is_retired=bool(getattr(cast, 'is_retired', False)),
            retired_at=getattr(cast, 'retired_at', None),
            help_from_store_name=help_store_name,
        )


@router.get("/{store_id}", response_model=list[CastResponse])
def get_casts(
    store_id: int,
    include_retired: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.Cast).filter(models.Cast.store_id == store_id, models.Cast.is_active == True)
    if not include_retired:
        q = q.filter(models.Cast.is_retired == False)
    casts = q.all()
    # ヘルプキャストの所属店舗名解決用マップ
    store_map = {s.id: s.name for s in db.query(models.Store).all()}
    return [CastResponse.from_orm_cast(c, store_map) for c in casts]


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
    cast_data = data.model_dump()
    cast_data['help_hourly_rate'] = cast_data['hourly_rate'] + 100
    cast = models.Cast(store_id=store_id, cast_code=cast_code, **cast_data)
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

    # ヘルプ時給は常に基本時給+100に強制（直接更新は無視）
    update_data.pop('help_hourly_rate', None)
    if "hourly_rate" in update_data:
        update_data['help_hourly_rate'] = update_data['hourly_rate'] + 100

    for field, value in update_data.items():
        setattr(cast, field, value)
    db.commit()
    db.refresh(cast)
    return CastResponse.from_orm_cast(cast)


class StaffDeleteRequest(BaseModel):
    operator_name: Optional[str] = None
    reason: Optional[str] = None


@router.post("/staff-attendance/{record_id}/remove")
def delete_staff_attendance_post(record_id: int, data: StaffDeleteRequest = StaffDeleteRequest(), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """社員/アルバイト勤怠記録を削除（担当者・理由付き）"""
    record = db.query(models.StaffAttendance).filter(models.StaffAttendance.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="記録が見つかりません")
    log = models.OrderItemLog(
        store_id=record.store_id, action='staff_delete',
        item_name=f"社員勤怠削除: {record.name}",
        operator_name=data.operator_name, reason=data.reason,
        changed_by=current_user.id,
    )
    db.add(log)
    db.delete(record)
    db.commit()
    return {"message": "削除しました"}


@router.delete("/staff-attendance/{record_id}")
def delete_staff_attendance(record_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """社員/アルバイト勤怠記録を削除（後方互換）"""
    record = db.query(models.StaffAttendance).filter(models.StaffAttendance.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="記録が見つかりません")
    db.delete(record)
    db.commit()
    return {"message": "削除しました"}


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


@router.post("/{store_id}/{cast_id}/reinstate")
def reinstate_cast(
    store_id: int,
    cast_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """退店キャストを在籍に戻す"""
    cast = db.query(models.Cast).filter(
        models.Cast.id == cast_id,
        models.Cast.store_id == store_id,
    ).first()
    if not cast:
        raise HTTPException(status_code=404, detail="キャストが見つかりません")
    cast.is_retired = False
    cast.retired_at = None
    db.commit()
    return {"message": "在籍に戻しました"}


@router.post("/{store_id}/{cast_id}/retire")
def retire_cast(
    store_id: int,
    cast_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """キャストを退店にする"""
    from datetime import date as date_type
    cast = db.query(models.Cast).filter(
        models.Cast.id == cast_id,
        models.Cast.store_id == store_id,
    ).first()
    if not cast:
        raise HTTPException(status_code=404, detail="キャストが見つかりません")
    cast.is_retired = True
    cast.retired_at = date_type.today()
    db.commit()
    return {"message": "退店しました"}


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

    # 自店のシフト
    own_shifts = db.query(models.ConfirmedShift).filter(
        models.ConfirmedShift.cast_id == cast_id,
        models.ConfirmedShift.store_id == store_id,
    ).all()

    # ヘルプ先（他店）のシフトも集約: このキャストの名前で他店にヘルプ出勤した記録
    help_shifts = []
    if cast.stage_name and not cast.stage_name.startswith("[ヘルプ]"):
        help_shifts = db.query(models.ConfirmedShift).filter(
            models.ConfirmedShift.help_from_store_id == store_id,
            models.ConfirmedShift.help_cast_name == cast.stage_name,
            models.ConfirmedShift.store_id != store_id,
        ).all()

    shifts = own_shifts + help_shifts

    total_minutes = 0.0
    weekday_minutes: dict[int, list[float]] = defaultdict(list)
    monthly_counts: dict[str, int] = defaultdict(int)
    # 当欠率・遅刻率・日払い率用：月ごとに集計
    monthly_total_rows: dict[str, int] = defaultdict(int)
    monthly_absent_rows: dict[str, int] = defaultdict(int)
    monthly_late_rows: dict[str, int] = defaultdict(int)
    monthly_daily_pay_rows: dict[str, int] = defaultdict(int)

    # shift_data + POSオーダーから集計
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

    # POSオーダー（OrderItem）からドリンク実績を集計
    # このキャストに紐づく全オーダー（自店 + ヘルプ先の[ヘルプ]キャスト分）
    pos_cast_ids = [cast_id]
    if not cast.stage_name.startswith("[ヘルプ]"):
        # ヘルプ先で作られた[ヘルプ]cast_idも集約
        help_cast_ids = [
            c.id for c in db.query(models.Cast.id).filter(
                models.Cast.stage_name == f"[ヘルプ]{cast.stage_name}",
                models.Cast.is_active == True,
            ).all()
        ]
        pos_cast_ids.extend(help_cast_ids)

    from sqlalchemy import func as sqlfunc
    pos_items = db.query(
        models.OrderItem.item_type,
        sqlfunc.sum(models.OrderItem.quantity),
        sqlfunc.sum(models.OrderItem.amount),
    ).filter(
        models.OrderItem.cast_id.in_(pos_cast_ids),
        models.OrderItem.canceled_at.is_(None),
    ).group_by(models.OrderItem.item_type).all()

    for item_type, qty, amt in pos_items:
        qty = int(qty or 0)
        amt = int(amt or 0)
        if item_type == 'drink_s':
            total_set_l += qty  # SもL数として合算（1セットあたりの指標）
        elif item_type == 'drink_l':
            total_set_l += qty
        elif item_type == 'drink_mg':
            total_set_mg += qty
        elif item_type == 'shot_cast':
            total_set_shot += qty
        elif item_type == 'champagne':
            total_champagne_back += amt
        total_drink_count += qty

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


@router.get("/{store_id}/{cast_id}/shifts/{shift_id}/detail")
def get_cast_shift_detail(
    store_id: int,
    cast_id: int,
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """出勤履歴1件の詳細: 日報スナップショットの cast_block と担当伝票一覧"""
    shift = db.query(models.ConfirmedShift).filter(
        models.ConfirmedShift.id == shift_id,
        models.ConfirmedShift.cast_id == cast_id,
        models.ConfirmedShift.store_id == store_id,
    ).first()
    if not shift:
        raise HTTPException(status_code=404, detail="シフトが見つかりません")

    # スナップショット（最新バージョン）
    snap = db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.store_id == store_id,
        models.DailyReportSnapshot.business_date == shift.date,
    ).order_by(models.DailyReportSnapshot.version.desc()).first()

    cast_block = None
    if snap and snap.payload:
        for b in snap.payload.get("cast_attendance", []):
            if b.get("cast_id") == cast_id:
                cast_block = b
                break

    # その日の担当伝票（CastAssignment 経由）
    from datetime import timedelta
    day_start_utc = datetime(shift.date.year, shift.date.month, shift.date.day, 3, 0, 0) - timedelta(hours=9)
    day_end_utc = day_start_utc + timedelta(hours=24)

    # その日の全伝票（OrderItem 集計用・CastAssignment とは別に、シャンパン分配もカバー）
    day_tickets = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.deleted_at.is_(None),
        models.Ticket.started_at >= day_start_utc,
        models.Ticket.started_at < day_end_utc,
    ).all()

    # 対応した伝票（CastAssignment のある伝票）
    assigned_tids = set(r[0] for r in db.query(models.CastAssignment.ticket_id).filter(
        models.CastAssignment.cast_id == cast_id,
        models.CastAssignment.started_at >= day_start_utc,
        models.CastAssignment.started_at < day_end_utc,
    ).distinct().all())

    tickets_out = []
    for t in day_tickets:
        if t.id not in assigned_tids:
            continue
        adj = sum(
            (i.amount or 0) for i in (t.order_items or [])
            if i.item_name and (
                i.item_name.startswith('先会計') or
                i.item_name.startswith('分割清算') or
                i.item_name.startswith('値引き') or
                i.item_name.startswith('加算')
            ) and not i.canceled_at
        )
        sub = (t.total_amount or 0) - adj
        grand = round(sub * 1.21) + adj
        # この伝票内のこのキャストのドリンク/シャンパン内訳
        t_s = t_l = t_mg = t_shot = 0
        t_champ = 0
        t_champ_amount = 0  # このキャストに按分されたシャンパン売上
        for o in (t.order_items or []):
            if o.canceled_at:
                continue
            if o.cast_id == cast_id:
                if o.item_type == "drink_s": t_s += (o.quantity or 0)
                elif o.item_type == "drink_l": t_l += (o.quantity or 0)
                elif o.item_type == "drink_mg": t_mg += (o.quantity or 0)
                elif o.item_type == "shot_cast": t_shot += (o.quantity or 0)
            if o.item_type == "champagne":
                dist = o.cast_distribution or []
                if not dist:
                    if o.cast_id == cast_id:
                        t_champ += (o.quantity or 0)
                        t_champ_amount += (o.incentive_amount or 0)
                else:
                    if (o.amount or 0) > 0:
                        for e in dist:
                            if e.get("cast_id") == cast_id:
                                t_champ += 1
                                t_champ_amount += int((o.incentive_amount or 0) * e.get("ratio", 0) / 100)
                                break
        tickets_out.append({
            "ticket_id": t.id,
            "table_no": t.table_no,
            "customer_name": t.customer.name if t.customer else None,
            "grand_total": max(0, grand),
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "ended_at": t.ended_at.isoformat() if t.ended_at else None,
            "drink_s": t_s,
            "drink_l": t_l,
            "drink_mg": t_mg,
            "shot_cast": t_shot,
            "champagne": t_champ,
            "champagne_amount": t_champ_amount,
        })
    tickets_out.sort(key=lambda x: x.get("started_at") or "")

    # ドリンク件数 & シャンパン集計を DB から直接算出（スナップショット非依存）
    drink_counts = {"drink_s": 0, "drink_l": 0, "drink_mg": 0, "shot_cast": 0}
    champagne_count = 0      # 本数
    champagne_sales = 0      # 売上(非按分)
    champagne_incentive = 0  # 按分後インセンティブ額
    for t in day_tickets:
        for o in (t.order_items or []):
            if o.canceled_at:
                continue
            # 非シャンパンドリンク: cast_id 完全一致で集計
            if o.cast_id == cast_id and o.item_type in drink_counts:
                drink_counts[o.item_type] += (o.quantity or 0)
            # シャンパン: cast_distribution の按分
            if o.item_type == "champagne":
                dist = o.cast_distribution or []
                # ratio 付きマーカー(0円)も含めて1本のシャンパン単位で集計するため
                # dist を持つ「本体」行のみ採用
                if not dist:
                    # cast_id 完全一致(キャスト指定なし×キャスト選択シャンパン)
                    if o.cast_id == cast_id:
                        champagne_count += (o.quantity or 0)
                        champagne_sales += (o.amount or 0)
                        champagne_incentive += (o.incentive_amount or 0)
                    continue
                for entry in dist:
                    if entry.get("cast_id") == cast_id:
                        ratio = entry.get("ratio", 0)
                        # dist は同グループの全注文に同じJSONが入るため、amount>0 の行だけ集計
                        if (o.amount or 0) > 0:
                            champagne_count += 1
                            champagne_sales += int((o.amount or 0) * ratio / 100)
                            champagne_incentive += int((o.incentive_amount or 0) * ratio / 100)
                        break

    return {
        "cast_block": cast_block,
        "tickets": tickets_out,
        "drink_counts": drink_counts,
        "champagne_count": champagne_count,
        "champagne_sales": champagne_sales,
        "champagne_incentive": champagne_incentive,
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

    # 日報スナップショットから cast_id × date での cast_block を事前取得
    # （営業締めで actual_start/end がクリアされたシフトの実勤務時間復元用）
    dates = list({s.date for s in shifts})
    snapshot_blocks: dict = {}  # (cast_id, date) -> cast_block
    if dates:
        snaps = db.query(models.DailyReportSnapshot).filter(
            models.DailyReportSnapshot.store_id == store_id,
            models.DailyReportSnapshot.business_date.in_(dates),
        ).all()
        # 各日付で最新バージョンのみ採用
        best_by_date: dict = {}
        for sn in snaps:
            cur = best_by_date.get(sn.business_date)
            if cur is None or (sn.version or 0) > (cur.version or 0):
                best_by_date[sn.business_date] = sn
        for d, sn in best_by_date.items():
            payload = sn.payload or {}
            for b in payload.get("cast_attendance", []):
                cid = b.get("cast_id")
                if cid is None:
                    continue
                key = (int(cid), d)
                if key not in snapshot_blocks:
                    snapshot_blocks[key] = b

    result = []
    def _jst_iso_to_utc_iso(iso_str):
        """JST naive ISO ('2026-04-13T21:00:00') を UTC ISO (+'Z') に変換"""
        if not iso_str:
            return None
        try:
            from datetime import timedelta as _td
            # 'Z' や '+' が既に付いている場合はそのまま返す
            if iso_str.endswith('Z') or '+' in iso_str:
                return iso_str
            dt = datetime.fromisoformat(iso_str.split('.')[0]) - _td(hours=9)
            return dt.isoformat() + 'Z'
        except Exception:
            return iso_str

    for s in shifts:
        snap = snapshot_blocks.get((cast_id, s.date)) if cast_id else None
        actual_start_iso = s.actual_start.isoformat() if s.actual_start else None
        actual_end_iso = s.actual_end.isoformat() if s.actual_end else None
        if actual_start_iso is None and snap:
            actual_start_iso = _jst_iso_to_utc_iso(snap.get("actual_start"))
        if actual_end_iso is None and snap:
            actual_end_iso = _jst_iso_to_utc_iso(snap.get("actual_end"))
        actual_hours = None
        if s.actual_start and s.actual_end:
            actual_hours = round((s.actual_end - s.actual_start).total_seconds() / 3600, 1)
        elif snap and snap.get("work_hours") is not None:
            actual_hours = round(float(snap.get("work_hours") or 0), 1)
        pay = s.daily_pay
        total_pay = pay.total_pay if pay else None
        drink_back = pay.drink_back if pay else None
        champagne_back = pay.champagne_back if pay else None
        honshimei_back = pay.honshimei_back if pay else None
        # daily_pay が無い場合は snapshot から補完
        if total_pay is None and snap:
            base = int(snap.get("base_pay") or 0)
            incentive = int(snap.get("incentive_total") or 0)
            daily_pay_amt = int(snap.get("daily_pay") or 0)
            total_pay = base + incentive - daily_pay_amt
            drink_back = drink_back if drink_back is not None else 0
            champagne_back = champagne_back if champagne_back is not None else int(snap.get("champagne_amount") or 0)
        result.append({
            "id": s.id,
            "date": s.date.isoformat(),
            "planned_start": s.planned_start,
            "planned_end": s.planned_end,
            "actual_start": actual_start_iso,
            "actual_end": actual_end_iso,
            "actual_hours": actual_hours,
            "is_late": bool(s.is_late) or (snap.get("is_late") if snap else False),
            "is_absent": bool(s.is_absent) or (snap.get("is_absent") if snap else False),
            "total_pay": total_pay,
            "drink_back": drink_back,
            "champagne_back": champagne_back,
            "honshimei_back": honshimei_back,
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
    operator_name: Optional[str] = None
    reason: Optional[str] = None


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
    # キャスト別の最終アクティビティ終了時刻（待機中の「何分待機」計算用）
    cast_ids = [s.cast_id for s in shifts if s.cast_id is not None]
    last_activity_end: dict = {}
    if cast_ids:
        for cid in cast_ids:
            # CastAssignment の最終 ended_at
            last_assign = db.query(models.CastAssignment.ended_at).filter(
                models.CastAssignment.cast_id == cid,
                models.CastAssignment.ended_at.isnot(None),
            ).order_by(models.CastAssignment.ended_at.desc()).first()
            # TissueDistribution の最終 ended_at
            last_tissue = db.query(models.TissueDistribution.ended_at).filter(
                models.TissueDistribution.cast_id == cid,
                models.TissueDistribution.ended_at.isnot(None),
            ).order_by(models.TissueDistribution.ended_at.desc()).first()
            candidates = [x[0] for x in (last_assign, last_tissue) if x and x[0]]
            if candidates:
                last_activity_end[cid] = max(candidates)

    result = []
    for s in shifts:
        if s.cast_id is not None:
            cast_name = s.cast.stage_name if s.cast else f"Cast{s.cast_id}"
        elif s.help_cast_name:
            cast_name = f"[ヘルプ]{s.help_cast_name}"
        else:
            cast_name = "不明"
        # 待機開始時刻: 最終アクティビティ終了時刻 > actual_start の方を採用
        idle_since = s.actual_start
        if s.cast_id and s.cast_id in last_activity_end:
            ae = last_activity_end[s.cast_id]
            if s.actual_start is None or ae > s.actual_start:
                idle_since = ae
        result.append({
            "shift_id": s.id,
            "cast_id": s.cast_id,
            "cast_name": cast_name,
            "actual_start": s.actual_start.isoformat() if s.actual_start else None,
            "actual_end": s.actual_end.isoformat() if s.actual_end else None,
            "idle_since": idle_since.isoformat() if idle_since else None,
            "is_late": bool(s.is_late),
            "is_absent": bool(s.is_absent),
            "taiken_status": s.cast.taiken_status if s.cast else None,
            "help_cast_name": s.help_cast_name,
        })
    return result


class HelpClockInRequest(BaseModel):
    store_id: int
    help_from_store_id: int
    help_cast_name: str
    actual_start: Optional[str] = None  # "HH:MM" JST


@router.post("/attendance/help-clock-in")
def help_clock_in(data: HelpClockInRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """ヘルプ出勤打刻: Castレコードを作成(または再利用)して紐付け"""
    from datetime import timedelta
    today = date.today()

    now = _bar_hhmm_to_utc(data.actual_start, today) if data.actual_start else datetime.utcnow()

    # ヘルプキャスト用のCastレコードを検索or作成
    help_name = f"[ヘルプ]{data.help_cast_name}"
    cast = db.query(models.Cast).filter(
        models.Cast.store_id == data.store_id,
        models.Cast.stage_name == help_name,
    ).first()
    if not cast:
        cast = models.Cast(
            store_id=data.store_id,
            stage_name=help_name,
            real_name=data.help_cast_name,
            rank="C",
            hourly_rate=1400,
            help_hourly_rate=1500,
            is_active=True,
            notes=f"ヘルプ体入 from store {data.help_from_store_id}",
        )
        db.add(cast)
        db.flush()

    shift = models.ConfirmedShift(
        cast_id=cast.id,
        store_id=data.store_id,
        date=today,
        help_from_store_id=data.help_from_store_id,
        help_cast_name=data.help_cast_name,
        actual_start=now,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return {"shift_id": shift.id, "cast_id": cast.id, "message": "ヘルプ出勤しました"}


class TaikenClockInRequest(BaseModel):
    store_id: int
    cast_name: str
    actual_start: Optional[str] = None  # "HH:MM" JST
    hourly_rate: Optional[int] = 1400


@router.post("/attendance/taiken-clock-in")
def taiken_clock_in(data: TaikenClockInRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """体験入店打刻: Castレコード「[体入]名前」を作成 or 再利用して紐付け"""
    today = date.today()
    now = _bar_hhmm_to_utc(data.actual_start, today) if data.actual_start else datetime.utcnow()

    taiken_name = f"[体入]{data.cast_name}"
    cast = db.query(models.Cast).filter(
        models.Cast.store_id == data.store_id,
        models.Cast.stage_name == taiken_name,
    ).first()
    if not cast:
        rate = data.hourly_rate or 1400
        cast = models.Cast(
            store_id=data.store_id,
            stage_name=taiken_name,
            real_name=data.cast_name,
            rank="C",
            hourly_rate=rate,
            help_hourly_rate=rate + 100,
            is_active=True,
            taiken_status="taiken",
            notes="体験入店",
        )
        db.add(cast)
        db.flush()

    shift = models.ConfirmedShift(
        cast_id=cast.id,
        store_id=data.store_id,
        date=today,
        help_cast_name=data.cast_name,
        actual_start=now,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return {"shift_id": shift.id, "cast_id": cast.id, "message": "体験入店しました"}


class TaikenStatusRequest(BaseModel):
    status: str  # honnyuu / fusaiyou / sai_taiken


@router.post("/{cast_id}/taiken-status")
def update_taiken_status(
    cast_id: int,
    data: TaikenStatusRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """体入キャストのステータスを更新"""
    cast = db.query(models.Cast).filter(models.Cast.id == cast_id).first()
    if not cast:
        raise HTTPException(status_code=404, detail="キャストが見つかりません")

    if data.status == "honnyuu":
        # 本入: [体入] プレフィックスを外して正規キャストに
        if cast.stage_name.startswith("[体入]"):
            cast.stage_name = cast.stage_name.replace("[体入]", "")
        cast.taiken_status = "honnyuu"
        cast.is_active = True
        cast.notes = (cast.notes or "") + f"\n本入店 {date.today()}"
    elif data.status == "fusaiyou":
        cast.taiken_status = "fusaiyou"
        cast.is_active = False
    elif data.status == "sai_taiken":
        cast.taiken_status = "sai_taiken"
        cast.is_active = True

    db.commit()
    return {"message": f"ステータスを{data.status}に更新しました", "cast_id": cast.id, "stage_name": cast.stage_name}


@router.post("/attendance/clock-in")
def clock_in(data: ClockInRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """出勤打刻: 本日のシフトに actual_start をセット。シフトがなければ当日分を新規作成"""
    today = date.today()
    from datetime import timedelta

    now = _bar_hhmm_to_utc(data.actual_start, today) if data.actual_start else datetime.utcnow()

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

    # 本日のシフトを探す（退勤済みシフトは上書きしない）
    if data.is_absent:
        # 当欠: actual_start なし、is_absent=True
        shift = db.query(models.ConfirmedShift).filter(
            models.ConfirmedShift.cast_id == data.cast_id,
            models.ConfirmedShift.store_id == data.store_id,
            models.ConfirmedShift.date == today,
            models.ConfirmedShift.actual_start.is_(None),
        ).first()
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

    # 未打刻シフト（予定のみ or 欠勤）があれば流用、なければ新規行
    empty_shift = db.query(models.ConfirmedShift).filter(
        models.ConfirmedShift.cast_id == data.cast_id,
        models.ConfirmedShift.store_id == data.store_id,
        models.ConfirmedShift.date == today,
        models.ConfirmedShift.actual_start.is_(None),
    ).first()
    if empty_shift:
        empty_shift.actual_start = now
        empty_shift.actual_end = None
        empty_shift.is_late = data.is_late
        empty_shift.is_absent = False
        shift = empty_shift
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
    actual_end: Optional[str] = None
    operator_name: Optional[str] = None
    reason: Optional[str] = None


@router.post("/attendance/{shift_id}/clock-out")
def clock_out(shift_id: int, data: ClockOutRequest = ClockOutRequest(), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """退勤打刻"""
    from datetime import timedelta
    shift = db.query(models.ConfirmedShift).filter(models.ConfirmedShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="シフトが見つかりません")
    cast_name = shift.help_cast_name or (db.query(models.Cast.stage_name).filter(models.Cast.id == shift.cast_id).scalar() if shift.cast_id else "不明")
    if data.actual_end:
        shift.actual_end = _bar_hhmm_to_utc(data.actual_end, shift.date)
    else:
        shift.actual_end = datetime.utcnow()
    # 退勤と同時に対応中（未終了のCastAssignment）を全て終了
    if shift.cast_id:
        active_assigns = db.query(models.CastAssignment).filter(
            models.CastAssignment.cast_id == shift.cast_id,
            models.CastAssignment.ended_at.is_(None),
        ).all()
        for a in active_assigns:
            a.ended_at = shift.actual_end
        # 退勤と同時にティッシュ配り中（未終了）も終了
        from .tissue import end_active_tissue_for_cast
        end_active_tissue_for_cast(db, shift.cast_id)
    log = models.OrderItemLog(
        store_id=shift.store_id, action='attendance_clock_out',
        item_name=f"退勤: {cast_name} {data.actual_end or '現在時刻'}",
        operator_name=data.operator_name, reason=data.reason,
        changed_by=current_user.id,
    )
    db.add(log)
    db.flush()
    # 同日・同キャスト・同店舗の退勤済みシフトで重なり/隣接するものをマージ
    _merge_overlapping_shifts(db, shift.cast_id, shift.store_id, shift.date)
    db.commit()
    return {"message": "退勤しました"}


def _merge_overlapping_shifts(db: Session, cast_id: Optional[int], store_id: int, target_date: date):
    """同日・同キャスト・同店舗の退勤済みシフトを重なり/隣接判定でマージする。
    - min(actual_start), max(actual_end) で統合
    - 統合対象の他シフトは削除"""
    if cast_id is None:
        return
    shifts = db.query(models.ConfirmedShift).filter(
        models.ConfirmedShift.cast_id == cast_id,
        models.ConfirmedShift.store_id == store_id,
        models.ConfirmedShift.date == target_date,
        models.ConfirmedShift.actual_start.isnot(None),
        models.ConfirmedShift.actual_end.isnot(None),
        models.ConfirmedShift.is_absent == False,
    ).order_by(models.ConfirmedShift.actual_start.asc()).all()
    if len(shifts) < 2:
        return
    current = shifts[0]
    for s in shifts[1:]:
        # 重なりまたは隣接（s.start <= current.end）ならマージ
        if s.actual_start <= current.actual_end:
            if s.actual_start < current.actual_start:
                current.actual_start = s.actual_start
                if s.is_late and not current.is_late:
                    current.is_late = True
            if s.actual_end > current.actual_end:
                current.actual_end = s.actual_end
            db.delete(s)
        else:
            current = s


@router.patch("/attendance/{shift_id}/time")
def update_attendance_time(shift_id: int, data: AttendanceTimeUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """出退勤時刻を修正（HH:MM JST で受け取り UTC に変換して保存）"""
    shift = db.query(models.ConfirmedShift).filter(models.ConfirmedShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="シフトが見つかりません")

    hhmm_jst_to_utc = _bar_hhmm_to_utc

    changes = []
    cast_name = shift.help_cast_name or (db.query(models.Cast.stage_name).filter(models.Cast.id == shift.cast_id).scalar() if shift.cast_id else "不明")
    if data.actual_start:
        shift.actual_start = hhmm_jst_to_utc(data.actual_start, shift.date)
        changes.append(f"出勤→{data.actual_start}")
    if data.actual_end:
        shift.actual_end = hhmm_jst_to_utc(data.actual_end, shift.date)
        changes.append(f"退勤→{data.actual_end}")
    log = models.OrderItemLog(
        store_id=shift.store_id, action='attendance_time_update',
        item_name=f"時間修正: {cast_name} {' '.join(changes)}",
        operator_name=data.operator_name, reason=data.reason,
        changed_by=current_user.id,
    )
    db.add(log)
    db.commit()
    return {"message": "時刻を更新しました"}


class AttendanceRemoveRequest(BaseModel):
    operator_name: Optional[str] = None
    reason: Optional[str] = None


@router.post("/attendance/{shift_id}/remove")
def delete_attendance(shift_id: int, data: AttendanceRemoveRequest = AttendanceRemoveRequest(), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """出勤記録を削除（actual_start/actual_end をクリア）"""
    shift = db.query(models.ConfirmedShift).filter(models.ConfirmedShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="シフトが見つかりません")
    cast_name = shift.help_cast_name or (db.query(models.Cast.stage_name).filter(models.Cast.id == shift.cast_id).scalar() if shift.cast_id else "不明")
    log = models.OrderItemLog(
        store_id=shift.store_id, action='attendance_delete',
        item_name=f"勤怠削除: {cast_name}",
        operator_name=data.operator_name, reason=data.reason,
        changed_by=current_user.id,
    )
    db.add(log)
    if shift.cast_id is None:
        db.delete(shift)
    else:
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
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    operator_name: Optional[str] = None
    reason: Optional[str] = None


_hhmm_to_utc = _bar_hhmm_to_utc


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
    actual_end: Optional[str] = None
    operator_name: Optional[str] = None
    reason: Optional[str] = None


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
    log = models.OrderItemLog(
        store_id=record.store_id, action='staff_clock_out',
        item_name=f"社員退勤: {record.name} {data.actual_end or '現在時刻'}",
        operator_name=data.operator_name, reason=data.reason,
        changed_by=current_user.id,
    )
    db.add(log)
    db.commit()
    return {"message": "退勤しました"}


@router.patch("/staff-attendance/{record_id}/time")
def update_staff_time(record_id: int, data: StaffTimeUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """社員/アルバイト出退勤時刻修正"""
    record = db.query(models.StaffAttendance).filter(models.StaffAttendance.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="記録が見つかりません")
    changes = []
    if data.actual_start is not None:
        record.actual_start = _hhmm_to_utc(data.actual_start, record.date)
        changes.append(f"出勤→{data.actual_start}")
    if data.actual_end is not None:
        record.actual_end = _hhmm_to_utc(data.actual_end, record.date)
        changes.append(f"退勤→{data.actual_end}")
    log = models.OrderItemLog(
        store_id=record.store_id, action='staff_time_update',
        item_name=f"社員時間修正: {record.name} {' '.join(changes)}",
        operator_name=data.operator_name, reason=data.reason,
        changed_by=current_user.id,
    )
    db.add(log)
    db.commit()
    return {"message": "時刻を更新しました"}
