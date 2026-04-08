"""
Phase A-2 移行スクリプト

目的:
1. 既存シャンパン注文の cast_distribution を埋める
   - item_name の "[X% ・ Y%]" をパースして cast_id ベースのJSONに変換
   - 同じ item_name でグループ化した複数行に同じJSONを設定（案X）
   - パース失敗グループは未分配のまま記録
2. 全 OrderItem の incentive_snapshot を埋める
   - 現行のメニューマスタ（IncentiveConfig）から計算して保存
   - キャンセル済み (canceled_at IS NOT NULL) はスキップ
   - cast_id IS NULL（インセンティブ対象外）はスキップ
3. StaffAttendance.employee_type を埋める
   - name で StaffMember を引いて employee_type をコピー
   - 一致しないものは「アルバイト」をデフォルトとして記録（後から手動修正可能）

使い方:
  # dry-run（変更せず集計のみ表示）
  python -m backend.scripts.migrate_champagne_and_incentive --dry-run

  # 本番実行
  python -m backend.scripts.migrate_champagne_and_incentive --apply
"""
import argparse
import re
import sys
from collections import defaultdict
from typing import List, Optional, Tuple

# プロジェクトルートを sys.path に追加
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.orm import Session
from backend.app.database import SessionLocal
from backend.app import models


# ─────────────────────────────────────────
# シャンパン分配パース
# ─────────────────────────────────────────

def parse_champagne_ratios(item_name: str) -> List[int]:
    """
    "クリスタル[すずな 60%・みお 40%]" → [60, 40]
    """
    if not item_name:
        return []
    match = re.search(r'[［\[](.+?)[］\]]', item_name)
    if not match:
        return []
    inner = match.group(1)
    parts = re.split(r'[・,、]', inner)
    ratios: List[int] = []
    for part in parts:
        m = re.search(r'(\d+)%', part)
        if m:
            ratios.append(int(m.group(1)))
        else:
            ratios.append(0)
    return ratios


def migrate_champagne(db: Session, dry_run: bool) -> dict:
    """
    シャンパンの cast_distribution を埋める。
    案X: 同一 ticket_id × 同一 item_name のグループに同じJSONを全行設定。
    """
    stats = {
        "groups_total": 0,
        "groups_success": 0,
        "groups_failed": 0,
        "groups_already_set": 0,
        "rows_updated": 0,
        "failures": [],  # [(ticket_id, item_name, reason), ...]
    }

    # ticket_id × item_name でグループ化
    rows = db.query(models.OrderItem).filter(
        models.OrderItem.item_type == "champagne",
        models.OrderItem.canceled_at.is_(None),
    ).order_by(models.OrderItem.ticket_id, models.OrderItem.item_name, models.OrderItem.id).all()

    groups: dict = defaultdict(list)
    for r in rows:
        key = (r.ticket_id, r.item_name or "")
        groups[key].append(r)

    for (ticket_id, item_name), items in groups.items():
        stats["groups_total"] += 1

        # 既に cast_distribution が設定されてればスキップ
        if any(i.cast_distribution for i in items):
            stats["groups_already_set"] += 1
            continue

        ratios = parse_champagne_ratios(item_name)
        items_sorted = sorted(items, key=lambda i: i.id)

        # パース失敗判定
        if not ratios:
            stats["groups_failed"] += 1
            stats["failures"].append((ticket_id, item_name, "no ratios parsed"))
            continue
        if len(ratios) != len(items_sorted):
            stats["groups_failed"] += 1
            stats["failures"].append((
                ticket_id, item_name,
                f"ratio count {len(ratios)} != item count {len(items_sorted)}"
            ))
            continue
        if any(i.cast_id is None for i in items_sorted):
            stats["groups_failed"] += 1
            stats["failures"].append((ticket_id, item_name, "cast_id is null"))
            continue

        # 分配JSON生成
        distribution = [
            {"cast_id": item.cast_id, "ratio": ratio}
            for item, ratio in zip(items_sorted, ratios)
        ]

        # 全行に同じJSONをセット（案X）
        if not dry_run:
            for item in items_sorted:
                item.cast_distribution = distribution
        stats["rows_updated"] += len(items_sorted)
        stats["groups_success"] += 1

    return stats


# ─────────────────────────────────────────
# インセンティブスナップショット
# ─────────────────────────────────────────

def build_incentive_map(db: Session, store_id: int) -> dict:
    """
    store_id の IncentiveConfig を辞書化:
    drink_type → ("percent"|"fixed", value)
    """
    configs = db.query(models.IncentiveConfig).filter(
        models.IncentiveConfig.store_id == store_id
    ).all()
    result = {}
    for c in configs:
        if c.incentive_mode == "fixed" and c.fixed_amount is not None:
            result[c.drink_type] = ("fixed", c.fixed_amount)
        else:
            result[c.drink_type] = ("percent", c.rate or 10)
    return result


def build_custom_menu_label_map(db: Session, store_id: int) -> dict:
    """
    store_id の MenuItemConfig (has_incentive=True) を:
    label → menu_id  の辞書として返す
    """
    rows = db.query(models.MenuItemConfig).filter(
        models.MenuItemConfig.store_id == store_id,
        models.MenuItemConfig.has_incentive == True,
        models.MenuItemConfig.is_active == True,
    ).all()
    return {m.label: m.id for m in rows}


def strip_cast_suffix(item_name: str) -> str:
    """'オリカクL[あむ]' → 'オリカクL'"""
    if not item_name:
        return ""
    return re.sub(r'[［\[].*?[］\]]\s*$', '', item_name).strip()


def resolve_drink_type(item: models.OrderItem, label_map: dict) -> Optional[str]:
    """
    OrderItem の item_type を IncentiveConfig.drink_type に解決。
    通常は item_type そのもの、custom_menu の場合は menu_{id} に変換。
    """
    if item.item_type != "custom_menu":
        return item.item_type
    label = strip_cast_suffix(item.item_name or "")
    menu_id = label_map.get(label)
    if menu_id is None:
        return None
    return f"menu_{menu_id}"


def calc_incentive_amount(
    item_type: str,
    unit_price: int,
    quantity: int,
    incentive_map: dict,
    cast_distribution: Optional[list] = None,
) -> Tuple[Optional[str], Optional[int], Optional[int], int]:
    """
    インセンティブ計算:
    return (mode, rate, fixed_amount, calculated_amount)

    シャンパンで cast_distribution がある場合、その行のキャストへの分配額を計算。
    （「その行が代表するキャストの取り分」を保存する）
    """
    cfg = incentive_map.get(item_type)
    if cfg is None:
        return (None, None, None, 0)

    mode, value = cfg

    if mode == "fixed":
        return ("fixed", None, value, value * quantity)

    # percent
    rate = value
    base_amount = int(unit_price * rate / 100) * quantity

    return ("percent", rate, None, base_amount)


def migrate_incentive_snapshots(db: Session, dry_run: bool) -> dict:
    stats = {
        "items_total": 0,
        "items_updated": 0,
        "items_skipped_no_cast": 0,
        "items_skipped_canceled": 0,
        "items_skipped_no_config": 0,
        "items_already_set": 0,
    }

    # 店舗ごとの incentive_map / label_map をキャッシュ
    incentive_maps: dict = {}
    label_maps: dict = {}

    def get_imap(store_id: int) -> dict:
        if store_id not in incentive_maps:
            incentive_maps[store_id] = build_incentive_map(db, store_id)
        return incentive_maps[store_id]

    def get_lmap(store_id: int) -> dict:
        if store_id not in label_maps:
            label_maps[store_id] = build_custom_menu_label_map(db, store_id)
        return label_maps[store_id]

    rows = db.query(models.OrderItem).join(models.Ticket).all()

    for item in rows:
        stats["items_total"] += 1

        if item.canceled_at is not None:
            stats["items_skipped_canceled"] += 1
            continue
        if item.cast_id is None:
            stats["items_skipped_no_cast"] += 1
            continue
        if item.incentive_snapshot:
            stats["items_already_set"] += 1
            continue

        store_id = item.ticket.store_id
        imap = get_imap(store_id)
        lmap = get_lmap(store_id)

        # custom_menu の場合は menu_{id} に解決
        drink_type = resolve_drink_type(item, lmap)
        if drink_type is None or drink_type not in imap:
            stats["items_skipped_no_config"] += 1
            continue

        mode, rate, fixed, amount = calc_incentive_amount(
            drink_type,
            item.unit_price or 0,
            item.quantity or 1,
            imap,
            item.cast_distribution,
        )

        snapshot = {
            "mode": mode,
            "rate": rate,
            "fixed_amount": fixed,
            "calculated_amount": amount,
        }

        if not dry_run:
            item.incentive_snapshot = snapshot
        stats["items_updated"] += 1

    return stats


# ─────────────────────────────────────────
# StaffAttendance.employee_type
# ─────────────────────────────────────────

def migrate_staff_employee_type(db: Session, dry_run: bool) -> dict:
    stats = {
        "records_total": 0,
        "records_matched": 0,
        "records_unmatched": 0,
        "records_already_set": 0,
        "records_deleted_legacy_help": 0,
        "unmatched_names": set(),
    }

    # name → employee_type のマップ作成（StaffMember から）
    members = db.query(models.StaffMember).all()
    name_to_type = {}
    for m in members:
        name_to_type[m.name] = m.employee_type

    records = db.query(models.StaffAttendance).all()

    for r in records:
        stats["records_total"] += 1

        # 古いヘルプキャスト残骸データ（[ヘルプ:○○] 形式）は削除
        if r.name and r.name.startswith("[ヘルプ:") and r.name.endswith("]"):
            if not dry_run:
                db.delete(r)
            stats["records_deleted_legacy_help"] += 1
            continue

        if r.employee_type:
            stats["records_already_set"] += 1
            continue

        emp_type = name_to_type.get(r.name)
        if emp_type:
            if not dry_run:
                r.employee_type = emp_type
            stats["records_matched"] += 1
        else:
            stats["records_unmatched"] += 1
            stats["unmatched_names"].add(r.name)

    return stats


# ─────────────────────────────────────────
# main
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="変更せず集計のみ表示")
    parser.add_argument("--apply", action="store_true", help="本番実行（DB書き込み）")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("エラー: --dry-run か --apply のどちらかを指定してください")
        sys.exit(1)

    if args.dry_run and args.apply:
        print("エラー: --dry-run と --apply は同時指定不可")
        sys.exit(1)

    dry_run = args.dry_run
    mode_label = "DRY RUN" if dry_run else "APPLY"

    print(f"=" * 60)
    print(f"Phase A-2 移行スクリプト [{mode_label}]")
    print(f"=" * 60)

    db = SessionLocal()
    try:
        # 1. シャンパン
        print("\n[1/3] シャンパン cast_distribution 移行")
        print("-" * 60)
        champ_stats = migrate_champagne(db, dry_run)
        print(f"  グループ総数:        {champ_stats['groups_total']}")
        print(f"  既設定スキップ:      {champ_stats['groups_already_set']}")
        print(f"  成功:                {champ_stats['groups_success']}")
        print(f"  失敗:                {champ_stats['groups_failed']}")
        print(f"  更新行数:            {champ_stats['rows_updated']}")
        if champ_stats["failures"]:
            print(f"\n  失敗グループ一覧（最大20件）:")
            for tid, name, reason in champ_stats["failures"][:20]:
                print(f"    ticket_id={tid} item_name={name!r} reason={reason}")
            if len(champ_stats["failures"]) > 20:
                print(f"    ...他 {len(champ_stats['failures']) - 20} 件")

        # 2. インセンティブスナップショット
        print("\n[2/3] OrderItem incentive_snapshot 移行")
        print("-" * 60)
        inc_stats = migrate_incentive_snapshots(db, dry_run)
        print(f"  全行数:              {inc_stats['items_total']}")
        print(f"  既設定スキップ:      {inc_stats['items_already_set']}")
        print(f"  更新:                {inc_stats['items_updated']}")
        print(f"  スキップ(キャスト無): {inc_stats['items_skipped_no_cast']}")
        print(f"  スキップ(キャンセル): {inc_stats['items_skipped_canceled']}")
        print(f"  スキップ(設定無):    {inc_stats['items_skipped_no_config']}")

        # 3. StaffAttendance employee_type
        print("\n[3/3] StaffAttendance employee_type 移行")
        print("-" * 60)
        staff_stats = migrate_staff_employee_type(db, dry_run)
        print(f"  全レコード:          {staff_stats['records_total']}")
        print(f"  既設定スキップ:      {staff_stats['records_already_set']}")
        print(f"  一致:                {staff_stats['records_matched']}")
        print(f"  不一致:              {staff_stats['records_unmatched']}")
        print(f"  ヘルプ残骸削除:      {staff_stats['records_deleted_legacy_help']}")
        if staff_stats["unmatched_names"]:
            print(f"\n  不一致の名前一覧:")
            for name in sorted(staff_stats["unmatched_names"]):
                print(f"    - {name!r}")

        # コミット or ロールバック
        if dry_run:
            db.rollback()
            print("\n[DRY RUN] 変更はDBに反映されていません")
        else:
            db.commit()
            print("\n[APPLY] DBに反映しました")

        print("\n完了")

    except Exception as e:
        db.rollback()
        print(f"\nエラーで中断: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
