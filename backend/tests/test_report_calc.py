"""
日報計算ロジックのテスト。
Phase C 仕様書 セクション11 の 3 パターン以上をカバー。
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
import pytest

from app.services.report_calc import (
    OrderInput, TicketInput, CastShiftInput, StaffAttendanceInput,
    work_hours, safe_div, jst_bar_hour,
    total_sales, total_extensions, total_n_guests, total_r_guests,
    total_ticket_count, total_guest_count, split_nr_sales,
    avg_per_guest, avg_per_n, avg_per_r,
    rotation_count_for_ticket, rotation_per_cast_for_ticket, rotation_summary,
    count_by_plan, count_by_motivation, hourly_arrivals,
    drink_total_by_type, champagne_groups, champagne_count_total, champagne_amount_total,
    total_set_count, drinks_per_set,
    applied_hourly_rate, cast_base_pay, total_cast_base_pay,
    cast_incentive_total_for, cast_payroll_summary,
    overlap_hours_22_26, cast_perf_22_26,
    cast_daily_pay, staff_daily_pay,
)


# ─────────────────────────────────────────
# ヘルパー
# ─────────────────────────────────────────

def jst(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute)


def make_order(
    id, item_type, cast_id=None, qty=1, unit_price=0,
    canceled=False, created_at=None, incentive_amount=0,
    cast_distribution=None, item_name=None,
    cast_required=False, has_incentive=False,
):
    return OrderInput(
        id=id,
        item_type=item_type,
        item_name=item_name,
        quantity=qty,
        unit_price=unit_price,
        cast_id=cast_id,
        canceled=canceled,
        created_at_jst=created_at or jst(2026, 4, 9, 20),
        incentive_amount=incentive_amount,
        cast_distribution=cast_distribution,
        cast_required=cast_required,
        has_incentive=has_incentive,
    )


def make_ticket(
    id, *,
    started_at=None, ended_at=None,
    guest_count=2, n_count=0, r_count=2,
    extension_count=0, plan_type="standard",
    visit_motivation=None, motivation_cast_id=None,
    customer_name=None, total_amount=0, orders=None,
    cash_amount=0, card_amount=0, code_amount=0, payment_method=None,
    table_no=None,
):
    return TicketInput(
        id=id,
        table_no=table_no,
        started_at_jst=started_at or jst(2026, 4, 9, 19, 30),
        ended_at_jst=ended_at,
        guest_count=guest_count,
        n_count=n_count,
        r_count=r_count,
        extension_count=extension_count,
        plan_type=plan_type,
        visit_motivation=visit_motivation,
        motivation_cast_id=motivation_cast_id,
        customer_name=customer_name,
        total_amount=total_amount,
        cash_amount=cash_amount,
        card_amount=card_amount,
        code_amount=code_amount,
        payment_method=payment_method,
        orders=orders or [],
    )


def make_shift(cast_id, name, start, end, hourly_rate=1400, is_help=False, help_rate=None, is_absent=False, is_late=False):
    return CastShiftInput(
        cast_id=cast_id,
        cast_name=name,
        is_help=is_help,
        help_from_store_name=None,
        actual_start_jst=start,
        actual_end_jst=end,
        is_late=is_late,
        is_absent=is_absent,
        hourly_rate=hourly_rate,
        help_hourly_rate=help_rate,
    )


# ─────────────────────────────────────────
# 基本ヘルパー関数
# ─────────────────────────────────────────

class TestWorkHours:
    def test_normal(self):
        assert work_hours(jst(2026, 4, 9, 19), jst(2026, 4, 10, 1)) == 6.0

    def test_30min_round_down(self):
        # 6h 29min → 6.0
        assert work_hours(jst(2026, 4, 9, 19), jst(2026, 4, 10, 1, 29)) == 6.0

    def test_30min_exact(self):
        assert work_hours(jst(2026, 4, 9, 19), jst(2026, 4, 10, 1, 30)) == 6.5

    def test_none(self):
        assert work_hours(None, None) == 0.0
        assert work_hours(jst(2026, 4, 9, 19), None) == 0.0


class TestSafeDiv:
    def test_normal(self):
        assert safe_div(10, 2) == 5.0

    def test_zero(self):
        assert safe_div(10, 0) is None


class TestJstBarHour:
    def test_evening(self):
        assert jst_bar_hour(jst(2026, 4, 9, 19, 30)) == 19

    def test_late_night(self):
        assert jst_bar_hour(jst(2026, 4, 10, 2, 0)) == 26

    def test_midnight(self):
        assert jst_bar_hour(jst(2026, 4, 10, 0, 0)) == 24


# ─────────────────────────────────────────
# 売上集計（Case A: 平均的な営業日）
# ─────────────────────────────────────────

class TestSalesCaseA:
    """3伝票・全伝票が純N or 純R"""
    @pytest.fixture
    def tickets(self):
        return [
            make_ticket(1, guest_count=2, n_count=2, r_count=0, total_amount=10000),
            make_ticket(2, guest_count=3, n_count=0, r_count=3, total_amount=20000),
            make_ticket(3, guest_count=1, n_count=0, r_count=1, total_amount=5000),
        ]

    def test_total_sales(self, tickets):
        assert total_sales(tickets) == 35000

    def test_total_n_r(self, tickets):
        assert total_n_guests(tickets) == 2
        assert total_r_guests(tickets) == 4

    def test_avg_per_guest(self, tickets):
        # 35000 / 6 = 5833.33 → 5833
        assert avg_per_guest(tickets) == 5833

    def test_avg_per_n(self, tickets):
        # N売上=10000 / N人数=2 = 5000
        assert avg_per_n(tickets) == 5000

    def test_avg_per_r(self, tickets):
        # R売上=25000 / R人数=4 = 6250
        assert avg_per_r(tickets) == 6250

    def test_ticket_count(self, tickets):
        assert total_ticket_count(tickets) == 3


# ─────────────────────────────────────────
# Case B: N/R混在 + 客単価按分
# ─────────────────────────────────────────

class TestSalesMixed:
    def test_split_n1_r2_30000(self):
        # 仕様書サンプル: N=1人, R=2人, ¥30,000伝票 → N按分¥10,000 / R按分¥20,000
        t = make_ticket(1, guest_count=3, n_count=1, r_count=2, total_amount=30000)
        n, r = split_nr_sales(t)
        assert n == 10000
        assert r == 20000

    def test_avg_mixed(self):
        tickets = [
            make_ticket(1, guest_count=3, n_count=1, r_count=2, total_amount=30000),
            make_ticket(2, guest_count=2, n_count=2, r_count=0, total_amount=10000),
        ]
        assert avg_per_n(tickets) == (10000 + 10000) // 3  # N総額÷N人数
        assert avg_per_r(tickets) == 20000 // 2

    def test_zero_division(self):
        # 全員 visit_type 未設定（n_count=0, r_count=0）→ N客単価 None
        tickets = [
            make_ticket(1, guest_count=2, n_count=0, r_count=0, total_amount=10000),
        ]
        assert avg_per_n(tickets) is None
        assert avg_per_r(tickets) is None
        assert avg_per_guest(tickets) == 5000


# ─────────────────────────────────────────
# 交代回数（Case C: 時刻順カウント）
# ─────────────────────────────────────────

class TestRotation:
    def test_rotation_basic(self):
        # あむ→あむ→かのん→あむ で2回
        orders = [
            make_order(1, "drink_l", cast_id=5, created_at=jst(2026, 4, 9, 19, 30), cast_required=True),
            make_order(2, "drink_l", cast_id=5, created_at=jst(2026, 4, 9, 19, 45), cast_required=True),
            make_order(3, "drink_l", cast_id=8, created_at=jst(2026, 4, 9, 20, 10), cast_required=True),
            make_order(4, "drink_l", cast_id=5, created_at=jst(2026, 4, 9, 20, 50), cast_required=True),
        ]
        t = make_ticket(1, orders=orders)
        assert rotation_count_for_ticket(t) == 2

    def test_rotation_per_cast(self):
        # 引き継がれた側にカウント: かのんが+1（あむから引き継ぎ）、あむが+1（かのんから引き継ぎ）
        orders = [
            make_order(1, "drink_l", cast_id=5, created_at=jst(2026, 4, 9, 19, 30), cast_required=True),
            make_order(2, "drink_l", cast_id=5, created_at=jst(2026, 4, 9, 19, 45), cast_required=True),
            make_order(3, "drink_l", cast_id=8, created_at=jst(2026, 4, 9, 20, 10), cast_required=True),
            make_order(4, "drink_l", cast_id=5, created_at=jst(2026, 4, 9, 20, 50), cast_required=True),
        ]
        t = make_ticket(1, orders=orders)
        per_cast = rotation_per_cast_for_ticket(t)
        assert per_cast == {8: 1, 5: 1}

    def test_rotation_canceled_excluded(self):
        # キャンセルされた行は除外
        orders = [
            make_order(1, "drink_l", cast_id=5, created_at=jst(2026, 4, 9, 19, 30), cast_required=True),
            make_order(2, "drink_l", cast_id=8, created_at=jst(2026, 4, 9, 19, 45), cast_required=True, canceled=True),
            make_order(3, "drink_l", cast_id=5, created_at=jst(2026, 4, 9, 20, 0), cast_required=True),
        ]
        t = make_ticket(1, orders=orders)
        # キャンセル除外で あむ→あむ → 0回
        assert rotation_count_for_ticket(t) == 0

    def test_rotation_summary(self):
        # 2卓分
        t1 = make_ticket(1, orders=[
            make_order(1, "drink_l", cast_id=5, created_at=jst(2026, 4, 9, 19), cast_required=True),
            make_order(2, "drink_l", cast_id=8, created_at=jst(2026, 4, 9, 20), cast_required=True),
        ])
        t2 = make_ticket(2, orders=[
            make_order(3, "drink_l", cast_id=8, created_at=jst(2026, 4, 9, 19), cast_required=True),
            make_order(4, "drink_l", cast_id=5, created_at=jst(2026, 4, 9, 20), cast_required=True),
            make_order(5, "drink_l", cast_id=8, created_at=jst(2026, 4, 9, 21), cast_required=True),
        ])
        s = rotation_summary([t1, t2])
        assert s["total"] == 1 + 2
        assert s["per_ticket"] == {1: 1, 2: 2}
        # 卓1: 8に+1、卓2: 5に+1, 8に+1
        assert s["per_cast"] == {8: 2, 5: 1}


# ─────────────────────────────────────────
# セット数とドリンク
# ─────────────────────────────────────────

class TestSetAndDrinks:
    def test_set_count(self):
        # 仕様書サンプル: 来店3人、延長合計9 → セット数12
        tickets = [
            make_ticket(1, guest_count=3, extension_count=9),
        ]
        assert total_set_count(tickets) == 12

    def test_drinks_per_set(self):
        # Sドリンク12本 / セット12 = 1.0
        orders = [make_order(i, "drink_s", qty=1) for i in range(12)]
        tickets = [make_ticket(1, guest_count=3, extension_count=9, orders=orders)]
        assert drinks_per_set(tickets, "drink_s") == 1.0

    def test_drinks_per_set_no_set(self):
        # セット数0だと None
        assert drinks_per_set([], "drink_s") is None


# ─────────────────────────────────────────
# キャスト人件費（ヘルプ時給含む）
# ─────────────────────────────────────────

class TestCastPayroll:
    def test_normal_hourly(self):
        s = make_shift(5, "あむ", jst(2026, 4, 9, 19), jst(2026, 4, 10, 1), hourly_rate=1400)
        assert applied_hourly_rate(s) == 1400
        assert cast_base_pay(s) == 6 * 1400

    def test_help_individual_rate(self):
        # 個別 help_hourly_rate がある
        s = make_shift(5, "あむ", jst(2026, 4, 9, 19), jst(2026, 4, 10, 1),
                       hourly_rate=1400, is_help=True, help_rate=1800)
        assert applied_hourly_rate(s) == 1800
        assert cast_base_pay(s) == 6 * 1800

    def test_help_fallback(self):
        # 個別 help_hourly_rate なし → hourly_rate + 100
        s = make_shift(5, "あむ", jst(2026, 4, 9, 19), jst(2026, 4, 10, 1),
                       hourly_rate=1400, is_help=True, help_rate=None)
        assert applied_hourly_rate(s) == 1500

    def test_absent(self):
        s = make_shift(5, "あむ", jst(2026, 4, 9, 19), jst(2026, 4, 10, 1), is_absent=True)
        assert cast_base_pay(s) == 0


# ─────────────────────────────────────────
# インセンティブ（シャンパン分配含む）
# ─────────────────────────────────────────

class TestIncentive:
    def test_nonchamp_only(self):
        # あむが Lドリンク2回受注、各 incentive_amount=400
        orders = [
            make_order(1, "drink_l", cast_id=5, incentive_amount=400),
            make_order(2, "drink_l", cast_id=5, incentive_amount=400),
        ]
        t = make_ticket(1, orders=orders)
        assert cast_incentive_total_for(5, [t]) == 800

    def test_canceled_excluded(self):
        orders = [
            make_order(1, "drink_l", cast_id=5, incentive_amount=400),
            make_order(2, "drink_l", cast_id=5, incentive_amount=400, canceled=True),
        ]
        t = make_ticket(1, orders=orders)
        assert cast_incentive_total_for(5, [t]) == 400

    def test_champagne_distribution(self):
        # シャンパン 1本 35000、率10% → back_pool 3500
        # 60/40 で あむ2100 / かのん1400
        orders = [
            make_order(1, "champagne", cast_id=5, qty=1, unit_price=35000,
                       item_name="ヴーヴ・クリコ",
                       incentive_amount=3500,
                       cast_distribution=[
                           {"cast_id": 5, "ratio": 60},
                           {"cast_id": 8, "ratio": 40},
                       ]),
            make_order(2, "champagne", cast_id=8, qty=1, unit_price=0,
                       item_name="ヴーヴ・クリコ",
                       incentive_amount=0,
                       cast_distribution=[
                           {"cast_id": 5, "ratio": 60},
                           {"cast_id": 8, "ratio": 40},
                       ]),
        ]
        t = make_ticket(1, orders=orders)
        assert cast_incentive_total_for(5, [t]) == 2100
        assert cast_incentive_total_for(8, [t]) == 1400

    def test_payroll_summary(self):
        shifts = [
            make_shift(5, "あむ", jst(2026, 4, 9, 19), jst(2026, 4, 10, 1), hourly_rate=1400),  # 6h × 1400 = 8400
        ]
        orders = [make_order(1, "drink_l", cast_id=5, incentive_amount=500)]
        tickets = [make_ticket(1, orders=orders, total_amount=10000)]
        s = cast_payroll_summary(shifts, tickets, daily_sales=10000)
        assert s["base_pay_total"] == 8400
        assert s["incentive_total"] == 500
        assert s["actual_pay_total"] == 8900
        # 8900 / 10000 * 100 = 89.0
        assert s["ratio_percent"] == 89.0


# ─────────────────────────────────────────
# 22-26時パフォーマンス
# ─────────────────────────────────────────

class TestPerf2226:
    def test_overlap_full(self):
        # 19:00-27:00 → 22-26時の4時間
        assert overlap_hours_22_26(jst(2026, 4, 9, 19), jst(2026, 4, 10, 3)) == 4.0

    def test_overlap_inner(self):
        # 23:00-25:00 → 2時間
        assert overlap_hours_22_26(jst(2026, 4, 9, 23), jst(2026, 4, 10, 1)) == 2.0

    def test_overlap_none(self):
        # 18:00-21:00 → 0
        assert overlap_hours_22_26(jst(2026, 4, 9, 18), jst(2026, 4, 9, 21)) == 0.0


# ─────────────────────────────────────────
# 日払い計算
# ─────────────────────────────────────────

class TestDailyPay:
    def test_cast_no_record(self):
        s = make_shift(5, "あむ", jst(2026, 4, 9, 19), jst(2026, 4, 10, 1))
        assert cast_daily_pay(s, has_payment_record=False) == 0

    def test_cast_with_record(self):
        # 6h × 1000 = 6000
        s = make_shift(5, "あむ", jst(2026, 4, 9, 19), jst(2026, 4, 10, 1))
        assert cast_daily_pay(s, has_payment_record=True) == 6000

    def test_staff_employee_fixed(self):
        att = StaffAttendanceInput(
            id=1, name="社員A", employee_type="staff",
            actual_start_jst=jst(2026, 4, 9, 19),
            actual_end_jst=jst(2026, 4, 10, 1),
            is_late=False, is_absent=False,
        )
        assert staff_daily_pay(att, has_payment_record=True) == 8000

    def test_staff_part_time(self):
        att = StaffAttendanceInput(
            id=1, name="バイトA", employee_type="part_time",
            actual_start_jst=jst(2026, 4, 9, 19),
            actual_end_jst=jst(2026, 4, 10, 1),
            is_late=False, is_absent=False,
        )
        # 6h × 1000 = 6000
        assert staff_daily_pay(att, has_payment_record=True) == 6000


# ─────────────────────────────────────────
# 来店動機・1時間ごと来店人数
# ─────────────────────────────────────────

class TestMotivationAndHourly:
    def test_count_by_motivation(self):
        tickets = [
            make_ticket(1, guest_count=2, visit_motivation="ティッシュ"),
            make_ticket(2, guest_count=3, visit_motivation="紹介"),
            make_ticket(3, guest_count=1, visit_motivation="ティッシュ"),
        ]
        result = count_by_motivation(tickets)
        assert result == {"ティッシュ": 3, "紹介": 3}

    def test_hourly_arrivals(self):
        tickets = [
            make_ticket(1, guest_count=2, started_at=jst(2026, 4, 9, 19, 30)),
            make_ticket(2, guest_count=3, started_at=jst(2026, 4, 9, 20, 15)),
            make_ticket(3, guest_count=1, started_at=jst(2026, 4, 10, 1, 0)),  # 25時
        ]
        result = hourly_arrivals(tickets)
        assert result == {19: 2, 20: 3, 25: 1}

    def test_count_by_plan(self):
        tickets = [
            make_ticket(1, guest_count=2, plan_type="standard"),
            make_ticket(2, guest_count=3, plan_type="premium"),
        ]
        result = count_by_plan(tickets)
        assert result == {"standard": 2, "premium": 3}
