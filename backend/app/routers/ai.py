import os
import json
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from ..database import get_db
from .. import models
from ..auth import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def get_claude_client():
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    except Exception:
        return None


def call_claude(prompt: str, system: str = "") -> str:
    client = get_claude_client()
    if not client:
        return "AI機能を使用するにはANTHROPIC_API_KEYを設定してください。"
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        return f"AI呼び出しエラー: {str(e)}"


ROTATION_SYSTEM = """
あなたはナイトワーク（ガールズバー）の現場専門AIです。
付け回し（テーブルへのキャスト配置）に関して、豊富な知識と経験を持ちます。

以下の観点で最適なキャストを推薦してください：
- 顧客の過去来店歴・好み・指名キャスト
- 現在出勤中のキャストのスキル・相性
- 時間帯・混雑状況
- 売上最大化と顧客満足度のバランス

回答は日本語で、具体的かつ簡潔に。
"""

MANAGEMENT_SYSTEM = """
あなたはナイトワーク（ガールズバー）の経営専門AIコンサルタントです。
売上データ・顧客データ・外部環境を分析し、経営者に具体的な営業方針を提示します。

分析観点：
- 売上トレンドと目標達成率
- 顧客層の変化（新規/リピーター比率）
- キャスト別パフォーマンス
- 曜日・時間帯別データ
- 季節要因・地域イベント

回答は日本語で、実践的な提案を3〜5つ箇条書きで。
"""

CUSTOMER_SYSTEM = """
あなたは顧客管理の専門AIです。
接客メモを分析し、顧客プロフィールを更新します。

以下を抽出・要約してください：
- 顧客の好み・趣味・話題
- 対応で気をつけるべきポイント
- 次回来店時の提案
- 特記事項

200字以内で簡潔に。
"""


class RotationRequest(BaseModel):
    store_id: int
    customer_id: Optional[int] = None
    customer_notes: Optional[str] = None
    available_cast_ids: list[int] = []


class ManagementRequest(BaseModel):
    store_id: int
    period: str = "today"  # today, week, month


class CustomerProfileRequest(BaseModel):
    customer_id: int
    new_note: str


@router.post("/rotation-advice")
def rotation_advice(
    req: RotationRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 顧客情報取得
    customer_info = ""
    if req.customer_id:
        customer = db.query(models.Customer).filter(models.Customer.id == req.customer_id).first()
        if customer:
            customer_info = f"顧客名: {customer.alias or customer.name}\n"
            customer_info += f"来店回数: {customer.total_visits}回\n"
            customer_info += f"AI顧客カルテ: {customer.ai_summary or 'なし'}\n"
            if customer.preferences:
                customer_info += f"好み: {customer.preferences}\n"

    # 利用可能キャスト情報
    casts_info = ""
    if req.available_cast_ids:
        casts = db.query(models.Cast).filter(models.Cast.id.in_(req.available_cast_ids)).all()
        for c in casts:
            casts_info += f"- {c.stage_name}（ランク:{c.rank}、お酒:{c.alcohol_tolerance}）\n"

    prompt = f"""
以下の状況で付け回しアドバイスをお願いします。

【顧客情報】
{customer_info or req.customer_notes or '情報なし'}

【現在出勤中のキャスト】
{casts_info or '情報なし'}

最適な付け回し順と理由を教えてください。
"""

    advice = call_claude(prompt, ROTATION_SYSTEM)

    # 保存
    ai_record = models.AIAdvice(
        store_id=req.store_id,
        advice_type=models.AIAdviceType.rotation,
        context={"customer_id": req.customer_id, "cast_ids": req.available_cast_ids},
        advice=advice,
    )
    db.add(ai_record)
    db.commit()

    return {"advice": advice}


@router.post("/management-advice")
def management_advice(
    req: ManagementRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from datetime import date
    today = date.today()

    # 直近の日報データ取得
    reports = db.query(models.DailyReport).filter(
        models.DailyReport.store_id == req.store_id
    ).order_by(models.DailyReport.date.desc()).limit(7).all()

    report_summary = ""
    for r in reports:
        report_summary += f"{r.date}: 売上{r.total_sales:,}円, 新規{r.new_customers}名, リピ{r.repeat_customers}名\n"

    prompt = f"""
店舗の直近データを分析して経営アドバイスをお願いします。

【直近7日間の実績】
{report_summary or 'データなし'}

今週の営業方針と改善提案を教えてください。
"""

    advice = call_claude(prompt, MANAGEMENT_SYSTEM)

    ai_record = models.AIAdvice(
        store_id=req.store_id,
        advice_type=models.AIAdviceType.management,
        context={"period": req.period},
        advice=advice,
    )
    db.add(ai_record)
    db.commit()

    return {"advice": advice}


@router.post("/customer-profile")
def update_customer_profile(
    req: CustomerProfileRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = db.query(models.Customer).filter(models.Customer.id == req.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="顧客が見つかりません")

    # 過去メモ取得
    notes = db.query(models.CustomerVisitNote).filter(
        models.CustomerVisitNote.customer_id == req.customer_id
    ).order_by(models.CustomerVisitNote.created_at.desc()).limit(5).all()

    past_notes = "\n".join([f"- {n.note}" for n in notes])

    prompt = f"""
顧客カルテを更新してください。

【過去のメモ】
{past_notes or 'なし'}

【今回の新しいメモ】
{req.new_note}

顧客プロフィールを200字以内で要約してください。
"""

    summary = call_claude(prompt, CUSTOMER_SYSTEM)
    customer.ai_summary = summary
    db.commit()

    return {"summary": summary}


# ─────────────────────────────────────────
# Gemini ベース 付け回しAIアドバイザー
# ─────────────────────────────────────────

ADVISOR_SYSTEM = """あなたはガールズバーの付け回し（テーブル割り当て）専門AIです。
以下のJSONデータを分析し、最適なキャスト配置を提案してください。

判断基準：
1. 未接客優先: その客に一度も付いたことがないキャストを優先
2. 相性マッチ: 過去にそのキャストが付いた時に売上(MG/シャンパン/ショット)が伸びた実績
3. 客の好み: 客の注文傾向に合うキャスト(例: ショット好き客→キャストショット実績多いキャスト)
4. 公平性: 既に対応中の卓数が少ないキャストを優先
5. 推しキャスト在席時はそれを尊重

出力は必ず以下のJSON形式のみ:
{
  "suggestions": [
    {
      "ticket_id": <番号>,
      "table_no": "<卓番>",
      "customer_name": "<客名>",
      "recommended_casts": [
        {"cast_id": <id>, "stage_name": "<名前>", "reason": "<推薦理由 30文字程度>", "score": <1-100>}
      ]
    }
  ],
  "overall_advice": "<店舗全体への一言アドバイス 100文字程度>"
}
余計な文章・マークダウンは出力しないこと。"""


def call_gemini_json(prompt: str, system: str = "") -> dict:
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEYが設定されていません"}
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system or None,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.4,
            },
        )
        resp = model.generate_content(prompt)
        text = resp.text or "{}"
        return json.loads(text)
    except Exception as e:
        return {"error": f"Gemini呼び出しエラー: {str(e)}"}


def _build_advisor_context(db: Session, store_id: int) -> dict:
    """店舗の現状況とAI判断材料を集約"""
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())

    # 営業中(未会計)の伝票
    open_tickets = db.query(models.Ticket).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.is_closed == False,
        models.Ticket.deleted_at.is_(None),
    ).all()

    # 本日対応中(本日伝票に紐付くキャスト assignment 全員)を「出勤中」とみなす
    today_ticket_ids = [t.id for t in db.query(models.Ticket.id).filter(
        models.Ticket.store_id == store_id,
        models.Ticket.started_at >= today_start,
        models.Ticket.deleted_at.is_(None),
    ).all()]

    working_cast_ids = set()
    if today_ticket_ids:
        rows = db.query(models.CastAssignment.cast_id).filter(
            models.CastAssignment.ticket_id.in_(today_ticket_ids)
        ).distinct().all()
        working_cast_ids = {r[0] for r in rows}

    # 出勤中キャストが現在対応中の卓数(未会計のみ)
    busy_count: dict[int, int] = {}
    for t in open_tickets:
        for a in t.assignments:
            if a.ended_at is None:
                busy_count[a.cast_id] = busy_count.get(a.cast_id, 0) + 1

    # キャスト情報 + 過去実績(MG/champagne/shot_cast の総注文数)
    casts_info = []
    if working_cast_ids:
        casts = db.query(models.Cast).filter(models.Cast.id.in_(working_cast_ids)).all()
        for c in casts:
            stats_rows = db.query(
                models.OrderItem.item_type,
                func.coalesce(func.sum(models.OrderItem.quantity), 0)
            ).filter(
                models.OrderItem.cast_id == c.id,
                models.OrderItem.canceled_at.is_(None),
                models.OrderItem.item_type.in_(["drink_mg", "champagne", "shot_cast"]),
            ).group_by(models.OrderItem.item_type).all()
            stats = {row[0]: int(row[1]) for row in stats_rows}
            casts_info.append({
                "cast_id": c.id,
                "stage_name": c.stage_name,
                "rank": c.rank,
                "alcohol": c.alcohol_tolerance,
                "busy_tables_now": busy_count.get(c.id, 0),
                "lifetime_mg_count": stats.get("drink_mg", 0),
                "lifetime_champagne_count": stats.get("champagne", 0),
                "lifetime_shot_cast_count": stats.get("shot_cast", 0),
            })

    # 各営業中卓の情報
    tickets_info = []
    for t in open_tickets:
        cust = t.customer
        # 顧客の注文傾向(過去全伝票)
        cust_pref = {}
        if cust:
            cust_ticket_ids = [r[0] for r in db.query(models.Ticket.id).filter(
                models.Ticket.customer_id == cust.id,
                models.Ticket.deleted_at.is_(None),
            ).all()]
            if cust_ticket_ids:
                rows = db.query(
                    models.OrderItem.item_type,
                    func.coalesce(func.sum(models.OrderItem.quantity), 0),
                ).filter(
                    models.OrderItem.ticket_id.in_(cust_ticket_ids),
                    models.OrderItem.canceled_at.is_(None),
                    models.OrderItem.item_type.in_(["drink_mg", "champagne", "shot_cast", "drink_l", "drink_s"]),
                ).group_by(models.OrderItem.item_type).all()
                cust_pref = {row[0]: int(row[1]) for row in rows}

        # 顧客×キャストの過去接客回数(出勤中キャストとの過去履歴)
        past_cast_counts: dict[int, int] = {}
        if cust and working_cast_ids:
            cust_ticket_ids2 = [r[0] for r in db.query(models.Ticket.id).filter(
                models.Ticket.customer_id == cust.id,
                models.Ticket.deleted_at.is_(None),
            ).all()]
            if cust_ticket_ids2:
                rows = db.query(
                    models.CastAssignment.cast_id,
                    func.count(models.CastAssignment.id),
                ).filter(
                    models.CastAssignment.ticket_id.in_(cust_ticket_ids2),
                    models.CastAssignment.cast_id.in_(working_cast_ids),
                ).group_by(models.CastAssignment.cast_id).all()
                past_cast_counts = {r[0]: int(r[1]) for r in rows}

        # 現在対応中のキャスト
        current_casts = [
            {"cast_id": a.cast_id, "stage_name": (a.cast.stage_name if a.cast else "")}
            for a in t.assignments if a.ended_at is None
        ]

        elapsed_min = 0
        if t.started_at:
            elapsed_min = int((datetime.utcnow() - t.started_at).total_seconds() / 60)

        tickets_info.append({
            "ticket_id": t.id,
            "table_no": t.table_no,
            "customer_id": cust.id if cust else None,
            "customer_name": (cust.alias or cust.name) if cust else "未登録客",
            "customer_total_visits": cust.total_visits if cust else 0,
            "customer_preferences": cust_pref,
            "past_cast_counts_with_working": past_cast_counts,
            "guest_count": t.guest_count or 1,
            "elapsed_minutes": elapsed_min,
            "current_total": t.total_amount or 0,
            "featured_cast_id": t.featured_cast_id,
            "current_casts": current_casts,
        })

    return {
        "store_id": store_id,
        "now": datetime.utcnow().isoformat(),
        "working_casts": casts_info,
        "open_tickets": tickets_info,
    }


@router.post("/suggest-rotation/{store_id}")
def suggest_rotation(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    context = _build_advisor_context(db, store_id)
    if not context["working_casts"]:
        return {"suggestions": [], "overall_advice": "出勤中のキャストが見つかりません。", "context": context}
    if not context["open_tickets"]:
        return {"suggestions": [], "overall_advice": "現在営業中の卓がありません。", "context": context}

    prompt = f"""以下の店舗状況を分析して、各卓に最適なキャスト推薦をJSONで出力してください。

【データ】
{json.dumps(context, ensure_ascii=False, indent=2)}

各卓につき推薦キャストを最大3名(score降順)で提案。past_cast_counts_with_working が 0 のキャストは「未接客」として優先度UP。
"""

    result = call_gemini_json(prompt, ADVISOR_SYSTEM)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result
