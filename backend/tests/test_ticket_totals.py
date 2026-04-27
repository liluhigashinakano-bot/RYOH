"""
伝票金額計算（total_amount / extension_count）の整合性テスト。
_sync_ticket_totals による再計算が様々な操作パターンで正しく機能することを検証する。
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models
from app.routers.tickets import _sync_ticket_totals


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    store = models.Store(name="テスト店舗", code="TEST")
    session.add(store)
    session.flush()
    yield session, store.id
    session.close()


def _make_ticket(db, store_id, guest_count=2, plan_type="standard"):
    ticket = models.Ticket(
        store_id=store_id,
        guest_count=guest_count,
        plan_type=plan_type,
        total_amount=0,
        extension_count=0,
    )
    db.add(ticket)
    db.flush()
    return ticket


def _add_item(db, ticket, item_type, item_name, quantity, unit_price, **kwargs):
    item = models.OrderItem(
        ticket_id=ticket.id,
        item_type=item_type,
        item_name=item_name,
        quantity=quantity,
        unit_price=unit_price,
        amount=unit_price * quantity,
        **kwargs,
    )
    db.add(item)
    db.flush()
    return item


# ─────────────────────────────────────────
# 基本: _sync_ticket_totals
# ─────────────────────────────────────────

class TestSyncTicketTotals:
    def test_empty_ticket(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 0
        assert ticket.extension_count == 0

    def test_single_order(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5000

    def test_multiple_orders(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)
        _add_item(session, ticket, "drink_l", "Lドリンク", 3, 1700)
        _add_item(session, ticket, "extension", "延長", 2, 3000)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5000 + 5100 + 6000  # 16100
        assert ticket.extension_count == 1

    def test_cancelled_orders_excluded(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)
        cancelled = _add_item(session, ticket, "drink_l", "Lドリンク", 2, 1700)
        cancelled.canceled_at = datetime.utcnow()
        session.flush()
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5000

    def test_with_discount(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)
        ticket.discount_amount = 100
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 4900

    def test_discount_does_not_go_negative(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 1, 100)
        ticket.discount_amount = 500
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 0

    def test_negative_items_included(self, db):
        """値引きや分割清算の負額アイテムが正しく含まれる"""
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)
        _add_item(session, ticket, "other", "値引き（端数カット）担当:星", 1, -36)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5000 - 36  # 4964


# ─────────────────────────────────────────
# 延長 (extension) 関連
# ─────────────────────────────────────────

class TestExtensions:
    def test_extension_count_single(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id, guest_count=2)
        _add_item(session, ticket, "extension", "延長", 2, 3000)
        _sync_ticket_totals(ticket, session)
        assert ticket.extension_count == 1
        assert ticket.total_amount == 6000

    def test_extension_count_multiple_periods(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id, guest_count=2)
        _add_item(session, ticket, "extension", "延長", 2, 3000)
        _add_item(session, ticket, "extension", "延長", 2, 3000)
        _add_item(session, ticket, "extension", "延長", 2, 3000)
        _sync_ticket_totals(ticket, session)
        assert ticket.extension_count == 3
        assert ticket.total_amount == 18000

    def test_extension_cancel_reduces_count(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id, guest_count=2)
        ext1 = _add_item(session, ticket, "extension", "延長", 2, 3000)
        _add_item(session, ticket, "extension", "延長", 2, 3000)
        ext1.canceled_at = datetime.utcnow()
        session.flush()
        _sync_ticket_totals(ticket, session)
        assert ticket.extension_count == 1
        assert ticket.total_amount == 6000

    def test_extension_premium(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id, guest_count=2, plan_type="premium")
        _add_item(session, ticket, "extension_prem", "延長プレミアム", 2, 4000)
        _sync_ticket_totals(ticket, session)
        assert ticket.extension_count == 1
        assert ticket.total_amount == 8000

    def test_mixed_extension_types(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id, guest_count=2)
        _add_item(session, ticket, "extension", "延長", 2, 3000)
        _add_item(session, ticket, "extension_prem", "延長プレミアム", 2, 4000)
        _sync_ticket_totals(ticket, session)
        assert ticket.extension_count == 2
        assert ticket.total_amount == 6000 + 8000

    def test_extension_with_other_orders(self, db):
        """スクリーンショットの再現ケース: セット + ドリンク + 延長 + 値引き"""
        session, store_id = db
        ticket = _make_ticket(session, store_id, guest_count=2)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)       # 5000
        _add_item(session, ticket, "extension", "延長", 2, 3000)       # 6000
        _add_item(session, ticket, "drink_l", "Lドリンク", 2, 1700)    # 3400
        _add_item(session, ticket, "drink_l", "Lドリンク", 4, 1700)    # 6800
        _add_item(session, ticket, "drink_l", "Lドリンク", 2, 1700)    # 3400
        _add_item(session, ticket, "other", "値引き（端数カット）担当:星", 1, -36)  # -36
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5000 + 6000 + 3400 + 6800 + 3400 - 36  # 24564
        assert ticket.extension_count == 1

    def test_extension_add_then_cancel_net_zero(self, db):
        """延長追加→キャンセルで元に戻る"""
        session, store_id = db
        ticket = _make_ticket(session, store_id, guest_count=2)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)  # 5000
        ext = _add_item(session, ticket, "extension", "延長", 2, 3000)  # 6000
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 11000
        assert ticket.extension_count == 1

        ext.canceled_at = datetime.utcnow()
        session.flush()
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5000
        assert ticket.extension_count == 0


# ─────────────────────────────────────────
# 数量変更
# ─────────────────────────────────────────

class TestQuantityUpdate:
    def test_increase_quantity(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        item = _add_item(session, ticket, "drink_l", "Lドリンク", 2, 1700)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 3400

        item.quantity = 4
        item.amount = item.unit_price * 4
        session.flush()
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 6800

    def test_decrease_quantity(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        item = _add_item(session, ticket, "drink_l", "Lドリンク", 4, 1700)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 6800

        item.quantity = 1
        item.amount = item.unit_price * 1
        session.flush()
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 1700


# ─────────────────────────────────────────
# グループ数量削減（reduce_group_quantity 相当）
# ─────────────────────────────────────────

class TestReduceGroupQuantity:
    def test_cancel_whole_item(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id, guest_count=2)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)
        ext1 = _add_item(session, ticket, "extension", "延長", 2, 3000)
        _add_item(session, ticket, "extension", "延長", 2, 3000)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5000 + 6000 + 6000
        assert ticket.extension_count == 2

        ext1.canceled_at = datetime.utcnow()
        session.flush()
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5000 + 6000
        assert ticket.extension_count == 1

    def test_partial_quantity_reduce(self, db):
        """アイテムの数量を部分的に減らす"""
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        item = _add_item(session, ticket, "drink_l", "Lドリンク", 5, 1700)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 8500

        item.quantity = 3
        item.amount = 1700 * 3
        session.flush()
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5100

    def test_extension_cancel_does_not_subtract_guest_count_from_extension_count(self, db):
        """旧バグの再現テスト: 延長キャンセル時に extension_count から
        item.quantity（=ゲスト数）を引いていたバグが修正されていること"""
        session, store_id = db
        ticket = _make_ticket(session, store_id, guest_count=3)
        _add_item(session, ticket, "extension", "延長", 3, 3000)  # period 1
        ext2 = _add_item(session, ticket, "extension", "延長", 3, 3000)  # period 2
        _add_item(session, ticket, "extension", "延長", 3, 3000)  # period 3
        _sync_ticket_totals(ticket, session)
        assert ticket.extension_count == 3

        ext2.canceled_at = datetime.utcnow()
        session.flush()
        _sync_ticket_totals(ticket, session)
        assert ticket.extension_count == 2  # 旧バグでは 3 - 3(quantity) = 0 になっていた
        assert ticket.total_amount == 9000 + 9000  # 2期分


# ─────────────────────────────────────────
# 会計 (close) + 値引き
# ─────────────────────────────────────────

class TestCloseTicket:
    def test_close_with_discount(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)
        _add_item(session, ticket, "drink_l", "Lドリンク", 4, 1700)
        ticket.is_closed = True
        ticket.discount_amount = 200
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5000 + 6800 - 200  # 11600

    def test_close_with_zero_discount(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)
        ticket.is_closed = True
        ticket.discount_amount = 0
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5000


# ─────────────────────────────────────────
# 会計後値引き・加算 (post_discount)
# ─────────────────────────────────────────

class TestPostDiscount:
    def test_post_close_discount(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)
        ticket.is_closed = True
        ticket.discount_amount = 0
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5000

        _add_item(session, ticket, "other", "値引き（端数カット）担当:星", 1, -100)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 4900

    def test_post_close_addition(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)
        ticket.is_closed = True
        ticket.discount_amount = 0
        _sync_ticket_totals(ticket, session)

        _add_item(session, ticket, "other", "加算（追加注文）担当:星", 1, 500)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 5500


# ─────────────────────────────────────────
# 合算・合算解除 (merge / unmerge)
# ─────────────────────────────────────────

class TestMergeUnmerge:
    def test_merge_totals(self, db):
        session, store_id = db
        t1 = _make_ticket(session, store_id)
        t2 = _make_ticket(session, store_id)
        _add_item(session, t1, "set", "セット料金", 2, 2500)
        item_to_move = _add_item(session, t2, "drink_l", "Lドリンク", 3, 1700)

        item_to_move.ticket_id = t1.id
        item_to_move.original_ticket_id = t2.id
        session.flush()

        _sync_ticket_totals(t1, session)
        assert t1.total_amount == 5000 + 5100  # 10100

        t2.total_amount = 0
        t2.is_closed = True
        _sync_ticket_totals(t2, session)
        assert t2.total_amount == 0

    def test_unmerge_totals(self, db):
        session, store_id = db
        t1 = _make_ticket(session, store_id)
        t2 = _make_ticket(session, store_id)
        _add_item(session, t1, "set", "セット料金", 2, 2500)
        moved = _add_item(session, t2, "drink_l", "Lドリンク", 3, 1700)

        moved.ticket_id = t1.id
        moved.original_ticket_id = t2.id
        session.flush()
        _sync_ticket_totals(t1, session)
        assert t1.total_amount == 10100

        moved.ticket_id = t2.id
        moved.original_ticket_id = None
        t2.is_closed = False
        t2.discount_amount = 0
        session.flush()

        _sync_ticket_totals(t1, session)
        _sync_ticket_totals(t2, session)
        assert t1.total_amount == 5000
        assert t2.total_amount == 5100


# ─────────────────────────────────────────
# 割り勘 (warikan)
# ─────────────────────────────────────────

class TestWarikan:
    def test_split_payment_reduces_total(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)  # 5000
        _add_item(session, ticket, "other", "分割清算（現金）", 1, -2000)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 3000

    def test_full_split_zeroes_total(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 1, 5000)  # 5000
        _add_item(session, ticket, "other", "分割清算（現金）", 1, -3000)
        _add_item(session, ticket, "other", "分割清算（カード決済）", 1, -2000)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 0


# ─────────────────────────────────────────
# ドリフト修復: total_amount が手動でずれた場合に recalc で修復される
# ─────────────────────────────────────────

class TestDriftRepair:
    def test_repair_drifted_total(self, db):
        """total_amount が何らかの理由でずれていても recalc で正しい値に戻る"""
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)
        _add_item(session, ticket, "extension", "延長", 2, 3000)

        ticket.total_amount = 99999
        ticket.extension_count = 99
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 11000
        assert ticket.extension_count == 1

    def test_repair_negative_total(self, db):
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 1, 1000)
        ticket.total_amount = -500
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 1000


# ─────────────────────────────────────────
# 税サ込み合計 (_calc_grand_total)
# ─────────────────────────────────────────

class TestCalcGrandTotal:
    def test_grand_total_basic(self, db):
        from app.routers.tickets import _calc_grand_total
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)
        _sync_ticket_totals(ticket, session)
        # 5000 * 1.21 = 6050
        assert _calc_grand_total(ticket) == 6050

    def test_grand_total_with_discount_item(self, db):
        from app.routers.tickets import _calc_grand_total
        session, store_id = db
        ticket = _make_ticket(session, store_id)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)  # 5000
        _add_item(session, ticket, "other", "値引き（端数カット）担当:星", 1, -36)
        _sync_ticket_totals(ticket, session)
        # adj = -36 (値引きアイテム)
        # sub = 4964 - (-36) = 5000
        # grand = round(5000 * 1.21) + (-36) = 6050 - 36 = 6014
        assert _calc_grand_total(ticket) == 6014

    def test_grand_total_screenshot_case(self, db):
        """スクリーンショットの再現: 小計21,600 → 合計26,100 の検算"""
        from app.routers.tickets import _calc_grand_total
        session, store_id = db
        ticket = _make_ticket(session, store_id, guest_count=2)
        _add_item(session, ticket, "set", "セット料金", 2, 2500)       # 5000
        _add_item(session, ticket, "extension", "延長", 2, 3000)       # 6000
        _add_item(session, ticket, "drink_l", "Lドリンク", 2, 1700)    # 3400
        _add_item(session, ticket, "drink_l", "Lドリンク", 4, 1700)    # 6800
        _add_item(session, ticket, "drink_l", "Lドリンク", 2, 1700)    # 3400
        _add_item(session, ticket, "other", "値引き（端数カット）担当:星", 1, -36)
        _sync_ticket_totals(ticket, session)
        assert ticket.total_amount == 24564  # 正しい小計（修正後）

        grand = _calc_grand_total(ticket)
        # adj = -36
        # sub = 24564 - (-36) = 24600
        # grand = round(24600 * 1.21) + (-36) = 29766 - 36 = 29730
        assert grand == 29730
