"""ティッシュ配り (TissueDistribution) API"""
from datetime import datetime, date as date_cls, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from .. import models
from ..auth import get_current_user


router = APIRouter(prefix="/api/tissue", tags=["tissue"])


def _to_dict(td: models.TissueDistribution) -> dict:
    return {
        "id": td.id,
        "store_id": td.store_id,
        "cast_id": td.cast_id,
        "cast_name": td.cast.stage_name if td.cast else None,
        "started_at": td.started_at.isoformat() if td.started_at else None,
        "ended_at": td.ended_at.isoformat() if td.ended_at else None,
        "count": td.count,
        "is_active": td.ended_at is None,
    }


def _end_active_assignments(db: Session, cast_id: int, ticket_id: Optional[int] = None) -> None:
    """そのキャストの active な CastAssignment を終了する（ティッシュ配り開始時）"""
    q = db.query(models.CastAssignment).filter(
        models.CastAssignment.cast_id == cast_id,
        models.CastAssignment.ended_at.is_(None),
    )
    if ticket_id is not None:
        q = q.filter(models.CastAssignment.ticket_id != ticket_id)
    now = datetime.utcnow()
    for a in q.all():
        a.ended_at = now


def end_active_tissue_for_cast(db: Session, cast_id: int) -> None:
    """そのキャストの active な ティッシュ配り を終了する。
    接客中設定やドリンク注文時に外部から呼ぶ。count は null のままで保存。"""
    actives = db.query(models.TissueDistribution).filter(
        models.TissueDistribution.cast_id == cast_id,
        models.TissueDistribution.ended_at.is_(None),
    ).all()
    now = datetime.utcnow()
    for td in actives:
        td.ended_at = now


@router.get("/active")
def list_active(
    store_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """配り中（ended_at IS NULL）の一覧"""
    rows = db.query(models.TissueDistribution).filter(
        models.TissueDistribution.store_id == store_id,
        models.TissueDistribution.ended_at.is_(None),
    ).order_by(models.TissueDistribution.started_at.asc()).all()
    return [_to_dict(r) for r in rows]


class StartRequest(BaseModel):
    store_id: int
    cast_ids: List[int]


@router.post("/start")
def start_distribution(
    data: StartRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指定キャストをティッシュ配り中にする。
    - 既に active がある cast はスキップ（1キャスト1 active ルール）
    - 開始時にそのキャストの CastAssignment(active) は終了
    """
    cast_ids = list(dict.fromkeys(data.cast_ids))
    started = []
    skipped = []

    # 既存の active を持っているキャストを除外
    existing = db.query(models.TissueDistribution).filter(
        models.TissueDistribution.cast_id.in_(cast_ids),
        models.TissueDistribution.ended_at.is_(None),
    ).all()
    busy_cast_ids = {x.cast_id for x in existing}

    now = datetime.utcnow()
    for cid in cast_ids:
        if cid in busy_cast_ids:
            skipped.append(cid)
            continue
        # CastAssignment を終了
        for a in db.query(models.CastAssignment).filter(
            models.CastAssignment.cast_id == cid,
            models.CastAssignment.ended_at.is_(None),
        ).all():
            a.ended_at = now
        td = models.TissueDistribution(
            store_id=data.store_id,
            cast_id=cid,
            started_at=now,
            created_by=current_user.id,
        )
        db.add(td)
        started.append(cid)

    db.commit()
    return {"started": started, "skipped": skipped}


class CompleteRequest(BaseModel):
    count: int


@router.post("/{td_id}/complete")
def complete_distribution(
    td_id: int,
    data: CompleteRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """枚数を入力して配り終了"""
    td = db.query(models.TissueDistribution).filter(
        models.TissueDistribution.id == td_id
    ).first()
    if not td:
        raise HTTPException(status_code=404, detail="記録が見つかりません")
    if data.count < 0:
        raise HTTPException(status_code=400, detail="枚数は0以上にしてください")
    if td.ended_at is None:
        td.ended_at = datetime.utcnow()
    td.count = data.count
    db.commit()
    return _to_dict(td)


@router.delete("/{td_id}")
def cancel_distribution(
    td_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """配り中を取り消し（行ごと削除）"""
    td = db.query(models.TissueDistribution).filter(
        models.TissueDistribution.id == td_id
    ).first()
    if not td:
        raise HTTPException(status_code=404, detail="記録が見つかりません")
    db.delete(td)
    db.commit()
    return {"ok": True}


class UpdateCountRequest(BaseModel):
    count: Optional[int] = None


@router.patch("/{td_id}")
def update_distribution(
    td_id: int,
    data: UpdateCountRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """枚数の後編集（日報UI用）"""
    td = db.query(models.TissueDistribution).filter(
        models.TissueDistribution.id == td_id
    ).first()
    if not td:
        raise HTTPException(status_code=404, detail="記録が見つかりません")
    if data.count is not None and data.count < 0:
        raise HTTPException(status_code=400, detail="枚数は0以上にしてください")
    td.count = data.count
    db.commit()
    return _to_dict(td)
