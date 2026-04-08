"""
インセンティブ計算の共通ロジック。

注文時・編集時・日報集計時に同じ計算を使い回すための純関数群。
DB から取得した辞書を渡す形にして、テストしやすく・キャッシュ可能にしている。
"""
import re
from typing import Optional, Tuple, List, Dict
from sqlalchemy.orm import Session
from .. import models


# ─────────────────────────────────────────
# ルックアップマップ構築
# ─────────────────────────────────────────

def build_incentive_map(db: Session, store_id: int) -> Dict[str, Tuple[str, int]]:
    """
    store_id の IncentiveConfig を辞書化:
    drink_type → (mode, value)
        mode  = "percent" | "fixed"
        value = percentの場合は%、fixedの場合は円
    """
    configs = db.query(models.IncentiveConfig).filter(
        models.IncentiveConfig.store_id == store_id
    ).all()
    result: Dict[str, Tuple[str, int]] = {}
    for c in configs:
        if c.incentive_mode == "fixed" and c.fixed_amount is not None:
            result[c.drink_type] = ("fixed", c.fixed_amount)
        else:
            result[c.drink_type] = ("percent", c.rate or 10)
    return result


def build_custom_menu_label_map(db: Session, store_id: int) -> Dict[str, int]:
    """
    store_id の MenuItemConfig (has_incentive=True, is_active=True) を:
    label → menu_id  の辞書として返す
    """
    rows = db.query(models.MenuItemConfig).filter(
        models.MenuItemConfig.store_id == store_id,
        models.MenuItemConfig.has_incentive == True,
        models.MenuItemConfig.is_active == True,
    ).all()
    return {m.label: m.id for m in rows}


# ─────────────────────────────────────────
# item_type → drink_type 解決
# ─────────────────────────────────────────

_BRACKET_SUFFIX_RE = re.compile(r'[［\[].*?[］\]]\s*$')


def strip_cast_suffix(item_name: str) -> str:
    """'オリカクL[あむ]' → 'オリカクL'"""
    if not item_name:
        return ""
    return _BRACKET_SUFFIX_RE.sub('', item_name).strip()


def resolve_drink_type(
    item_type: str,
    item_name: Optional[str],
    label_map: Dict[str, int],
) -> Optional[str]:
    """
    OrderItem の item_type を IncentiveConfig.drink_type に解決。
    通常は item_type そのもの。custom_menu の場合は menu_{id} に変換。
    解決できない場合は None。
    """
    if item_type != "custom_menu":
        return item_type
    label = strip_cast_suffix(item_name or "")
    menu_id = label_map.get(label)
    if menu_id is None:
        return None
    return f"menu_{menu_id}"


# ─────────────────────────────────────────
# スナップショット計算
# ─────────────────────────────────────────

def calc_incentive_snapshot(
    item_type: str,
    item_name: Optional[str],
    unit_price: int,
    quantity: int,
    incentive_map: Dict[str, Tuple[str, int]],
    label_map: Dict[str, int],
) -> Optional[dict]:
    """
    1注文分のインセンティブスナップショットを計算して dict で返す。
    インセンティブ対象外（drink_type が解決不能 or マスタに無い）の場合は None。

    返り値の構造:
    {
        "mode": "percent" | "fixed",
        "rate": int | None,           # percentの場合のみ
        "fixed_amount": int | None,   # fixedの場合のみ
        "calculated_amount": int,     # 計算済み金額（円・キャスト1人分の総額）
    }

    シャンパンの分配は別のレイヤー（cast_distribution）で扱う。
    この関数は「キャスト1人分のインセンティブ総額」を返す。
    """
    drink_type = resolve_drink_type(item_type, item_name, label_map)
    if drink_type is None:
        return None
    cfg = incentive_map.get(drink_type)
    if cfg is None:
        return None

    mode, value = cfg
    if mode == "fixed":
        return {
            "mode": "fixed",
            "rate": None,
            "fixed_amount": value,
            "calculated_amount": value * quantity,
        }
    else:  # percent
        return {
            "mode": "percent",
            "rate": value,
            "fixed_amount": None,
            "calculated_amount": int(unit_price * value / 100) * quantity,
        }
