"""鉄道運行情報（Yahoo路線情報スクレイピング）"""
import re
import time
from fastapi import APIRouter
import httpx

router = APIRouter(prefix="/api/train-info", tags=["train-info"])

# 対象路線キーワード（Yahoo上の表記）
TARGET_LINES = [
    "中央線(快速)",
    "中央総武線(各停)",
    "総武線(快速)",
    "都営大江戸線",
    "東京メトロ丸ノ内線",
]

# キャッシュ（5分間）
_cache: dict = {"data": None, "fetched_at": 0}
CACHE_TTL = 300


def _scrape_yahoo_train_info() -> list[dict]:
    url = "https://transit.yahoo.co.jp/traininfo/area/4/"
    try:
        resp = httpx.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"[TRAIN] Yahoo fetch error: {e}")
        return []

    results = []
    # <tr> 内の <td> をパース: <td><a>路線名</a></td><td>状況</td><td>詳細</td>
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) < 2:
            continue
        # 路線名（aタグの中のテキスト）
        line_match = re.search(r'>([^<]+)</a>', cells[0])
        if not line_match:
            continue
        line_name = line_match.group(1).strip()

        # 対象路線か判定
        matched = False
        for target in TARGET_LINES:
            if target in line_name:
                matched = True
                break
        if not matched:
            continue

        # 状況テキスト
        status_text = re.sub(r'<[^>]+>', '', cells[1]).strip()
        detail = re.sub(r'<[^>]+>', '', cells[2]).strip() if len(cells) > 2 else ""

        if "遅延" in status_text or "遅れ" in status_text:
            status = "delay"
        elif "見合わせ" in status_text or "運休" in status_text:
            status = "suspend"
        elif "直通運転中止" in status_text:
            status = "trouble"
        else:
            status = "normal"

        results.append({
            "line": line_name,
            "status": status,
            "status_text": status_text,
            "detail": detail if status != "normal" else "",
        })

    # 対象路線がページに見つからなかった場合は平常運転として追加
    found_names = {r["line"] for r in results}
    for target in TARGET_LINES:
        if not any(target in name for name in found_names):
            results.append({
                "line": target,
                "status": "normal",
                "status_text": "平常運転",
                "detail": "",
            })

    return results


@router.get("")
def get_train_info():
    now = time.time()
    if _cache["data"] is not None and (now - _cache["fetched_at"]) < CACHE_TTL:
        return {"lines": _cache["data"], "cached": True, "fetched_at": _cache["fetched_at"]}

    data = _scrape_yahoo_train_info()
    _cache["data"] = data
    _cache["fetched_at"] = now
    return {"lines": data, "cached": False, "fetched_at": now}
