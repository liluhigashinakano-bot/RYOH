from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..database import get_db
from .. import models
from ..auth import get_current_user

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


class TicketCreate(BaseModel):
    store_id: int
    customer_id: Optional[int] = None
    table_no: Optional[str] = None
    notes: Optional[str] = None
    guest_count: int = 1
    plan_type: Optional[str] = None
    visit_type: Optional[str] = None


class OrderItemCreate(BaseModel):
    item_type: str
    item_name: Optional[str] = None
    quantity: int = 1
    unit_price: int
    cast_id: Optional[int] = None


class TicketClose(BaseModel):
    payment_method: models.PaymentMethod
    cash_amount: int = 0
    card_amount: int = 0
    discount_amount: int = 0


class OrderItemResponse(BaseModel):
    id: int
    item_type: str
    item_name: Optional[str]
    quantity: int
    unit_price: int
    amount: int
    cast_id: Optional[int]
    canceled_at: Optional[datetime]

    class Config:
        from_attributes = True


class TicketResponse(BaseModel):
    id: int
    store_id: int
    customer_id: Optional[int]
    table_no: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    is_closed: bool
    set_count: int
    extension_count: int
    total_amount: int
    discount_amount: int
    notes: Optional[str]
    guest_count: int = 1
    plan_type: Optional[str] = None
    visit_type: Optional[str] = None

    class Config:
        from_attributes = True


class TicketDetailResponse(TicketResponse):
    order_items: list[OrderItemResponse] = []


@router.get("/{ticket_id}", response_model=TicketDetailResponse)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")
    result = TicketDetailResponse.model_validate(ticket)
    result.order_items = [OrderItemResponse.model_validate(i) for i in ticket.order_items if i.canceled_at is None]
    return result


@router.get("")
def get_tickets(
    store_id: int,
    is_closed: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Ticket).filter(models.Ticket.store_id == store_id)
    if is_closed is not None:
        query = query.filter(models.Ticket.is_closed == is_closed)
    return query.order_by(models.Ticket.started_at.desc()).all()


@router.post("", response_model=TicketResponse)
def create_ticket(
    data: TicketCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    store = db.query(models.Store).filter(models.Store.id == data.store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません")

    ticket = models.Ticket(
        store_id=data.store_id,
        customer_id=data.customer_id,
        table_no=data.table_no,
        staff_id=current_user.id,
        notes=data.notes,
        guest_count=data.guest_count,
        plan_type=data.plan_type,
        visit_type=data.visit_type,
    )
    # セット料金を自動追加
    if store.set_price > 0:
        ticket.total_amount = store.set_price

    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # セット料金を注文明細に追加
    if store.set_price > 0:
        item = models.OrderItem(
            ticket_id=ticket.id,
            item_type="set",
            item_name="セット料金",
            quantity=1,
            unit_price=store.set_price,
            amount=store.set_price,
        )
        db.add(item)
        db.commit()

    return ticket


@router.post("/{ticket_id}/orders")
def add_order(
    ticket_id: int,
    data: OrderItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id,
        models.Ticket.is_closed == False
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")

    amount = data.quantity * data.unit_price
    item = models.OrderItem(
        ticket_id=ticket_id,
        item_type=data.item_type,
        item_name=data.item_name,
        quantity=data.quantity,
        unit_price=data.unit_price,
        amount=amount,
        cast_id=data.cast_id,
    )
    db.add(item)
    ticket.total_amount += amount

    # 延長の場合カウントアップ
    if data.item_type == "extension":
        ticket.extension_count += 1

    db.commit()
    return {"message": "注文を追加しました", "id": item.id, "total_amount": ticket.total_amount}


@router.delete("/orders/{item_id}")
def cancel_order(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = db.query(models.OrderItem).filter(
        models.OrderItem.id == item_id,
        models.OrderItem.canceled_at == None
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="注文が見つかりません")

    ticket = db.query(models.Ticket).filter(models.Ticket.id == item.ticket_id).first()
    item.canceled_at = datetime.utcnow()
    item.canceled_by = current_user.id
    ticket.total_amount -= item.amount
    if item.item_type == "extension" and ticket.extension_count > 0:
        ticket.extension_count -= 1

    db.commit()
    return {"message": "注文をキャンセルしました"}


@router.post("/{ticket_id}/close", response_model=TicketResponse)
def close_ticket(
    ticket_id: int,
    data: TicketClose,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id,
        models.Ticket.is_closed == False
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")

    ticket.is_closed = True
    ticket.ended_at = datetime.utcnow()
    ticket.payment_method = data.payment_method
    ticket.cash_amount = data.cash_amount
    ticket.card_amount = data.card_amount
    ticket.discount_amount = data.discount_amount
    ticket.total_amount = max(0, ticket.total_amount - data.discount_amount)

    # 顧客の来店データ更新
    if ticket.customer_id:
        customer = db.query(models.Customer).filter(models.Customer.id == ticket.customer_id).first()
        if customer:
            customer.total_visits += 1
            customer.total_spend += ticket.total_amount
            customer.ltv = customer.total_spend
            from datetime import date
            customer.last_visit_date = date.today()
            if not customer.first_visit_date:
                customer.first_visit_date = date.today()

    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("/live/{store_id}")
def get_live_summary(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """リアルタイム売上サマリー"""
    from datetime import date
    today = date.today()

    open_tickets = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.is_closed == False,
    ).all()

    closed_today = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.is_closed == True,
        models.Ticket.ended_at >= datetime.combine(today, datetime.min.time()),
    ).all()

    return {
        "open_count": len(open_tickets),
        "open_amount": sum(t.total_amount for t in open_tickets),
        "closed_count": len(closed_today),
        "closed_amount": sum(t.total_amount for t in closed_today),
        "total_amount": sum(t.total_amount for t in open_tickets) + sum(t.total_amount for t in closed_today),
        "open_tickets": [{"id": t.id, "table_no": t.table_no, "amount": t.total_amount, "started_at": t.started_at} for t in open_tickets],
    }
