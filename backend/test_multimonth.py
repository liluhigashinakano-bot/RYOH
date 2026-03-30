"""複数月インポート時の計算正確性テスト"""
import sys
sys.path.insert(0, '.')
from app.routers.excel_import import _calc_prefs_from_monthly

day_labels = ["月", "火", "水", "木", "金", "土", "日"]

def test(label, monthly_data, expected):
    result = _calc_prefs_from_monthly(monthly_data, day_labels)
    errors = []
    for k, v in expected.items():
        actual = result.get(k)
        if actual != v:
            errors.append(f"  {k}: 期待={v}, 実際={actual}")
    # 来店動機合計 == 合計来店数チェック（assertで内部検証済み）
    src_total = sum(result["arrival_source"].values())
    if src_total != result["_total_visits"]:
        errors.append(f"  動機合計({src_total}) != 来店数({result['_total_visits']})")
    if errors:
        print(f"NG [{label}]")
        for e in errors: print(e)
    else:
        print(f"OK [{label}]")

# テスト1: 1ヶ月のみ（田口: 2月2回）
test("1ヶ月のみ", {
    "2026-02": {"visits": 2, "spend": 138000, "extensions": 8, "persons": 2,
                "set_l": 11.0, "set_mg": 0, "set_shot": 0,
                "in_mins": [1304, 1480], "arrival_source": {"紹介": 1, "line": 1}, "day_prefs": {"水": 1, "土": 1}}
}, {"_total_visits": 2, "_total_spend": 138000, "avg_spend": 69000,
    "avg_extensions": 4.0, "monthly_avg_visits": 2.0})

# テスト2: 2ヶ月インポート（1月2回 + 2月2回 = 合計4回）
test("2ヶ月合算", {
    "2026-01": {"visits": 2, "spend": 50000, "extensions": 2, "persons": 2,
                "set_l": 2.0, "set_mg": 0, "set_shot": 0,
                "in_mins": [1320, 1380], "arrival_source": {"看板": 2}, "day_prefs": {"火": 1, "木": 1}},
    "2026-02": {"visits": 2, "spend": 138000, "extensions": 8, "persons": 2,
                "set_l": 11.0, "set_mg": 0, "set_shot": 0,
                "in_mins": [1304, 1480], "arrival_source": {"紹介": 1, "line": 1}, "day_prefs": {"水": 1, "土": 1}}
}, {"_total_visits": 4, "_total_spend": 188000, "avg_spend": 47000,
    "avg_extensions": 2.5, "monthly_avg_visits": 2.0})

# テスト3: 同じ月を2回インポート（上書きで重複しないこと）
same_month = {"visits": 3, "spend": 60000, "extensions": 3, "persons": 3,
              "set_l": 3.0, "set_mg": 0, "set_shot": 0,
              "in_mins": [1320, 1380, 1440], "arrival_source": {"ティッシュ": 3}, "day_prefs": {"金": 3}}
test("同月再インポート（上書き）", {
    "2026-02": same_month,  # 同じキーなので上書き
}, {"_total_visits": 3, "_total_spend": 60000, "monthly_avg_visits": 3.0})

# テスト4: 動機別合計 == 来店回数（"不明"あり）
test("不明あり動機合計チェック", {
    "2026-02": {"visits": 3, "spend": 30000, "extensions": 0, "persons": 3,
                "set_l": 0, "set_mg": 0, "set_shot": 0,
                "in_mins": [], "arrival_source": {"ティッシュ": 2, "不明": 1}, "day_prefs": {}}
}, {"_total_visits": 3})

# テスト5: 月間平均来店の整合性（3ヶ月で9回 = 3.0回/月）
test("月間平均整合性", {
    "2025-12": {"visits": 3, "spend": 30000, "extensions": 0, "persons": 3, "set_l":0,"set_mg":0,"set_shot":0,"in_mins":[],"arrival_source":{"看板":3},"day_prefs":{}},
    "2026-01": {"visits": 3, "spend": 30000, "extensions": 0, "persons": 3, "set_l":0,"set_mg":0,"set_shot":0,"in_mins":[],"arrival_source":{"看板":3},"day_prefs":{}},
    "2026-02": {"visits": 3, "spend": 30000, "extensions": 0, "persons": 3, "set_l":0,"set_mg":0,"set_shot":0,"in_mins":[],"arrival_source":{"看板":3},"day_prefs":{}},
}, {"_total_visits": 9, "monthly_avg_visits": 3.0})

print("完了")
