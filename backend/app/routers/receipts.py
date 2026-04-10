"""領収書 / 概算伝票 PDF発行ルーター"""
import io
from datetime import datetime, timedelta, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from ..database import get_db
from .. import models
from ..auth import get_current_user

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# 日本語フォント (reportlab 同梱の CID フォント、追加ファイル不要)
try:
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    JP_FONT = "HeiseiKakuGo-W5"
except Exception:
    JP_FONT = "Helvetica"

router = APIRouter(prefix="/api/receipts", tags=["receipts"])


# ─────────────────────────────────────────
# 共通ヘルパー
# ─────────────────────────────────────────
def _calc_amounts(ticket: models.Ticket) -> dict:
    """ticket から税サ込み合計・サービス料・消費税を算出"""
    senkaikei = sum(
        abs(i.amount or 0) for i in (ticket.order_items or [])
        if i.canceled_at is None and (
            (i.item_name or '').startswith('先会計')
            or (i.item_name or '').startswith('分割清算')
            or (i.item_name or '').startswith('値引き')
        )
    )
    subtotal = (ticket.total_amount or 0) + senkaikei  # 税サ対象の小計
    # サービス料10%, 消費税10% (合計21%)
    service = round(subtotal * 0.10)
    tax_base = subtotal + service
    tax = round(tax_base * 0.10)
    grand = subtotal + service + tax - senkaikei - (ticket.discount_amount or 0)
    return {
        "subtotal": subtotal,
        "service": service,
        "tax": tax,
        "grand": max(0, grand),
        "senkaikei": senkaikei,
    }


def _next_receipt_no(db: Session, store_id: int) -> str:
    """日付+連番方式: 20260410-001"""
    today = date.today()
    prefix = today.strftime("%Y%m%d")
    count = db.query(func.count(models.ReceiptIssuance.id)).filter(
        models.ReceiptIssuance.store_id == store_id,
        models.ReceiptIssuance.receipt_no.like(f"{prefix}-%"),
    ).scalar() or 0
    return f"{prefix}-{count + 1:03d}"


def _draw_centered(c: canvas.Canvas, x_center: float, y: float, text: str, font: str = None, size: int = 10):
    c.setFont(font or JP_FONT, size)
    w = c.stringWidth(text, font or JP_FONT, size)
    c.drawString(x_center - w / 2, y, text)


# ─────────────────────────────────────────
# 80mm レシート PDF（領収書）
# ─────────────────────────────────────────
def _generate_receipt_80mm(ticket: models.Ticket, store: models.Store, amounts: dict,
                            receipt_no: str, recipient: str, note: str, issued_at: datetime) -> bytes:
    width = 80 * mm
    # 先に仮キャンバスで描画して高さを測定、次に正しい高さで再描画
    def _draw_content(c: canvas.Canvas, height: float) -> float:
        margin = 4 * mm
        cx = width / 2
        y = height - 8 * mm

        # タイトル
        _draw_centered(c, cx, y, "領 収 書", size=18)
        y -= 8 * mm
        c.setLineWidth(0.5)
        c.line(margin, y, width - margin, y)
        y -= 5 * mm

        # No / 日付
        c.setFont(JP_FONT, 8)
        c.drawString(margin, y, f"No. {receipt_no}")
        date_str = issued_at.strftime("%Y年%m月%d日")
        c.drawRightString(width - margin, y, date_str)
        y -= 8 * mm

        # 宛名
        c.setFont(JP_FONT, 11)
        name_text = (recipient or "").strip()
        name_line = f"{name_text}    様" if name_text else "                  様"
        c.drawString(margin + 2 * mm, y, name_line)
        c.line(margin + 2 * mm, y - 1 * mm, width - margin - 2 * mm, y - 1 * mm)
        y -= 10 * mm

        # 金額（大きめ）
        amount_str = f"¥ {amounts['grand']:,} -"
        _draw_centered(c, cx, y, amount_str, size=22)
        y -= 4 * mm
        c.line(margin + 5 * mm, y, width - margin - 5 * mm, y)
        y -= 6 * mm

        # 内訳
        c.setFont(JP_FONT, 8)
        c.drawString(margin + 2 * mm, y, f"（サービス料等 10%）  ¥{amounts['service']:,}")
        y -= 4 * mm
        c.drawString(margin + 2 * mm, y, f"（消費税     10%）  ¥{amounts['tax']:,}")
        y -= 7 * mm

        # 但し書き + [印]
        c.setFont(JP_FONT, 9)
        c.drawString(margin + 2 * mm, y, f"但し {note}")
        seal_x = width - margin - 8 * mm
        c.circle(seal_x, y + 1 * mm, 3 * mm, stroke=1, fill=0)
        _draw_centered(c, seal_x, y, "印", size=6)
        y -= 8 * mm

        # 領収文 + 収入印紙(5万円以上)
        c.setFont(JP_FONT, 8)
        c.drawString(margin + 2 * mm, y, "上記金額正に領収いたしました")
        if amounts['grand'] >= 50000:
            stamp_w = 18 * mm
            stamp_h = 25 * mm
            stamp_x = width - margin - stamp_w - 1 * mm
            stamp_y = y - stamp_h + 4 * mm
            c.rect(stamp_x, stamp_y, stamp_w, stamp_h, stroke=1, fill=0)
            c.setFont(JP_FONT, 7)
            _draw_centered(c, stamp_x + stamp_w / 2, stamp_y + stamp_h / 2 + 2 * mm, "収入")
            _draw_centered(c, stamp_x + stamp_w / 2, stamp_y + stamp_h / 2 - 4 * mm, "印紙")
            y -= stamp_h + 2 * mm
        else:
            y -= 8 * mm

        c.line(margin, y, width - margin, y)
        y -= 8 * mm

        # 店舗情報
        c.setFont(JP_FONT, 22)
        c.drawString(margin + 2 * mm, y, store.receipt_name or store.name or "")
        y -= 8 * mm
        c.setFont(JP_FONT, 8)
        if store.postal_code:
            c.drawString(margin + 2 * mm, y, f"〒{store.postal_code}")
            y -= 4 * mm
        if store.address:
            c.drawString(margin + 2 * mm, y, store.address)
            y -= 4 * mm
        if store.phone:
            c.drawString(margin + 2 * mm, y, f"TEL: {store.phone}")
            y -= 4 * mm
        if store.invoice_number:
            c.drawString(margin + 2 * mm, y, f"登録番号: {store.invoice_number}")
            y -= 4 * mm

        return y  # 最終Y座標を返す

    # 1パス目: 高さ測定
    tmp_buf = io.BytesIO()
    tmp_c = canvas.Canvas(tmp_buf, pagesize=(width, 500 * mm))
    final_y = _draw_content(tmp_c, 500 * mm)
    content_height = (500 * mm - final_y) + 8 * mm  # 下マージン追加

    # 2パス目: 正しい高さで描画
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, content_height))
    _draw_content(c, content_height)
    c.showPage()
    c.save()
    return buf.getvalue()


# ─────────────────────────────────────────
# A4 PDF（領収書）
# ─────────────────────────────────────────
def _generate_receipt_a4(ticket: models.Ticket, store: models.Store, amounts: dict,
                          receipt_no: str, recipient: str, note: str, issued_at: datetime) -> bytes:
    width, height = A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    margin = 20 * mm
    cx = width / 2
    y = height - 30 * mm

    # タイトル
    _draw_centered(c, cx, y, "領 収 書", size=28)
    y -= 12 * mm
    c.setLineWidth(0.8)
    c.line(margin, y, width - margin, y)
    y -= 10 * mm

    # No / 日付
    c.setFont(JP_FONT, 11)
    c.drawString(margin, y, f"No. {receipt_no}")
    c.drawRightString(width - margin, y, issued_at.strftime("%Y年%m月%d日"))
    y -= 18 * mm

    # 宛名
    c.setFont(JP_FONT, 16)
    name_text = (recipient or "").strip()
    name_line = f"{name_text}    様" if name_text else "                          様"
    c.drawString(margin + 10 * mm, y, name_line)
    c.line(margin + 10 * mm, y - 2 * mm, width - margin - 30 * mm, y - 2 * mm)
    y -= 20 * mm

    # 金額（大きく）
    amount_str = f"¥ {amounts['grand']:,} -"
    _draw_centered(c, cx, y, amount_str, size=36)
    y -= 8 * mm
    c.line(margin + 30 * mm, y, width - margin - 30 * mm, y)
    y -= 12 * mm

    # 内訳
    c.setFont(JP_FONT, 11)
    c.drawString(margin + 30 * mm, y, f"（サービス料等 10%）  ¥{amounts['service']:,}")
    y -= 6 * mm
    c.drawString(margin + 30 * mm, y, f"（消費税     10%）  ¥{amounts['tax']:,}")
    y -= 14 * mm

    # 但し書き + 印
    c.setFont(JP_FONT, 13)
    c.drawString(margin + 10 * mm, y, f"但し {note}")
    seal_x = width - margin - 20 * mm
    c.circle(seal_x, y + 2 * mm, 6 * mm, stroke=1, fill=0)
    _draw_centered(c, seal_x, y, "印", size=10)
    y -= 14 * mm

    # 領収文 + 収入印紙
    c.setFont(JP_FONT, 11)
    c.drawString(margin + 10 * mm, y, "上記金額正に領収いたしました")
    if amounts['grand'] >= 50000:
        stamp_w = 22 * mm
        stamp_h = 32 * mm
        stamp_x = width - margin - stamp_w - 5 * mm
        stamp_y = y - stamp_h + 6 * mm
        c.rect(stamp_x, stamp_y, stamp_w, stamp_h, stroke=1, fill=0)
        c.setFont(JP_FONT, 9)
        _draw_centered(c, stamp_x + stamp_w / 2, stamp_y + stamp_h / 2 + 3 * mm, "収入")
        _draw_centered(c, stamp_x + stamp_w / 2, stamp_y + stamp_h / 2 - 6 * mm, "印紙")
        y -= stamp_h + 4 * mm
    else:
        y -= 14 * mm

    c.line(margin, y, width - margin, y)
    y -= 14 * mm

    # 店舗情報
    c.setFont(JP_FONT, 28)
    c.drawString(margin, y, store.receipt_name or store.name or "")
    y -= 12 * mm
    c.setFont(JP_FONT, 11)
    if store.postal_code:
        c.drawString(margin, y, f"〒{store.postal_code}")
        y -= 6 * mm
    if store.address:
        c.drawString(margin, y, store.address)
        y -= 6 * mm
    if store.phone:
        c.drawString(margin, y, f"TEL: {store.phone}")
        y -= 6 * mm
    if store.invoice_number:
        c.drawString(margin, y, f"登録番号: {store.invoice_number}")
        y -= 6 * mm
    if store.receipt_footer:
        y -= 4 * mm
        c.setFont(JP_FONT, 9)
        for line in (store.receipt_footer or "").split("\n"):
            c.drawString(margin, y, line)
            y -= 5 * mm

    c.showPage()
    c.save()
    return buf.getvalue()


# ─────────────────────────────────────────
# 概算伝票 PDF (80mm)
# ─────────────────────────────────────────
def _generate_estimate_80mm(ticket: models.Ticket, store: models.Store, amounts: dict, issued_at: datetime) -> bytes:
    width = 80 * mm

    def _draw_est(c: canvas.Canvas, height: float) -> float:
        margin = 4 * mm
        cx = width / 2
        y = height - 8 * mm

        _draw_centered(c, cx, y, store.receipt_name or store.name or "", size=12)
        y -= 6 * mm
        if store.address:
            c.setFont(JP_FONT, 7)
            _draw_centered(c, cx, y, store.address, size=7)
            y -= 4 * mm
        if store.phone:
            _draw_centered(c, cx, y, f"TEL: {store.phone}", size=7)
            y -= 6 * mm

        c.line(margin, y, width - margin, y)
        y -= 5 * mm
        _draw_centered(c, cx, y, "【概算伝票】", size=12)
        y -= 7 * mm

        c.setFont(JP_FONT, 8)
        c.drawString(margin, y, f"卓番: {ticket.table_no or '-'}")
        y -= 4 * mm
        if ticket.started_at:
            in_jst = ticket.started_at + timedelta(hours=9)
            c.drawString(margin, y, f"入店: {in_jst.strftime('%H:%M')}")
            y -= 4 * mm
        c.drawString(margin, y, f"発行: {(issued_at + timedelta(hours=9)).strftime('%H:%M')}")
        y -= 6 * mm

        c.line(margin, y, width - margin, y)
        y -= 5 * mm

        c.setFont(JP_FONT, 8)
        for item in (ticket.order_items or []):
            if item.canceled_at:
                continue
            name = (item.item_name or item.item_type or '')[:18]
            qty = item.quantity or 1
            amt = item.amount or 0
            c.drawString(margin, y, name)
            c.drawRightString(width - margin, y, f"{qty}  ¥{amt:,}")
            y -= 4 * mm

        y -= 2 * mm
        c.line(margin, y, width - margin, y)
        y -= 5 * mm

        c.setFont(JP_FONT, 9)
        c.drawString(margin, y, "小計")
        c.drawRightString(width - margin, y, f"¥{amounts['subtotal']:,}")
        y -= 5 * mm
        c.drawString(margin, y, "サービス料 10%")
        c.drawRightString(width - margin, y, f"¥{amounts['service']:,}")
        y -= 5 * mm
        c.drawString(margin, y, "消費税 10%")
        c.drawRightString(width - margin, y, f"¥{amounts['tax']:,}")
        y -= 6 * mm
        c.line(margin, y, width - margin, y)
        y -= 6 * mm
        c.setFont(JP_FONT, 14)
        c.drawString(margin, y, "合計")
        c.drawRightString(width - margin, y, f"¥{amounts['grand']:,}")
        y -= 10 * mm

        c.setFont(JP_FONT, 7)
        _draw_centered(c, cx, y, "※これは概算伝票です", size=7)
        y -= 4 * mm
        _draw_centered(c, cx, y, "正式な領収書ではありません", size=7)
        return y

    # 1パス: 高さ測定
    tmp_buf = io.BytesIO()
    tmp_c = canvas.Canvas(tmp_buf, pagesize=(width, 500 * mm))
    final_y = _draw_est(tmp_c, 500 * mm)
    content_height = (500 * mm - final_y) + 8 * mm

    # 2パス: 正しい高さで描画
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, content_height))
    _draw_est(c, content_height)
    c.showPage()
    c.save()
    return buf.getvalue()


def _generate_estimate_a4(ticket: models.Ticket, store: models.Store, amounts: dict, issued_at: datetime) -> bytes:
    width, height = A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    margin = 20 * mm
    cx = width / 2
    y = height - 25 * mm

    _draw_centered(c, cx, y, store.receipt_name or store.name or "", size=18)
    y -= 8 * mm
    c.setFont(JP_FONT, 10)
    if store.address:
        _draw_centered(c, cx, y, store.address)
        y -= 5 * mm
    if store.phone:
        _draw_centered(c, cx, y, f"TEL: {store.phone}")
        y -= 8 * mm

    c.line(margin, y, width - margin, y)
    y -= 8 * mm
    _draw_centered(c, cx, y, "【概算伝票】", size=18)
    y -= 12 * mm

    c.setFont(JP_FONT, 11)
    c.drawString(margin, y, f"卓番: {ticket.table_no or '-'}")
    if ticket.started_at:
        in_jst = ticket.started_at + timedelta(hours=9)
        c.drawString(margin + 60 * mm, y, f"入店: {in_jst.strftime('%H:%M')}")
    c.drawRightString(width - margin, y, f"発行: {(issued_at + timedelta(hours=9)).strftime('%H:%M')}")
    y -= 10 * mm

    c.line(margin, y, width - margin, y)
    y -= 8 * mm

    # ヘッダー
    c.setFont(JP_FONT, 10)
    c.drawString(margin, y, "ご注文")
    c.drawString(margin + 100 * mm, y, "数")
    c.drawRightString(width - margin - 30 * mm, y, "単価")
    c.drawRightString(width - margin, y, "金額")
    y -= 5 * mm
    c.line(margin, y, width - margin, y)
    y -= 5 * mm

    for item in (ticket.order_items or []):
        if item.canceled_at:
            continue
        name = (item.item_name or item.item_type or '')[:30]
        qty = item.quantity or 1
        amt = item.amount or 0
        unit = item.unit_price or 0
        c.drawString(margin, y, name)
        c.drawString(margin + 100 * mm, y, str(qty))
        c.drawRightString(width - margin - 30 * mm, y, f"¥{unit:,}")
        c.drawRightString(width - margin, y, f"¥{amt:,}")
        y -= 5 * mm
        if y < 60 * mm:
            break

    y -= 5 * mm
    c.line(margin, y, width - margin, y)
    y -= 8 * mm

    c.setFont(JP_FONT, 11)
    c.drawString(width - margin - 70 * mm, y, "小計")
    c.drawRightString(width - margin, y, f"¥{amounts['subtotal']:,}")
    y -= 6 * mm
    c.drawString(width - margin - 70 * mm, y, "サービス料 10%")
    c.drawRightString(width - margin, y, f"¥{amounts['service']:,}")
    y -= 6 * mm
    c.drawString(width - margin - 70 * mm, y, "消費税 10%")
    c.drawRightString(width - margin, y, f"¥{amounts['tax']:,}")
    y -= 8 * mm
    c.line(width - margin - 80 * mm, y, width - margin, y)
    y -= 8 * mm
    c.setFont(JP_FONT, 16)
    c.drawString(width - margin - 70 * mm, y, "合計")
    c.drawRightString(width - margin, y, f"¥{amounts['grand']:,}")
    y -= 15 * mm

    c.setFont(JP_FONT, 9)
    _draw_centered(c, cx, y, "※これは概算伝票です。正式な領収書ではありません。")

    c.showPage()
    c.save()
    return buf.getvalue()


# ─────────────────────────────────────────
# エンドポイント
# ─────────────────────────────────────────
class IssueRequest(BaseModel):
    recipient_name: Optional[str] = ""
    note: Optional[str] = "ご飲食代として"
    paper_size: Optional[str] = "80mm"  # 80mm | a4


@router.get("/estimate/{ticket_id}")
def get_estimate_pdf(
    ticket_id: int,
    size: str = Query("80mm"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")
    store = db.query(models.Store).filter(models.Store.id == ticket.store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません")

    amounts = _calc_amounts(ticket)
    issued_at = datetime.utcnow()

    if size == "a4":
        pdf = _generate_estimate_a4(ticket, store, amounts, issued_at)
    else:
        pdf = _generate_estimate_80mm(ticket, store, amounts, issued_at)

    filename = f"estimate_{ticket.table_no or ticket.id}_{issued_at.strftime('%H%M%S')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/issue/{ticket_id}")
def issue_receipt(
    ticket_id: int,
    req: IssueRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="伝票が見つかりません")
    store = db.query(models.Store).filter(models.Store.id == ticket.store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません")

    amounts = _calc_amounts(ticket)
    receipt_no = _next_receipt_no(db, store.id)
    issued_at = datetime.utcnow()
    note = (req.note or "ご飲食代として").strip()
    paper = req.paper_size or "80mm"

    issuance = models.ReceiptIssuance(
        ticket_id=ticket.id,
        store_id=store.id,
        receipt_no=receipt_no,
        recipient_name=req.recipient_name or "",
        note=note,
        amount=amounts["grand"],
        service_charge=amounts["service"],
        tax=amounts["tax"],
        issued_by=current_user.id,
        issued_by_name=getattr(current_user, "name", None),
        paper_size=paper,
        issued_at=issued_at,
    )
    db.add(issuance)
    db.commit()
    db.refresh(issuance)

    if paper == "a4":
        pdf = _generate_receipt_a4(ticket, store, amounts, receipt_no, req.recipient_name or "", note, issued_at)
    else:
        pdf = _generate_receipt_80mm(ticket, store, amounts, receipt_no, req.recipient_name or "", note, issued_at)

    filename = f"receipt_{receipt_no}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Receipt-No": receipt_no,
            "X-Issuance-Id": str(issuance.id),
        },
    )


@router.get("/reissue/{issuance_id}")
def reissue_receipt(
    issuance_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """過去の発行履歴から再発行（同じ番号・宛名・但し書きで再生成）"""
    iss = db.query(models.ReceiptIssuance).filter(models.ReceiptIssuance.id == issuance_id).first()
    if not iss:
        raise HTTPException(status_code=404, detail="発行履歴が見つかりません")
    ticket = db.query(models.Ticket).filter(models.Ticket.id == iss.ticket_id).first()
    store = db.query(models.Store).filter(models.Store.id == iss.store_id).first()
    if not ticket or not store:
        raise HTTPException(status_code=404, detail="伝票/店舗が見つかりません")

    amounts = _calc_amounts(ticket)
    if iss.paper_size == "a4":
        pdf = _generate_receipt_a4(ticket, store, amounts, iss.receipt_no, iss.recipient_name or "", iss.note or "", iss.issued_at)
    else:
        pdf = _generate_receipt_80mm(ticket, store, amounts, iss.receipt_no, iss.recipient_name or "", iss.note or "", iss.issued_at)

    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="receipt_{iss.receipt_no}.pdf"'},
    )


@router.get("/history/{ticket_id}")
def get_receipt_history(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = db.query(models.ReceiptIssuance).filter(
        models.ReceiptIssuance.ticket_id == ticket_id
    ).order_by(models.ReceiptIssuance.issued_at.desc()).all()
    return [
        {
            "id": r.id,
            "receipt_no": r.receipt_no,
            "recipient_name": r.recipient_name,
            "note": r.note,
            "amount": r.amount,
            "paper_size": r.paper_size,
            "issued_by_name": r.issued_by_name,
            "issued_at": r.issued_at.isoformat() if r.issued_at else None,
        }
        for r in rows
    ]
