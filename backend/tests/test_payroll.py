"""
給与計算ロジックのTDDテスト
全てのビジネスロジックをカバー
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.payroll import (
    calculate_work_hours,
    calculate_base_pay,
    calculate_drink_back,
    calculate_champagne_back,
    calculate_total_pay,
    calculate_receipt_total,
    DrinkCounts,
    BackRates,
    MenuPrices,
)


class TestWorkHours:
    def test_normal_shift(self):
        """通常シフト: 20:00-26:00 = 6時間"""
        assert calculate_work_hours("20:00", "26:00") == 6.0

    def test_half_hour_truncation(self):
        """29分 → 30分未満 → 切り捨てで0.0時間加算"""
        assert calculate_work_hours("20:00", "26:29") == 6.0

    def test_30min_boundary(self):
        """30分ちょうど → 0.5時間加算"""
        assert calculate_work_hours("20:00", "26:30") == 6.5

    def test_late_night_shift(self):
        """深夜シフト: 25:30-29:00 = 3.5時間"""
        assert calculate_work_hours("25:30", "29:00") == 3.5

    def test_midnight_cross(self):
        """深夜越え: 22:00-26:00 = 4.0時間"""
        assert calculate_work_hours("22:00", "26:00") == 4.0


class TestBasePay:
    def test_standard_rate(self):
        """時給1400円 × 4時間 = 5600円"""
        assert calculate_base_pay(1400, 4.0) == 5600

    def test_half_hour(self):
        """時給1400円 × 3.5時間 = 4900円"""
        assert calculate_base_pay(1400, 3.5) == 4900

    def test_help_rate(self):
        """ヘルプ時給1500円 × 4時間 = 6000円"""
        assert calculate_base_pay(1500, 4.0) == 6000


class TestDrinkBack:
    def setup_method(self):
        self.prices = MenuPrices()
        self.rates = BackRates()

    def test_s_drink_back(self):
        """Sドリンク1杯: 900円 × 10% = 90円"""
        drinks = DrinkCounts(s=1)
        assert calculate_drink_back(drinks, self.prices, self.rates) == 90

    def test_l_drink_back(self):
        """Lドリンク1杯: 1700円 × 10% = 170円"""
        drinks = DrinkCounts(l=1)
        assert calculate_drink_back(drinks, self.prices, self.rates) == 170

    def test_mg_drink_back(self):
        """MGドリンク1杯: 3700円 × 10% = 370円"""
        drinks = DrinkCounts(mg=1)
        assert calculate_drink_back(drinks, self.prices, self.rates) == 370

    def test_mixed_drinks(self):
        """S×3 + L×2 + ショット×1: 270+340+150 = 760円"""
        drinks = DrinkCounts(s=3, l=2, shot=1)
        result = calculate_drink_back(drinks, self.prices, self.rates)
        assert result == 270 + 340 + 150

    def test_zero_drinks(self):
        """ドリンクなし = 0円"""
        drinks = DrinkCounts()
        assert calculate_drink_back(drinks, self.prices, self.rates) == 0


class TestTotalPay:
    def test_basic_calculation(self):
        """基本: 基本給5600 + ドリンクバック760 = 6360 → 百円切り捨て = 6300"""
        result = calculate_total_pay(
            base_pay=5600,
            drink_back=760,
            champagne_back=0,
            honshimei_back=0,
            douhan_back=0,
        )
        assert result["total_pay"] == 6300
        assert result["gross"] == 6360

    def test_with_transport_deduction(self):
        """交通費控除あり: 総支給6360 - 交通費1000 = 5360 → 5300"""
        result = calculate_total_pay(
            base_pay=5600,
            drink_back=760,
            champagne_back=0,
            honshimei_back=0,
            douhan_back=0,
            transport_deduction=1000,
        )
        assert result["total_pay"] == 5300

    def test_honshimei_back(self):
        """本指名2件: 2000円バック → 総支給8360 → 8300"""
        result = calculate_total_pay(
            base_pay=5600,
            drink_back=760,
            champagne_back=0,
            honshimei_back=2000,
            douhan_back=0,
        )
        assert result["gross"] == 8360
        assert result["total_pay"] == 8300

    def test_exact_round_amount(self):
        """ちょうど百円単位の場合は切り捨てなし"""
        result = calculate_total_pay(
            base_pay=6000,
            drink_back=0,
            champagne_back=0,
            honshimei_back=0,
            douhan_back=0,
        )
        assert result["total_pay"] == 6000


class TestReceiptTotal:
    def test_alcohol_only_8pct(self):
        """酒類のみ（8%）: 1000円 + 80円税 = 1080円"""
        result = calculate_receipt_total(
            alcohol_amount=1000,
            food_amount=0,
            service_amount=0,
        )
        assert result["tax_8"] == 80
        assert result["tax_10"] == 0
        assert result["total"] == 1080

    def test_service_10pct(self):
        """セット料金（10%）: 2200円 + 220円税 = 2420円"""
        result = calculate_receipt_total(
            alcohol_amount=0,
            food_amount=0,
            service_amount=2200,
        )
        assert result["tax_10"] == 220
        assert result["total"] == 2420

    def test_mixed_tax(self):
        """混合: 酒1000(8%) + セット2200(10%) → 税80+220=300"""
        result = calculate_receipt_total(
            alcohol_amount=1000,
            food_amount=0,
            service_amount=2200,
        )
        assert result["tax_8"] == 80
        assert result["tax_10"] == 220
        assert result["total"] == 1000 + 2200 + 80 + 220
