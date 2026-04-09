"""
日報・月報の表示API。

エンドポイント:
- GET  /api/reports/daily/latest          : 指定 store/date の最新版を返す
- GET  /api/reports/daily/versions        : 指定 store/date の全バージョン一覧
- GET  /api/reports/daily/{snapshot_id}   : 特定スナップショットを取得
- POST /api/reports/daily/regenerate      : 指定 session_id から再生成（新バージョン）
- GET  /api/reports/monthly               : 月報集計（指定 store/year/month）
"""
from datetime import date as date_cls, datetime, timedelta
from typing import Optional
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from .. import models
from ..auth import get_current_user
from ..services.report_builder import (
    build_daily_report_payload,
    save_snapshot,
    get_latest_snapshot,
)


router = APIRouter(prefix="/api/reports", tags=["reports"])


# 一時的な管理API: 壊れた（cast_attendance が空の）スナップショットを削除
# 復旧完了後に削除予定
@router.post("/_admin/rollback-broken-snapshots")
def rollback_broken_snapshots(
    apply: bool = Query(False, description="True で実行、False で DRY RUN"),
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not getattr(current_user, "is_admin", False) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="管理者のみ実行可能")

    q = db.query(models.DailyReportSnapshot)
    if store_id:
        q = q.filter(models.DailyReportSnapshot.store_id == store_id)
    snaps = q.order_by(
        models.DailyReportSnapshot.store_id,
        models.DailyReportSnapshot.business_date,
        models.DailyReportSnapshot.version.desc(),
    ).all()

    results = []
    deleted = 0
    for s in snaps:
        payload = s.payload if isinstance(s.payload, dict) else {}
        cast_att = payload.get("cast_attendance") or []
        if len(cast_att) == 0:
            prev = db.query(models.DailyReportSnapshot).filter(
                models.DailyReportSnapshot.store_id == s.store_id,
                models.DailyReportSnapshot.business_date == s.business_date,
                models.DailyReportSnapshot.version < s.version,
            ).order_by(models.DailyReportSnapshot.version.desc()).first()
            entry = {
                "id": s.id,
                "store_id": s.store_id,
                "business_date": s.business_date.isoformat(),
                "version": s.version,
                "prev_version": prev.version if prev else None,
            }
            if apply and prev is not None:
                db.delete(s)
                deleted += 1
                entry["action"] = "deleted"
            elif prev is None:
                entry["action"] = "skip (no prev)"
            else:
                entry["action"] = "would delete"
            results.append(entry)

    if apply:
        db.commit()

    return {
        "mode": "APPLY" if apply else "DRY RUN",
        "deleted": deleted,
        "results": results,
    }


# ─────────────────────────────────────────
# 日報
# ─────────────────────────────────────────

@router.get("/daily/latest")
def get_daily_latest(
    store_id: int = Query(...),
    date: date_cls = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指定 store_id × business_date の最新版日報を返す"""
    snap = get_latest_snapshot(db, store_id, date)
    if snap is None:
        raise HTTPException(status_code=404, detail="日報が見つかりません")
    return {
        "id": snap.id,
        "store_id": snap.store_id,
        "business_date": snap.business_date.isoformat(),
        "version": snap.version,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
        "created_by": snap.created_by,
        "payload": snap.payload,
    }


@router.get("/daily/versions")
def get_daily_versions(
    store_id: int = Query(...),
    date: date_cls = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指定 store_id × business_date の全バージョン一覧（payload は除外）"""
    rows = db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.store_id == store_id,
        models.DailyReportSnapshot.business_date == date,
    ).order_by(models.DailyReportSnapshot.version.desc()).all()
    return [
        {
            "id": r.id,
            "version": r.version,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "created_by": r.created_by,
        }
        for r in rows
    ]


@router.get("/daily/list")
def list_daily_reports(
    store_id: int = Query(...),
    start: Optional[date_cls] = Query(None),
    end: Optional[date_cls] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指定店舗の日報一覧（最新版のみ・期間絞り込み可）"""
    q = db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.store_id == store_id,
    )
    if start:
        q = q.filter(models.DailyReportSnapshot.business_date >= start)
    if end:
        q = q.filter(models.DailyReportSnapshot.business_date <= end)
    rows = q.order_by(
        models.DailyReportSnapshot.business_date.desc(),
        models.DailyReportSnapshot.version.desc(),
    ).all()

    # 同じ business_date は最新版のみ残す
    seen = set()
    result = []
    for r in rows:
        if r.business_date in seen:
            continue
        seen.add(r.business_date)
        sales = (r.payload or {}).get("sales", {})
        result.append({
            "id": r.id,
            "business_date": r.business_date.isoformat(),
            "version": r.version,
            "total_amount": sales.get("total_amount", 0),
            "ticket_count": sales.get("ticket_count", 0),
            "guest_count": sales.get("guest_count", 0),
        })
    return result


@router.get("/daily/{snapshot_id}")
def get_daily_by_id(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    snap = db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.id == snapshot_id
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="スナップショットが見つかりません")
    return {
        "id": snap.id,
        "store_id": snap.store_id,
        "business_date": snap.business_date.isoformat(),
        "version": snap.version,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
        "created_by": snap.created_by,
        "payload": snap.payload,
    }


class RegenerateRequest(BaseModel):
    session_id: int


@router.post("/daily/regenerate")
def regenerate_daily(
    data: RegenerateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指定 session から日報を再生成して新バージョンとして保存"""
    session = db.query(models.BusinessSession).filter(
        models.BusinessSession.id == data.session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    payload = build_daily_report_payload(db, session, generated_by=current_user.id)
    biz_date = (session.opened_at + timedelta(hours=9)).date()
    snap = save_snapshot(db, session.store_id, biz_date, payload, generated_by=current_user.id)
    return {
        "id": snap.id,
        "version": snap.version,
        "business_date": biz_date.isoformat(),
    }


# ─────────────────────────────────────────
# 月報
# ─────────────────────────────────────────

def _aggregate_monthly(payloads: list[dict]) -> dict:
    """日報JSONリストから月報集計"""
    if not payloads:
        return {
            "ticket_count": 0,
            "guest_count": 0,
            "n_count": 0,
            "r_count": 0,
            "total_amount": 0,
            "extension_count": 0,
            "drink_s_total": 0,
            "drink_l_total": 0,
            "drink_mg_total": 0,
            "champagne_count": 0,
            "champagne_amount": 0,
            "set_count": 0,
            "alcohol_expense": 0,
            "other_expense": 0,
            "motivation": {},
            "hourly_arrivals": {},
            "course_counts": {},
            "cast_rotation_total": 0,
            "cast_rotation_per_cast": {},
            "base_pay_total": 0,
            "incentive_total": 0,
            "actual_pay_total": 0,
            "ratio_percent": None,
            "avg_per_guest": None,
            "avg_per_n": None,
            "avg_per_r": None,
            "drink_s_per_set": None,
            "drink_l_per_set": None,
            "drink_mg_per_set": None,
        }

    motivation = defaultdict(int)
    hourly = defaultdict(int)
    course = defaultdict(int)
    rotation_per_cast = defaultdict(int)

    sums = defaultdict(int)
    sum_n_amount = 0
    sum_r_amount = 0

    for p in payloads:
        s = p.get("sales", {}) or {}
        cp = p.get("cast_payroll", {}) or {}
        for key in (
            "ticket_count", "guest_count", "n_count", "r_count",
            "total_amount", "extension_count",
            "drink_s_total", "drink_l_total", "drink_mg_total",
            "champagne_count", "champagne_amount",
            "set_count", "alcohol_expense", "other_expense",
            "cast_rotation_total",
        ):
            sums[key] += int(s.get(key) or 0)
        for k in ("base_pay_total", "incentive_total", "actual_pay_total"):
            sums[k] += int(cp.get(k) or 0)
        # 動機・時間帯・コース・キャスト別交代回数のマージ
        for k, v in (s.get("motivation") or {}).items():
            motivation[k] += int(v or 0)
        for k, v in (s.get("hourly_arrivals") or {}).items():
            hourly[k] += int(v or 0)
        for k, v in (s.get("course_counts") or {}).items():
            course[k] += int(v or 0)
        for k, v in (s.get("cast_rotation_per_cast") or {}).items():
            rotation_per_cast[k] += int(v or 0)
        # N/R 売上の按分は再計算が難しいので「avg_per_n × n_count」で逆算したいが、
        # ここでは「日報の avg_per_n × その日の n_count」を集計して総和を出す
        if s.get("avg_per_n") is not None and s.get("n_count"):
            sum_n_amount += int(s["avg_per_n"]) * int(s["n_count"])
        if s.get("avg_per_r") is not None and s.get("r_count"):
            sum_r_amount += int(s["avg_per_r"]) * int(s["r_count"])

    def _div(num, den):
        return int(num / den) if den else None

    ratio = None
    if sums["total_amount"] > 0:
        ratio = round(sums["actual_pay_total"] * 100 / sums["total_amount"], 1)

    return {
        **sums,
        "motivation": dict(motivation),
        "hourly_arrivals": dict(hourly),
        "course_counts": dict(course),
        "cast_rotation_per_cast": dict(rotation_per_cast),
        "ratio_percent": ratio,
        "avg_per_guest": _div(sums["total_amount"], sums["guest_count"]),
        "avg_per_n": _div(sum_n_amount, sums["n_count"]),
        "avg_per_r": _div(sum_r_amount, sums["r_count"]),
        "drink_s_per_set": round(sums["drink_s_total"] / sums["set_count"], 2) if sums["set_count"] else None,
        "drink_l_per_set": round(sums["drink_l_total"] / sums["set_count"], 2) if sums["set_count"] else None,
        "drink_mg_per_set": round(sums["drink_mg_total"] / sums["set_count"], 2) if sums["set_count"] else None,
    }


@router.get("/monthly")
def get_monthly(
    store_id: int = Query(...),
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """月報: 指定月の各日報スナップショット（最新版）を集計"""
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month は 1-12")
    start = date_cls(year, month, 1)
    if month == 12:
        end = date_cls(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date_cls(year, month + 1, 1) - timedelta(days=1)

    rows = db.query(models.DailyReportSnapshot).filter(
        models.DailyReportSnapshot.store_id == store_id,
        models.DailyReportSnapshot.business_date >= start,
        models.DailyReportSnapshot.business_date <= end,
    ).order_by(
        models.DailyReportSnapshot.business_date.asc(),
        models.DailyReportSnapshot.version.desc(),
    ).all()

    # 同じ日は最新版のみ
    by_date: dict = {}
    for r in rows:
        if r.business_date in by_date:
            continue
        by_date[r.business_date] = r

    payloads = [r.payload for r in by_date.values() if r.payload]
    summary = _aggregate_monthly(payloads)

    return {
        "store_id": store_id,
        "year": year,
        "month": month,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "report_days": len(payloads),
        "summary": summary,
        "daily_breakdown": [
            {
                "business_date": d.isoformat(),
                "snapshot_id": by_date[d].id,
                "version": by_date[d].version,
                "total_amount": (by_date[d].payload or {}).get("sales", {}).get("total_amount", 0),
                "guest_count": (by_date[d].payload or {}).get("sales", {}).get("guest_count", 0),
            }
            for d in sorted(by_date.keys())
        ],
    }
