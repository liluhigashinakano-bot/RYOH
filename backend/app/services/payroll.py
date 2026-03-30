"""
給与計算サービス - TDD対象のビジネスロジック
全ての計算は純粋関数として実装し、テスト可能にする
"""
import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class DrinkCounts:
    s: int = 0       # Sドリンク
    l: int = 0       # Lドリンク
    mg: int = 0      # メガドリンク
    shot: int = 0    # ショット
    champagne_glasses: int = 0  # シャンパングラス数


@dataclass
class BackRates:
    drink_s_rate: float = 0.1
    drink_l_rate: float = 0.1
    drink_mg_rate: float = 0.1
    shot_rate: float = 0.1
    champagne_rate: float = 0.1
    honshimei_unit: int = 1000  # 本指名1件あたりバック
    douhan_unit: int = 2000     # 同伴1件あたりバック


@dataclass
class MenuPrices:
    drink_s: int = 900
    drink_l: int = 1700
    drink_mg: int = 3700
    shot_cast: int = 1500
    champagne_glass: int = 1000  # グラス単価（仮）


def calculate_work_hours(start_time_str: str, end_time_str: str) -> float:
    """
    出退勤時間から労働時間を計算（30分単位切り捨て）
    時刻は "HH:MM" 形式。深夜は "25:30" のように24超えで表現。

    例: "20:00" → "26:30" = 6.5h → 切り捨てなし → 6.5h
        "20:00" → "26:20" = 6.33h → 30分単位切り捨て → 6.0h
    """
    def parse_time(t: str) -> float:
        h, m = t.split(":")
        return int(h) + int(m) / 60

    start = parse_time(start_time_str)
    end = parse_time(end_time_str)
    if end < start:
        end += 24
    hours = end - start
    # 30分単位切り捨て
    return math.floor(hours * 2) / 2


def calculate_base_pay(hourly_rate: int, work_hours: float) -> int:
    """基本給計算（端数切り捨て）"""
    return int(hourly_rate * work_hours)


def calculate_drink_back(
    drinks: DrinkCounts,
    prices: MenuPrices,
    rates: BackRates,
) -> int:
    """ドリンクバック計算"""
    back = (
        drinks.s * prices.drink_s * rates.drink_s_rate
        + drinks.l * prices.drink_l * rates.drink_l_rate
        + drinks.mg * prices.drink_mg * rates.drink_mg_rate
        + drinks.shot * prices.shot_cast * rates.shot_rate
    )
    return int(back)


def calculate_champagne_back(
    glasses: int,
    glass_price: int,
    rate: float,
) -> int:
    """シャンパンバック計算"""
    return int(glasses * glass_price * rate)


def calculate_honshimei_back(count: int, unit: int) -> int:
    """本指名バック計算"""
    return count * unit


def calculate_douhan_back(count: int, unit: int) -> int:
    """同伴バック計算"""
    return count * unit


def calculate_total_pay(
    base_pay: int,
    drink_back: int,
    champagne_back: int,
    honshimei_back: int,
    douhan_back: int,
    transport_deduction: int = 0,
    withholding_tax_rate: float = 0.0,
    round_unit: int = 100,  # 百円単位切り捨て
) -> dict:
    """
    最終給与計算
    Returns: {
        gross: 総支給額,
        tax: 源泉徴収額,
        transport_deduction: 交通費控除,
        total_pay: 手取り（round_unit切り捨て）
    }
    """
    gross = base_pay + drink_back + champagne_back + honshimei_back + douhan_back
    tax = int(gross * withholding_tax_rate)
    net = gross - tax - transport_deduction
    total_pay = (net // round_unit) * round_unit  # 切り捨て
    return {
        "gross": gross,
        "tax": tax,
        "transport_deduction": transport_deduction,
        "total_pay": total_pay,
    }


def calculate_consumption_tax(amount: int, rate: float = 0.10) -> int:
    """消費税計算"""
    return int(amount * rate)


def calculate_receipt_total(
    alcohol_amount: int,     # 酒類（8%）
    food_amount: int,        # フード（8%）
    service_amount: int,     # セット・延長等（10%）
    service_charge_rate: float = 0.0,
) -> dict:
    """
    レシート合計計算（インボイス対応）
    Returns: {
        subtotal: 税抜き合計,
        tax_8: 8%対象税額,
        tax_10: 10%対象税額,
        service_charge: サービス料,
        total: 最終合計
    }
    """
    tax_8_base = alcohol_amount + food_amount
    tax_10_base = service_amount
    tax_8 = calculate_consumption_tax(tax_8_base, 0.08)
    tax_10 = calculate_consumption_tax(tax_10_base, 0.10)
    subtotal = tax_8_base + tax_10_base
    service_charge = int(subtotal * service_charge_rate)
    total = subtotal + tax_8 + tax_10 + service_charge
    return {
        "subtotal": subtotal,
        "tax_8_base": tax_8_base,
        "tax_10_base": tax_10_base,
        "tax_8": tax_8,
        "tax_10": tax_10,
        "service_charge": service_charge,
        "total": total,
    }
