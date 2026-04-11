import os
import time
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import or_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from ..database import get_db
from .. import models
from ..auth import get_current_user
from ..utils.kana import to_halfwidth_katakana

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "uploads", "customers")

router = APIRouter(prefix="/api/customers", tags=["customers"])


def _parse_merged_ids(val) -> list:
    """merged_customer_ids をリストに変換（文字列でも対応）"""
    if not val:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        import json as _json
        try:
            return _json.loads(val)
        except Exception:
            return []
    return []


def _merge_monthly_data(monthly_dicts: list) -> dict:
    """複数のmonthly_dataを月ごとに合算する（excel_importと同じフィールド名）"""
    combined: dict = {}
    for monthly in monthly_dicts:
        if not monthly:
            continue
        for month_key, mdata in monthly.items():
            if month_key not in combined:
                combined[month_key] = {
                    "visits": 0, "spend": 0, "extensions": 0, "persons": 0,
                    "set_l": 0.0, "set_mg": 0.0, "set_shot": 0.0,
                    "in_mins": [],
                    "arrival_source": {},
                    "day_prefs": {},
                }
            c = combined[month_key]
            c["visits"] += mdata.get("visits", 0)
            c["spend"] += mdata.get("spend", 0)
            c["extensions"] += mdata.get("extensions", 0)
            c["persons"] += mdata.get("persons", 0)
            c["set_l"] += mdata.get("set_l", 0)
            c["set_mg"] += mdata.get("set_mg", 0)
            c["set_shot"] += mdata.get("set_shot", 0)
            c["in_mins"].extend(mdata.get("in_mins", []))
            for src, cnt in (mdata.get("arrival_source") or {}).items():
                c["arrival_source"][src] = c["arrival_source"].get(src, 0) + cnt
            for day, cnt in (mdata.get("day_prefs") or {}).items():
                c["day_prefs"][day] = c["day_prefs"].get(day, 0) + cnt
    return combined


def _calc_prefs(monthly_data: dict) -> dict:
    """monthly_dataから集計値を再計算する（excel_importと同一ロジック）"""
    total_visits = sum(m.get("visits", 0) for m in monthly_data.values())
    total_spend = sum(m.get("spend", 0) for m in monthly_data.values())
    total_extensions = sum(m.get("extensions", 0) for m in monthly_data.values())
    total_persons = sum(m.get("persons", 0) for m in monthly_data.values())
    total_set_l = sum(m.get("set_l", 0) for m in monthly_data.values())
    total_set_mg = sum(m.get("set_mg", 0) for m in monthly_data.values())
    total_set_shot = sum(m.get("set_shot", 0) for m in monthly_data.values())
    all_in_mins = [mn for m in monthly_data.values() for mn in m.get("in_mins", [])]

    avg_spend = int(total_spend / total_visits) if total_visits > 0 else 0
    avg_extensions = round(total_extensions / max(total_persons, 1), 2)
    avg_group = round(total_persons / total_visits, 1) if total_visits > 0 else 1
    divisor = total_extensions + 1
    set_l_avg = round(total_set_l / divisor, 2)
    set_mg_avg = round(total_set_mg / divisor, 2)
    set_shot_avg = round(total_set_shot / divisor, 2)

    if all_in_mins:
        avg_min = int(sum(all_in_mins) / len(all_in_mins))
        avg_in_time = (avg_min // 60) * 100 + (avg_min % 60)
    else:
        avg_in_time = None

    monthly_avg_visits = round(total_visits / max(len(monthly_data), 1), 1)

    merged_src: dict = {}
    for m in monthly_data.values():
        for k, cnt in m.get("arrival_source", {}).items():
            merged_src[k] = merged_src.get(k, 0) + cnt

    merged_day: dict = {}
    for m in monthly_data.values():
        for k, cnt in m.get("day_prefs", {}).items():
            merged_day[k] = merged_day.get(k, 0) + cnt

    return {
        "_total_visits": total_visits,
        "_total_spend": total_spend,
        "avg_spend": avg_spend,
        "avg_extensions": avg_extensions,
        "avg_group_size": avg_group,
        "avg_in_time": avg_in_time,
        "monthly_avg_visits": monthly_avg_visits,
        "set_l": set_l_avg,
        "set_mg": set_mg_avg,
        "set_shot": set_shot_avg,
        "day_prefs": merged_day,
        "arrival_source": merged_src,
        "monthly_data": monthly_data,
    }


def _recalculate_customer(db: Session, customer: models.Customer):
    """マージされた全顧客のデータを合算して再計算する"""
    merged_ids = _parse_merged_ids(customer.merged_customer_ids)
    source_ids = merged_ids  # primary以外のマージ元
    sources = db.query(models.Customer).filter(models.Customer.id.in_(source_ids)).all() if source_ids else []

    primary_prefs = customer.preferences or {}
    # primary自身のオリジナルデータ（_own_monthly_dataが保存されていればそちらを使う）
    primary_own_monthly = primary_prefs.get("_own_monthly_data") or primary_prefs.get("monthly_data", {})

    monthly_dicts = [primary_own_monthly] + [(c.preferences or {}).get("monthly_data", {}) for c in sources]
    combined = _merge_monthly_data(monthly_dicts)

    primary_prefs = customer.preferences or {}
    new_prefs = _calc_prefs(combined)
    new_prefs["merged_names"] = [c.name for c in sources if c.id != customer.id]

    for keep_key in ["anniversary_date"]:
        if keep_key in primary_prefs:
            new_prefs[keep_key] = primary_prefs[keep_key]

    first_dates = [c.first_visit_date for c in sources if c.first_visit_date]
    last_dates = [c.last_visit_date for c in sources if c.last_visit_date]

    customer.total_visits = new_prefs["_total_visits"]
    customer.total_spend = new_prefs["_total_spend"]
    customer.first_visit_date = min(first_dates) if first_dates else customer.first_visit_date
    customer.last_visit_date = max(last_dates) if last_dates else customer.last_visit_date
    customer.preferences = new_prefs
    flag_modified(customer, "preferences")


def generate_customer_code(db: Session, store_id: int) -> str:
    """店舗IDに基づいてユニークな顧客コードを生成する（例: L001C00001）"""
    store = db.query(models.Store).filter(models.Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません")
    prefix = store.code  # 例: L001

    existing = db.query(models.Customer.customer_code).filter(
        models.Customer.customer_code.like(f"{prefix}C%"),
    ).all()
    max_num = 0
    for (code,) in existing:
        if code:
            try:
                num = int(code[len(prefix) + 1:])
                max_num = max(max_num, num)
            except ValueError:
                pass
    next_num = max_num + 1
    if next_num > 99999:
        raise HTTPException(status_code=400, detail="顧客IDの上限（99999）に達しました")
    return f"{prefix}C{next_num:05d}"


class CustomerCreate(BaseModel):
    name: str
    alias: Optional[str] = None
    phone: Optional[str] = None
    birthday: Optional[date] = None
    age_group: Optional[str] = None
    features: Optional[str] = None
    preferences: dict = {}


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    alias: Optional[str] = None
    phone: Optional[str] = None
    birthday: Optional[date] = None
    age_group: Optional[str] = None
    features: Optional[str] = None
    preferences: Optional[dict] = None
    is_blacklisted: Optional[bool] = None


class CustomerResponse(BaseModel):
    id: int
    store_id: Optional[int]
    customer_code: Optional[str]
    name: str
    alias: Optional[str]
    phone_masked: Optional[str]  # 下4桁のみ
    birthday: Optional[date]
    first_visit_date: Optional[date]
    last_visit_date: Optional[date]
    total_visits: int
    total_spend: int
    point_balance: int
    ai_summary: Optional[str]
    age_group: Optional[str]
    features: Optional[str]
    photo_url: Optional[str]
    preferences: dict
    is_blacklisted: bool
    merged_names: List[str] = []
    merged_customer_ids: List[int] = []
    merged_into_id: Optional[int] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_masked(cls, customer: models.Customer):
        phone_masked = None
        if customer.phone:
            phone_masked = "****-" + customer.phone[-4:] if len(customer.phone) >= 4 else "****"
        photo_url = f"/uploads/customers/{customer.photo_path}" if customer.photo_path else None
        prefs = customer.preferences or {}
        merged_names = prefs.get("merged_names", [])
        return cls(
            id=customer.id,
            store_id=customer.store_id,
            customer_code=customer.customer_code,
            name=customer.name,
            alias=customer.alias,
            phone_masked=phone_masked,
            birthday=customer.birthday,
            first_visit_date=customer.first_visit_date,
            last_visit_date=customer.last_visit_date,
            total_visits=customer.total_visits,
            total_spend=customer.total_spend,
            point_balance=customer.point_balance,
            ai_summary=customer.ai_summary,
            age_group=customer.age_group,
            features=customer.features,
            photo_url=photo_url,
            preferences=prefs,
            is_blacklisted=customer.is_blacklisted,
            merged_names=merged_names,
            merged_customer_ids=customer.merged_customer_ids or [],
            merged_into_id=customer.merged_into_id,
        )


class NoteCreate(BaseModel):
    note: str
    ticket_id: Optional[int] = None


@router.get("", response_model=list[CustomerResponse])
def get_customers(
    q: Optional[str] = Query(None),
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Customer).filter(models.Customer.is_active == True)
    if store_id:
        query = query.filter(models.Customer.store_id == store_id)
    if q:
        q_half = to_halfwidth_katakana(q)
        query = query.filter(
            or_(
                models.Customer.name.contains(q_half),
                models.Customer.alias.contains(q),
                models.Customer.alias.contains(q_half),
            )
        )
    customers = query.order_by(models.Customer.last_visit_date.desc()).all()
    return [CustomerResponse.from_orm_masked(c) for c in customers]


@router.post("", response_model=CustomerResponse)
def create_customer(
    data: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    store_id = current_user.store_id or 1
    cdata = data.model_dump()
    cdata["name"] = to_halfwidth_katakana(cdata["name"])
    customer = models.Customer(**cdata, store_id=store_id)
    db.add(customer)
    db.flush()
    customer.customer_code = generate_customer_code(db, store_id)
    db.commit()
    db.refresh(customer)
    return CustomerResponse.from_orm_masked(customer)


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="顧客が見つかりません")
    return CustomerResponse.from_orm_masked(customer)


@router.put("/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="顧客が見つかりません")
    for field, value in data.model_dump(exclude_none=True).items():
        if field == "name":
            value = to_halfwidth_katakana(value)
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return CustomerResponse.from_orm_masked(customer)


@router.post("/{customer_id}/notes")
def add_note(
    customer_id: int,
    data: NoteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="顧客が見つかりません")
    note = models.CustomerVisitNote(
        customer_id=customer_id,
        ticket_id=data.ticket_id,
        staff_id=current_user.id,
        note=data.note,
    )
    db.add(note)
    db.commit()
    return {"message": "メモを保存しました", "id": note.id}


@router.get("/{customer_id}/notes")
def get_notes(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    notes = db.query(models.CustomerVisitNote).filter(
        models.CustomerVisitNote.customer_id == customer_id
    ).order_by(models.CustomerVisitNote.created_at.desc()).all()
    return [{"id": n.id, "note": n.note, "ai_summary": n.ai_summary, "created_at": n.created_at} for n in notes]


@router.delete("/{customer_id}/notes/{note_id}")
def delete_note(
    customer_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    note = db.query(models.CustomerVisitNote).filter(
        models.CustomerVisitNote.id == note_id,
        models.CustomerVisitNote.customer_id == customer_id,
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="メモが見つかりません")
    db.delete(note)
    db.commit()
    return {"message": "削除しました"}


class MergeRequest(BaseModel):
    source_id: int


@router.post("/{customer_id}/merge", response_model=CustomerResponse)
def merge_customer(
    customer_id: int,
    data: MergeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """source_id の顧客を customer_id にマージして再計算する"""
    if customer_id == data.source_id:
        raise HTTPException(status_code=400, detail="同じ顧客はマージできません")

    primary = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    source = db.query(models.Customer).filter(models.Customer.id == data.source_id).first()
    if not primary or not source:
        raise HTTPException(status_code=404, detail="顧客が見つかりません")
    if source.merged_into_id:
        raise HTTPException(status_code=400, detail="既に別の顧客にマージ済みです")

    merged_ids = _parse_merged_ids(primary.merged_customer_ids)
    if data.source_id not in merged_ids:
        merged_ids.append(data.source_id)
    primary.merged_customer_ids = merged_ids
    flag_modified(primary, "merged_customer_ids")

    # 初回マージ時にprimary自身のmonthly_dataを保存しておく
    primary_prefs = primary.preferences or {}
    if "_own_monthly_data" not in primary_prefs:
        primary_prefs["_own_monthly_data"] = primary_prefs.get("monthly_data", {})
        primary.preferences = primary_prefs
        flag_modified(primary, "preferences")

    source.merged_into_id = customer_id
    source.is_active = False

    _recalculate_customer(db, primary)
    db.commit()
    db.refresh(primary)
    return CustomerResponse.from_orm_masked(primary)


@router.delete("/{customer_id}/merge/{source_id}", response_model=CustomerResponse)
def unmerge_customer(
    customer_id: int,
    source_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """マージを解除して source_id を独立した顧客に戻す"""
    primary = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    source = db.query(models.Customer).filter(models.Customer.id == source_id).first()
    if not primary or not source:
        raise HTTPException(status_code=404, detail="顧客が見つかりません")

    merged_ids = _parse_merged_ids(primary.merged_customer_ids)
    if source_id in merged_ids:
        merged_ids.remove(source_id)
    primary.merged_customer_ids = merged_ids
    flag_modified(primary, "merged_customer_ids")

    source.merged_into_id = None
    source.is_active = True

    # 全解除時は _own_monthly_data を monthly_data に戻す
    if not merged_ids:
        p_prefs = primary.preferences or {}
        if "_own_monthly_data" in p_prefs:
            p_prefs["monthly_data"] = p_prefs.pop("_own_monthly_data")
            p_prefs.pop("merged_names", None)
            primary.preferences = p_prefs
            flag_modified(primary, "preferences")

    _recalculate_customer(db, primary)
    db.commit()
    db.refresh(primary)
    return CustomerResponse.from_orm_masked(primary)


@router.post("/{customer_id}/photo")
async def upload_customer_photo(
    customer_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="顧客が見つかりません")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise HTTPException(status_code=400, detail="jpg/png/webp/gif のみ対応しています")
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    filename = f"{customer_id}_{int(time.time())}{ext}"
    save_path = os.path.join(UPLOADS_DIR, filename)
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    customer.photo_path = filename
    db.commit()
    return {"photo_url": f"/uploads/customers/{filename}"}


@router.get("/{customer_id}/visits")
def get_customer_visits(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """顧客の来店履歴一覧（マージ済み顧客の履歴も含む）"""
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    all_ids = [customer_id] + (customer.merged_customer_ids or [] if customer else [])
    visits = (
        db.query(models.CustomerVisit)
        .filter(models.CustomerVisit.customer_id.in_(all_ids))
        .order_by(models.CustomerVisit.date.desc())
        .all()
    )
    return [
        {
            "id": v.id,
            "date": v.date.isoformat(),
            "store_name": v.store_name,
            "is_repeat": v.is_repeat,
            "in_time": v.in_time,
            "out_time": v.out_time,
            "total_payment": v.total_payment,
            "raw_data": v.raw_data or {},
        }
        for v in visits
    ]


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="顧客が見つかりません")
    customer.is_active = False
    db.commit()
    return {"message": "顧客を削除しました"}


@router.get("/birthdays/upcoming")
def get_upcoming_birthdays(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """今後N日以内に誕生日の顧客一覧"""
    from datetime import date, timedelta
    today = date.today()
    customers = db.query(models.Customer).filter(
        models.Customer.birthday.isnot(None),
        models.Customer.is_active == True,
    ).all()

    result = []
    for c in customers:
        bday = c.birthday
        # 今年の誕生日
        try:
            this_year_bday = bday.replace(year=today.year)
        except ValueError:
            this_year_bday = bday.replace(year=today.year, day=28)

        if this_year_bday < today:
            try:
                this_year_bday = bday.replace(year=today.year + 1)
            except ValueError:
                this_year_bday = bday.replace(year=today.year + 1, day=28)

        diff = (this_year_bday - today).days
        if 0 <= diff <= days:
            result.append({
                "id": c.id,
                "name": c.name,
                "alias": c.alias,
                "birthday": c.birthday.isoformat(),
                "days_until": diff,
                "birthday_this_year": this_year_bday.isoformat(),
            })

    result.sort(key=lambda x: x["days_until"])
    return result


@router.get("/{customer_id}/cast-stats")
def get_customer_cast_stats(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """顧客×キャスト別の注文集計（S/L/MG/ショット/シャンパン等）"""
    from sqlalchemy import func
    from collections import defaultdict

    # この顧客の全伝票ID
    ticket_ids = [r[0] for r in db.query(models.Ticket.id).filter(
        models.Ticket.customer_id == customer_id,
        models.Ticket.deleted_at.is_(None),
    ).all()]
    if not ticket_ids:
        return []

    # キャスト別×アイテムタイプ別の集計
    rows = db.query(
        models.OrderItem.cast_id,
        models.OrderItem.item_type,
        func.sum(models.OrderItem.quantity),
        func.sum(models.OrderItem.amount),
    ).filter(
        models.OrderItem.ticket_id.in_(ticket_ids),
        models.OrderItem.cast_id.isnot(None),
        models.OrderItem.canceled_at.is_(None),
    ).group_by(
        models.OrderItem.cast_id,
        models.OrderItem.item_type,
    ).all()

    # cast_id → { item_type: { qty, amount } }
    cast_data: dict = defaultdict(lambda: defaultdict(lambda: {"qty": 0, "amount": 0}))
    cast_ids_set = set()
    for cast_id, item_type, qty, amount in rows:
        cast_data[cast_id][item_type]["qty"] += int(qty or 0)
        cast_data[cast_id][item_type]["amount"] += int(amount or 0)
        cast_ids_set.add(cast_id)

    # 来店回数(このキャストがassignmentで付いた回数)
    assign_counts = {}
    if cast_ids_set:
        assign_rows = db.query(
            models.CastAssignment.cast_id,
            func.count(func.distinct(models.CastAssignment.ticket_id)),
        ).filter(
            models.CastAssignment.ticket_id.in_(ticket_ids),
            models.CastAssignment.cast_id.in_(cast_ids_set),
        ).group_by(models.CastAssignment.cast_id).all()
        assign_counts = {r[0]: int(r[1]) for r in assign_rows}

    # キャスト名取得
    cast_names = {}
    if cast_ids_set:
        for c in db.query(models.Cast).filter(models.Cast.id.in_(cast_ids_set)).all():
            cast_names[c.id] = c.stage_name

    result = []
    for cid in sorted(cast_ids_set):
        d = cast_data[cid]
        result.append({
            "cast_id": cid,
            "cast_name": cast_names.get(cid, f"ID{cid}"),
            "assign_count": assign_counts.get(cid, 0),
            "drink_s": d.get("drink_s", {}).get("qty", 0),
            "drink_l": d.get("drink_l", {}).get("qty", 0),
            "drink_mg": d.get("drink_mg", {}).get("qty", 0),
            "shot_cast": d.get("shot_cast", {}).get("qty", 0),
            "champagne_count": d.get("champagne", {}).get("qty", 0),
            "champagne_amount": d.get("champagne", {}).get("amount", 0),
            "total_amount": sum(v["amount"] for v in d.values()),
        })

    # 合計金額順に並べ替え
    result.sort(key=lambda x: -x["total_amount"])
    return result


@router.post("/normalize-names")
def normalize_customer_names(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """既存顧客名をすべて半角カタカナに正規化する（1回実行用）"""
    customers = db.query(models.Customer).all()
    count = 0
    for c in customers:
        new_name = to_halfwidth_katakana(c.name)
        if new_name != c.name:
            c.name = new_name
            count += 1
    db.commit()
    return {"message": f"{count}件の顧客名を正規化しました"}
