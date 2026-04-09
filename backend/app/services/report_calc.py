"""
日報計算の純関数群（DB非依存）。

全関数は以下の方針:
- 入力: dataclass または dict / list（DB モデルに依存しない）
- 出力: int / float / dict / list
- 副作用なし、テスタブル
- 端数処理は仕様書 13 章に従う

呼び出し側（report_builder）が DB から ORM オブジェクトを取得して
このモジュールが扱える形に変換してから呼ぶ。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, time
from typing import Optional, List, Dict, Tuple
import math


# ─────────────────────────────────────────
# 入力データ構造
# ─────────────────────────────────────────

@dataclass
class OrderInput:
    """OrderItem の集計用ビュー（不要フィールド削ってある）"""
    id: int
    item_type: str
    item_name: Optional[str]
    quantity: int
    unit_price: int
    cast_id: Optional[int]
    canceled: bool
    created_at_jst: datetime  # JST に変換済みの naive datetime
    incentive_amount: int  # incentive_snapshot.calculated_amount（無ければ 0）
    cast_distribution: Optional[List[Dict]] = None  # [{"cast_id": int, "ratio": int}]
    cast_required: bool = False  # メニュー設定: キャスト選択必要か
    has_incentive: bool = False  # メニュー設定: インセンティブあり


@dataclass
class TicketInput:
    """Ticket の集計用ビュー"""
    id: int
    table_no: Optional[str]
    started_at_jst: datetime
    ended_at_jst: Optional[datetime]
    guest_count: int
    n_count: int
    r_count: int
    extension_count: int
    plan_type: Optional[str]   # "standard" | "premium"
    visit_motivation: Optional[str]
    motivation_cast_id: Optional[int]
    customer_name: Optional[str]
    total_amount: int
    cash_amount: int
    card_amount: int
    code_amount: int
    payment_method: Optional[str]
    orders: List[OrderInput] = field(default_factory=list)


@dataclass
class CastShiftInput:
    """ConfirmedShift の集計用ビュー"""
    cast_id: Optional[int]
    cast_name: str
    is_help: bool
    help_from_store_name: Optional[str]
    actual_start_jst: Optional[datetime]
    actual_end_jst: Optional[datetime]
    is_late: bool
    is_absent: bool
    hourly_rate: int
    help_hourly_rate: Optional[int]  # None なら fallback で hourly_rate+100


@dataclass
class StaffAttendanceInput:
    """StaffAttendance の集計用ビュー"""
    id: int
    name: str
    employee_type: Optional[str]   # "staff" | "part_time" | None
    actual_start_jst: Optional[datetime]
    actual_end_jst: Optional[datetime]
    is_late: bool
    is_absent: bool


# ─────────────────────────────────────────
# 基本ヘルパー
# ─────────────────────────────────────────

def work_hours(start: Optional[datetime], end: Optional[datetime]) -> float:
    """労働時間（30分単位切り捨て）。当欠/未退勤は0."""
    if start is None or end is None:
        return 0.0
    if end <= start:
        return 0.0
    seconds = (end - start).total_seconds()
    hours = seconds / 3600
    return math.floor(hours * 2) / 2


def safe_div(num: float, den: float) -> Optional[float]:
    """ゼロ除算回避: 分母0なら None"""
    if den == 0:
        return None
    return num / den


def jst_bar_hour(dt: datetime) -> int:
    """JST datetime を バー営業時間表記の時 (19, 20, ..., 28, 29) に変換"""
    h = dt.hour
    return h + 24 if h < 12 else h


# ─────────────────────────────────────────
# 売上集計（セクション3）
# ─────────────────────────────────────────

def total_sales(tickets: List[TicketInput]) -> int:
    """3.1 全伝票の会計金額合計"""
    return sum(t.total_amount for t in tickets)


def total_extensions(tickets: List[TicketInput]) -> int:
    """3.2 合計延長回数"""
    return sum(t.extension_count for t in tickets)


def total_n_guests(tickets: List[TicketInput]) -> int:
    """3.3 N合計数"""
    return sum(t.n_count for t in tickets)


def total_r_guests(tickets: List[TicketInput]) -> int:
    """3.3 R合計数"""
    return sum(t.r_count for t in tickets)


def total_ticket_count(tickets: List[TicketInput]) -> int:
    """3.4 合計伝票枚数"""
    return len(tickets)


def total_guest_count(tickets: List[TicketInput]) -> int:
    """3.5 合計来店数"""
    return sum(t.guest_count for t in tickets)


def split_nr_sales(t: TicketInput) -> Tuple[int, int]:
    """1伝票を N人数比で按分し (n_share, r_share) を返す"""
    if t.guest_count <= 0:
        return (0, 0)
    if t.n_count == 0 and t.r_count == 0:
        return (0, 0)
    n_share = t.total_amount * t.n_count // t.guest_count
    r_share = t.total_amount - n_share if t.r_count > 0 else 0
    if t.n_count == 0:
        r_share = t.total_amount
        n_share = 0
    return (n_share, r_share)


def avg_per_guest(tickets: List[TicketInput]) -> Optional[int]:
    """3.6 客単価（円未満切り捨て）"""
    total = total_sales(tickets)
    guests = total_guest_count(tickets)
    res = safe_div(total, guests)
    return int(res) if res is not None else None


def avg_per_n(tickets: List[TicketInput]) -> Optional[int]:
    """3.6 N客単価"""
    n_total = sum(split_nr_sales(t)[0] for t in tickets)
    n_count = total_n_guests(tickets)
    res = safe_div(n_total, n_count)
    return int(res) if res is not None else None


def avg_per_r(tickets: List[TicketInput]) -> Optional[int]:
    """3.6 R客単価"""
    r_total = sum(split_nr_sales(t)[1] for t in tickets)
    r_count = total_r_guests(tickets)
    res = safe_div(r_total, r_count)
    return int(res) if res is not None else None


# ─────────────────────────────────────────
# キャスト紹介人数（交代回数）セクション3.7
# ─────────────────────────────────────────

def rotation_count_for_ticket(t: TicketInput) -> int:
    """卓1つの交代回数: キャスト選択ありの注文を時刻順に並べ、隣接で cast_id が違う回数"""
    items = sorted(
        (o for o in t.orders if o.cast_id is not None and not o.canceled and o.cast_required),
        key=lambda o: (o.created_at_jst, o.id),
    )
    if len(items) < 2:
        return 0
    count = 0
    for i in range(len(items) - 1):
        if items[i].cast_id != items[i + 1].cast_id:
            count += 1
    return count


def rotation_per_cast_for_ticket(t: TicketInput) -> Dict[int, int]:
    """卓1つの「引き継がれた」キャスト別カウント。
    'あむ→かのん' で かのん側に +1（引き継がれた側）"""
    items = sorted(
        (o for o in t.orders if o.cast_id is not None and not o.canceled and o.cast_required),
        key=lambda o: (o.created_at_jst, o.id),
    )
    result: Dict[int, int] = {}
    for i in range(1, len(items)):
        if items[i].cast_id != items[i - 1].cast_id:
            result[items[i].cast_id] = result.get(items[i].cast_id, 0) + 1
    return result


def rotation_summary(tickets: List[TicketInput]) -> dict:
    """全店分の交代回数: 合計・卓単位・キャスト単位"""
    per_ticket: Dict[int, int] = {}
    per_cast: Dict[int, int] = {}
    for t in tickets:
        c = rotation_count_for_ticket(t)
        if c > 0:
            per_ticket[t.id] = c
        for cid, n in rotation_per_cast_for_ticket(t).items():
            per_cast[cid] = per_cast.get(cid, 0) + n
    total = sum(per_ticket.values())
    return {
        "total": total,
        "per_ticket": per_ticket,
        "per_cast": per_cast,
    }


# ─────────────────────────────────────────
# コース別人数（3.8）
# ─────────────────────────────────────────

def count_by_plan(tickets: List[TicketInput]) -> Dict[str, int]:
    """コース別の合計来店人数"""
    result: Dict[str, int] = {}
    for t in tickets:
        key = t.plan_type or "unknown"
        result[key] = result.get(key, 0) + t.guest_count
    return result


# ─────────────────────────────────────────
# 来店動機別（3.9）
# ─────────────────────────────────────────

def count_by_motivation(tickets: List[TicketInput]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for t in tickets:
        key = t.visit_motivation or "未設定"
        result[key] = result.get(key, 0) + t.guest_count
    return result


# ─────────────────────────────────────────
# 1時間ごと時間帯別来店人数（3.10）
# ─────────────────────────────────────────

def hourly_arrivals(tickets: List[TicketInput]) -> Dict[int, int]:
    """入店時間（JST）の時を起点に集計。バー表記（19..29）"""
    result: Dict[int, int] = {}
    for t in tickets:
        h = jst_bar_hour(t.started_at_jst)
        result[h] = result.get(h, 0) + t.guest_count
    return result


# ─────────────────────────────────────────
# ドリンク・シャンパン集計
# ─────────────────────────────────────────

def drink_total_by_type(tickets: List[TicketInput], item_type: str) -> int:
    """指定 item_type の合計数量（キャンセル除外）"""
    return sum(
        o.quantity
        for t in tickets
        for o in t.orders
        if not o.canceled and o.item_type == item_type
    )


def champagne_groups(t: TicketInput) -> List[List[OrderInput]]:
    """同一 item_name のシャンパンをグループ化"""
    groups: Dict[str, List[OrderInput]] = {}
    for o in t.orders:
        if o.canceled or o.item_type != "champagne":
            continue
        groups.setdefault(o.item_name or "", []).append(o)
    return list(groups.values())


def champagne_count_total(tickets: List[TicketInput]) -> int:
    """シャンパン売上「本数」（同一グループは1本としてカウント）"""
    return sum(len(champagne_groups(t)) for t in tickets)


def champagne_amount_total(tickets: List[TicketInput]) -> int:
    """シャンパン売上合計金額（代表行 unit_price * quantity）"""
    total = 0
    for t in tickets:
        for group in champagne_groups(t):
            for o in group:
                if o.unit_price > 0:
                    total += o.unit_price * o.quantity
    return total


# ─────────────────────────────────────────
# セット数 と 1セットあたりドリンク
# ─────────────────────────────────────────

def total_set_count(tickets: List[TicketInput]) -> int:
    """セット数 = 来店人数合計 + 延長合計数"""
    return total_guest_count(tickets) + total_extensions(tickets)


def drinks_per_set(tickets: List[TicketInput], item_type: str) -> Optional[float]:
    """1セットあたりドリンク数（小数第2位まで保持）"""
    sets = total_set_count(tickets)
    qty = drink_total_by_type(tickets, item_type)
    res = safe_div(qty, sets)
    return round(res, 2) if res is not None else None


# ─────────────────────────────────────────
# キャスト人件費（セクション5）
# ─────────────────────────────────────────

def applied_hourly_rate(shift: CastShiftInput) -> int:
    """ヘルプ時給ルール適用後の時給"""
    if not shift.is_help:
        return shift.hourly_rate
    if shift.help_hourly_rate is not None:
        return shift.help_hourly_rate
    return shift.hourly_rate + 100


def cast_base_pay(shift: CastShiftInput) -> int:
    """1キャストの基本給"""
    if shift.is_absent:
        return 0
    hours = work_hours(shift.actual_start_jst, shift.actual_end_jst)
    rate = applied_hourly_rate(shift)
    return int(hours * rate)


def total_cast_base_pay(shifts: List[CastShiftInput]) -> int:
    return sum(cast_base_pay(s) for s in shifts)


def cast_incentive_total_for(
    cast_id: int,
    tickets: List[TicketInput],
) -> int:
    """1キャストのインセンティブ合計（非シャンパン + シャンパン分配）"""
    total = 0
    for t in tickets:
        # 非シャンパン: そのキャストが受けた order の incentive_amount を合算
        for o in t.orders:
            if o.canceled or o.item_type == "champagne":
                continue
            if o.cast_id == cast_id:
                total += o.incentive_amount

        # シャンパン: 同一グループの代表行から back_pool を取って按分
        for group in champagne_groups(t):
            dist_holder = next(
                (o for o in group if o.cast_distribution),
                None,
            )
            if dist_holder is None:
                continue
            back_pool = dist_holder.incentive_amount
            for entry in dist_holder.cast_distribution:
                if entry.get("cast_id") == cast_id:
                    ratio = entry.get("ratio", 0)
                    total += int(back_pool * ratio / 100)
    return total


def total_cast_incentive(cast_ids: List[int], tickets: List[TicketInput]) -> int:
    return sum(cast_incentive_total_for(cid, tickets) for cid in cast_ids)


def cast_payroll_summary(
    shifts: List[CastShiftInput],
    tickets: List[TicketInput],
    daily_sales: int,
) -> dict:
    """キャスト人件費サマリ（5.1〜5.4）"""
    base = total_cast_base_pay(shifts)
    cast_ids = [s.cast_id for s in shifts if s.cast_id is not None]
    incentive = total_cast_incentive(cast_ids, tickets)
    actual = base + incentive
    ratio = safe_div(actual * 100, daily_sales)
    return {
        "base_pay_total": base,
        "incentive_total": incentive,
        "actual_pay_total": actual,
        "ratio_percent": round(ratio, 1) if ratio is not None else None,
    }


# ─────────────────────────────────────────
# 22-26時パフォーマンス（セクション8）
# ─────────────────────────────────────────

def overlap_hours_22_26(start: Optional[datetime], end: Optional[datetime]) -> float:
    """勤務時間と 22:00-26:00 (=翌2:00) の重なり時間（30分単位切り捨て）"""
    if start is None or end is None:
        return 0.0
    if end <= start:
        return 0.0
    # 22:00 はその日の 22:00、26:00 は翌日 02:00
    base_date = start.date()
    window_start = datetime.combine(base_date, time(22, 0))
    # start が 22時より前なら 22 起点、22時以降なら start 起点
    if start.hour < 22 and start.date() == base_date:
        # start が同じ日の昼間（19:00 等）→ window_start は同日 22:00
        ws = window_start
    else:
        ws = max(start, window_start)
    # 26:00 = 翌日 02:00
    window_end = datetime.combine(base_date + timedelta(days=1), time(2, 0))
    we = min(end, window_end)
    if we <= ws:
        return 0.0
    seconds = (we - ws).total_seconds()
    hours = seconds / 3600
    return math.floor(hours * 2) / 2


def cast_perf_22_26(
    cast_id: int,
    shift: CastShiftInput,
    tickets: List[TicketInput],
) -> Optional[float]:
    """22-26時帯の1時間あたりパフォーマンス"""
    denom = overlap_hours_22_26(shift.actual_start_jst, shift.actual_end_jst)
    if denom == 0:
        return None
    # 分子: そのキャストが受けたインセンティブ対象注文のうち 22-26時帯に created_at が入るもの
    numer = 0
    for t in tickets:
        for o in t.orders:
            if o.canceled or o.cast_id != cast_id:
                continue
            if not (o.cast_required and o.has_incentive):
                continue
            h = o.created_at_jst.hour
            # 22-26時 = 22 <= h < 26 (バー表記)
            if 22 <= h or h < 2:
                numer += o.incentive_amount
    return round(numer / denom, 0)


# ─────────────────────────────────────────
# 日払い計算
# ─────────────────────────────────────────

def cast_daily_pay(shift: CastShiftInput, has_payment_record: bool) -> int:
    """キャスト/アルバイト日払い: 労働時間 × 1000円。出金記録がある場合のみ"""
    if not has_payment_record:
        return 0
    if shift.is_absent:
        return 0
    hours = work_hours(shift.actual_start_jst, shift.actual_end_jst)
    return int(hours * 1000)


def staff_daily_pay(att: StaffAttendanceInput, has_payment_record: bool) -> int:
    """社員/アルバイト日払い:
    - 社員 (employee_type='staff'): 8000円固定
    - アルバイト (employee_type='part_time'): 労働時間 × 1000
    出金記録がある場合のみ。"""
    if not has_payment_record:
        return 0
    if att.is_absent:
        return 0
    if att.employee_type == "staff":
        return 8000
    # part_time or unknown
    hours = work_hours(att.actual_start_jst, att.actual_end_jst)
    return int(hours * 1000)
