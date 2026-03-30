import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from ..database import get_db
from .. import models
from ..auth import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


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
