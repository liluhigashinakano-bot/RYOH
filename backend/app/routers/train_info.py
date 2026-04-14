"""鉄道運行情報（Yahoo路線情報スクレイピング）"""
import re
import time
from fastapi import APIRouter
import httpx

router = APIRouter(prefix="/api/train-info", tags=["train-info"])

# 対象路線キーワード（Yahoo上の表記）
_DEFAULT_TARGET_LINES = [
    "中央線(快速)",
    "中央総武線(各停)",
    "総武線(快速)",
    "都営大江戸線",
    "東京メトロ丸ノ内線",
]


def _get_target_lines() -> list[str]:
    """DBの全店舗のrelated_linesを統合してスクレイピング対象路線を取得"""
    from ..database import SessionLocal
    from .. import models
    try:
        db = SessionLocal()
        stores = db.query(models.Store).filter(models.Store.is_active == True).all()
        lines = set(_DEFAULT_TARGET_LINES)
        for s in stores:
            if s.related_lines:
                for line in s.related_lines:
                    lines.add(line)
        db.close()
        return list(lines)
    except Exception:
        return _DEFAULT_TARGET_LINES

# キャッシュ（5分間）
_cache: dict = {"data": None, "fetched_at": 0}
CACHE_TTL = 300


def _scrape_yahoo_train_info() -> list[dict]:
    TARGET_LINES = _get_target_lines()
    url = "https://transit.yahoo.co.jp/traininfo/area/4/"
    try:
        resp = httpx.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }, follow_redirects=True)
        resp.raise_for_status()
        html = resp.content.decode("utf-8", errors="replace")
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

    # 重複除去（同じ路線が複数行にある場合、遅延を優先）
    seen: dict[str, dict] = {}
    for r in results:
        key = r["line"]
        if key not in seen or r["status"] != "normal":
            seen[key] = r
    results = list(seen.values())

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


# 路線→ターミナル駅マッピング（上り/下りの主要始発駅）
_LINE_TERMINALS: dict[str, list[str]] = {
    "中央線(快速)": ["新宿", "東京"],
    "中央総武線(各停)": ["新宿", "千葉"],
    "総武線(快速)": ["新宿", "千葉"],
    "都営大江戸線": ["新宿西口", "都庁前"],
    "東京メトロ丸ノ内線": ["池袋", "荻窪"],
    "京王線": ["新宿", "京王八王子"],
    "京王井の頭線": ["渋谷", "吉祥寺"],
    "京王相模原線": ["新宿", "橋本"],
    "小田急小田原線": ["新宿", "小田原"],
    "東急東横線": ["渋谷", "横浜"],
    "東急田園都市線": ["渋谷", "中央林間"],
    "西武新宿線": ["西武新宿", "本川越"],
    "西武池袋線": ["池袋", "飯能"],
    "東武東上線": ["池袋", "川越"],
    "東京メトロ銀座線": ["渋谷", "浅草"],
    "東京メトロ日比谷線": ["中目黒", "北千住"],
    "東京メトロ東西線": ["中野", "西船橋"],
    "東京メトロ千代田線": ["代々木上原", "綾瀬"],
    "東京メトロ有楽町線": ["和光市", "新木場"],
    "東京メトロ半蔵門線": ["渋谷", "押上"],
    "東京メトロ南北線": ["目黒", "赤羽岩淵"],
    "東京メトロ副都心線": ["渋谷", "和光市"],
    "都営新宿線": ["新宿", "本八幡"],
    "都営三田線": ["目黒", "西高島平"],
    "都営浅草線": ["西馬込", "押上"],
    "山手線": ["新宿", "渋谷", "池袋", "東京"],
    "京浜東北線": ["大宮", "大船"],
    "埼京線": ["新宿", "大宮"],
    "湘南新宿ライン": ["新宿", "大船"],
}

# フォールバック用
_DEFAULT_LAST_TRAIN_ROUTES = [
    {"from": "新宿", "to": "東中野", "store": "higashinakano"},
    {"from": "中野", "to": "東中野", "store": "higashinakano"},
    {"from": "池袋", "to": "新中野", "store": "shinnakano"},
    {"from": "荻窪", "to": "新中野", "store": "shinnakano"},
    {"from": "池袋", "to": "方南町", "store": "honancho"},
]

_last_train_cache: dict = {"data": None, "fetched_at": 0}
LAST_TRAIN_TTL = 900  # 15分


def _get_last_train_routes() -> list[dict]:
    """DBの店舗設定（最寄り駅+関連路線）から終電ルートを自動生成"""
    from ..database import SessionLocal
    from .. import models
    try:
        db = SessionLocal()
        stores = db.query(models.Store).filter(models.Store.is_active == True).all()
        routes = []
        for s in stores:
            station = s.nearest_station
            if not station:
                continue
            lines = s.related_lines or []
            seen = set()
            for line in lines:
                terminals = _LINE_TERMINALS.get(line, [])
                for terminal in terminals:
                    if terminal == station:
                        continue
                    key = (terminal, station)
                    if key not in seen:
                        seen.add(key)
                        routes.append({"from": terminal, "to": station, "store": s.code})
        db.close()
        return routes if routes else _DEFAULT_LAST_TRAIN_ROUTES
    except Exception:
        return _DEFAULT_LAST_TRAIN_ROUTES


def _scrape_last_trains() -> list[dict]:
    routes = _get_last_train_routes()
    results = []
    for route in routes:
        try:
            resp = httpx.get(
                "https://transit.yahoo.co.jp/search/result",
                params={"from": route["from"], "to": route["to"], "type": "4", "ticket": "ic"},
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                follow_redirects=True,
            )
            html = resp.content.decode("utf-8", errors="replace")
            clean = re.sub(r"<!--.*?-->", "", html)
            matches = re.findall(r"(\d{1,2}:\d{2})\s*→\s*(?:<[^>]*>)*(\d{1,2}:\d{2})", clean)
            if matches:
                results.append({
                    "from": route["from"],
                    "to": route["to"],
                    "store": route["store"],
                    "depart": matches[0][0],
                    "arrive": matches[0][1],
                })
            else:
                results.append({
                    "from": route["from"],
                    "to": route["to"],
                    "store": route["store"],
                    "depart": None,
                    "arrive": None,
                })
        except Exception as e:
            print(f"[TRAIN] Last train error {route['from']}→{route['to']}: {e}")
            results.append({"from": route["from"], "to": route["to"], "store": route["store"], "depart": None, "arrive": None})
    return results


@router.get("")
def get_train_info():
    now = time.time()
    if _cache["data"] is not None and (now - _cache["fetched_at"]) < CACHE_TTL:
        lines = _cache["data"]
    else:
        lines = _scrape_yahoo_train_info()
        _cache["data"] = lines
        _cache["fetched_at"] = now

    if _last_train_cache["data"] is not None and (now - _last_train_cache["fetched_at"]) < LAST_TRAIN_TTL:
        last_trains = _last_train_cache["data"]
    else:
        last_trains = _scrape_last_trains()
        _last_train_cache["data"] = last_trains
        _last_train_cache["fetched_at"] = now

    return {"lines": lines, "last_trains": last_trains, "fetched_at": now}
