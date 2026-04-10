"""鉄道運行情報（Yahoo路線情報スクレイピング）"""
import re
import time
from datetime import datetime
from fastapi import APIRouter
import httpx

router = APIRouter(prefix="/api/train-info", tags=["train-info"])

# 対象路線のキーワード（Yahoo路線情報ページ内のテキストマッチ用）
TARGET_LINES = [
    "JR中央線(快速)",
    "JR中央・総武線",
    "JR総武線(快速)",
    "都営大江戸線",
    "東京メトロ丸ノ内線",
]

# キャッシュ（5分間）
_cache: dict = {"data": None, "fetched_at": 0}
CACHE_TTL = 300  # 5分


def _scrape_yahoo_train_info() -> list[dict]:
    """Yahoo路線情報 関東エリアをスクレイピング"""
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
    for line_name in TARGET_LINES:
        # 路線名を含む行を探す
        # Yahoo のHTML構造: <a ...>路線名</a> の後に状況テキスト
        escaped = re.escape(line_name)
        # パターン1: 遅延・運休がある場合
        pattern_delay = rf'{escaped}.*?<a[^>]*>([^<]*(?:遅延|運転見合わせ|運休|直通運転中止)[^<]*)</a>'
        match_delay = re.search(pattern_delay, html, re.DOTALL)
        if match_delay:
            status_text = match_delay.group(1).strip()
            # 詳細テキストを取得
            detail = ""
            detail_pattern = rf'{escaped}.*?<p[^>]*class="[^"]*trouble[^"]*"[^>]*>(.*?)</p>'
            detail_match = re.search(detail_pattern, html, re.DOTALL)
            if detail_match:
                detail = re.sub(r'<[^>]+>', '', detail_match.group(1)).strip()
            results.append({
                "line": line_name,
                "status": "delay" if "遅延" in status_text else "suspend" if "見合わせ" in status_text or "運休" in status_text else "trouble",
                "status_text": status_text,
                "detail": detail,
            })
        else:
            # 路線名がページに存在するか確認
            if line_name in html:
                results.append({
                    "line": line_name,
                    "status": "normal",
                    "status_text": "平常運転",
                    "detail": "",
                })
            else:
                # 路線名が見つからない＝情報なし（平常と判断）
                results.append({
                    "line": line_name,
                    "status": "normal",
                    "status_text": "平常運転",
                    "detail": "",
                })

    return results


@router.get("")
def get_train_info():
    """対象路線の運行情報を返す（5分キャッシュ）"""
    now = time.time()
    if _cache["data"] is not None and (now - _cache["fetched_at"]) < CACHE_TTL:
        return {"lines": _cache["data"], "cached": True, "fetched_at": _cache["fetched_at"]}

    data = _scrape_yahoo_train_info()
    _cache["data"] = data
    _cache["fetched_at"] = now
    return {"lines": data, "cached": False, "fetched_at": now}
