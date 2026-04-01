import os
import time
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel
from typing import Optional
from datetime import date
from ..database import get_db
from .. import models
from ..auth import get_current_user

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "uploads", "customers")

router = APIRouter(prefix="/api/customers", tags=["customers"])


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

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_masked(cls, customer: models.Customer):
        phone_masked = None
        if customer.phone:
            phone_masked = "****-" + customer.phone[-4:] if len(customer.phone) >= 4 else "****"
        photo_url = f"/uploads/customers/{customer.photo_path}" if customer.photo_path else None
        return cls(
            id=customer.id,
            store_id=customer.store_id,
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
            preferences=customer.preferences or {},
            is_blacklisted=customer.is_blacklisted,
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
        query = query.filter(
            or_(
                models.Customer.name.contains(q),
                models.Customer.alias.contains(q),
            )
        )
    customers = query.order_by(models.Customer.last_visit_date.desc()).limit(100).all()
    return [CustomerResponse.from_orm_masked(c) for c in customers]


@router.post("", response_model=CustomerResponse)
def create_customer(
    data: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = models.Customer(**data.model_dump())
    db.add(customer)
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
    """顧客の来店履歴一覧（Excelインポート分）"""
    visits = (
        db.query(models.CustomerVisit)
        .filter(models.CustomerVisit.customer_id == customer_id)
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
