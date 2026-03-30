"""計算ロジックの多パターンテスト"""
import sys, io
sys.path.insert(0, '.')
import openpyxl
from app.routers.excel_import import parse_daily_sheets

def run_tests(path, year, month):
    with open(path, "rb") as f:
        content = f.read()
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    visits = parse_daily_sheets(wb, year, month)
    print(f"\n{'='*50}")
    print(f"ファイル: {path.split(chr(92))[-1]}, {year}年{month}月")
    print(f"総来店レコード数: {len(visits)}")

    from datetime import date
    from collections import defaultdict

    day_labels = ["月", "火", "水", "木", "金", "土", "日"]
    seen = set()
    errors = []

    for v in visits:
        name = v["customer_name"]
        if name in seen:
            continue
        seen.add(name)

        cvs = [x for x in visits if x["customer_name"] == name]
        visit_count = len(cvs)
        total_spend = sum(x["total_payment"] for x in cvs)
        total_extensions = sum(x["extensions"] for x in cvs)
        total_persons = sum(x["group_size"] for x in cvs)
        avg_extensions = round(total_extensions / max(total_persons, 1), 2)

        # 来店動機集計
        src_counts = {}
        for x in cvs:
            src = x["arrival_source"] if x["arrival_source"] else "不明"
            src_counts[src] = src_counts.get(src, 0) + 1
        src_total = sum(src_counts.values())

        # 月間平均
        visit_dates = [date.fromisoformat(x["date"]) for x in cvs]
        distinct_months = len({(d.year, d.month) for d in visit_dates})
        monthly_avg = round(visit_count / max(distinct_months, 1), 1)

        # テスト1: 来店動機合計 == 来店回数
        if src_total != visit_count:
            errors.append(f"[動機合計NG] {name}: 来店{visit_count}回 vs 動機合計{src_total}回 → {src_counts}")

        # テスト2: 月間平均の整合性（来店1回/月なら月間平均<=来店回数）
        if monthly_avg > visit_count:
            errors.append(f"[月間平均NG] {name}: monthly_avg={monthly_avg} > visit_count={visit_count}")

        # テスト3: avg_extensions >= 0
        if avg_extensions < 0:
            errors.append(f"[延長NG] {name}: avg_extensions={avg_extensions}")

    if errors:
        print(f"\nNG エラー {len(errors)}件:")
        for e in errors:
            print(f"  {e}")
    else:
        print(f"OK 全テストパス（{len(seen)}名）")

    # サンプル確認（最多来店者）
    name_counts = defaultdict(int)
    for v in visits:
        name_counts[v["customer_name"]] += 1
    top3 = sorted(name_counts.items(), key=lambda x: -x[1])[:3]
    print(f"\n来店回数TOP3: {top3}")
    for name, cnt in top3:
        cvs = [x for x in visits if x["customer_name"] == name]
        src_counts = {}
        for x in cvs:
            src = x["arrival_source"] if x["arrival_source"] else "不明"
            src_counts[src] = src_counts.get(src, 0) + 1
        visit_dates = [date.fromisoformat(x["date"]) for x in cvs]
        distinct_months = len({(d.year, d.month) for d in visit_dates})
        monthly_avg = round(cnt / max(distinct_months, 1), 1)
        print(f"  {name}: {cnt}回 | 動機合計{sum(src_counts.values())} | 月平均{monthly_avg} | {src_counts}")

# テスト実行
run_tests(r"C:\Users\lalal\Downloads\東中野PC日報2月2026.xlsx", 2026, 2)
run_tests(r"C:\Users\lalal\Downloads\東中野PC日報1月2026.xlsx", 2026, 1)
