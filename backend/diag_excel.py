"""日別シートのカラム位置を診断"""
import sys, openpyxl
sys.path.insert(0, '.')

path = r"C:\Users\lalal\Downloads\東中野PC日報2月2026.xlsx"
wb = openpyxl.load_workbook(path, data_only=True)

ws = wb["1日"]
rows = list(ws.iter_rows(values_only=True))

print("=== 1日シート ヘッダー行 (行0〜5) ===")
for i, row in enumerate(rows[:6]):
    print(f"Row{i}: {list(enumerate(row))[:50]}")

print("\n=== データ行 (行6〜15) ===")
for i, row in enumerate(rows[6:16], start=6):
    if row[0] is not None:
        print(f"Row{i} col0={row[0]}")
        # 主要カラムを表示
        for ci in [0,1,2,3,4,5,6,7,8,9,10,11,12,16,17,18,23,25,27,28,29,30,31,32,40,41,42,43]:
            if ci < len(row):
                print(f"  [{ci}]={row[ci]}", end="")
        print()
