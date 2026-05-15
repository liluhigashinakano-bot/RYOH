from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from ..database import get_db
from .. import models
from ..auth import get_current_user, require_superadmin, is_admin

router = APIRouter(prefix="/api/stores", tags=["stores"])


class StoreCreate(BaseModel):
    name: str
    code: str
    set_price: int = 0
    extension_price: int = 0
    address: Optional[str] = None
    phone: Optional[str] = None
    postal_code: Optional[str] = None
    invoice_number: Optional[str] = None
    receipt_name: Optional[str] = None
    receipt_footer: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    nearest_station: Optional[str] = None
    related_lines: Optional[List[str]] = None
    last_train_routes: Optional[List[dict]] = None


class StoreUpdate(BaseModel):
    name: Optional[str] = None
    set_price: Optional[int] = None
    extension_price: Optional[int] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    postal_code: Optional[str] = None
    invoice_number: Optional[str] = None
    receipt_name: Optional[str] = None
    receipt_footer: Optional[str] = None
    ai_advisor_enabled: Optional[bool] = None
    manual_set_start: Optional[bool] = None
    cast_order_counter_enabled: Optional[bool] = None
    is_active: Optional[bool] = None
    open_time: Optional[str] = None
    close_time: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    nearest_station: Optional[str] = None
    related_lines: Optional[List[str]] = None
    last_train_routes: Optional[List[dict]] = None


class StoreResponse(BaseModel):
    id: int
    name: str
    code: str
    set_price: Optional[int] = 0
    extension_price: Optional[int] = 0
    address: Optional[str]
    phone: Optional[str]
    postal_code: Optional[str] = None
    invoice_number: Optional[str] = None
    receipt_name: Optional[str] = None
    receipt_footer: Optional[str] = None
    ai_advisor_enabled: Optional[bool] = True
    manual_set_start: Optional[bool] = True
    cast_order_counter_enabled: Optional[bool] = True
    is_active: bool
    open_time: Optional[str] = None
    close_time: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    nearest_station: Optional[str] = None
    related_lines: Optional[List[str]] = None
    last_train_routes: Optional[List[dict]] = None

    class Config:
        from_attributes = True


@router.get("", response_model=list[StoreResponse])
def get_stores(
    all: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if all or is_admin(current_user) or not current_user.store_id:
        return db.query(models.Store).filter(models.Store.is_active == True).all()
    return db.query(models.Store).filter(
        models.Store.id == current_user.store_id,
        models.Store.is_active == True
    ).all()


@router.get("/geocode")
def geocode_station(
    station_name: str,
    current_user: models.User = Depends(get_current_user),
):
    """駅名からNominatim (OpenStreetMap) で緯度経度を取得"""
    import requests
    query = f"{station_name}駅" if "駅" not in station_name else station_name
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "json", "countrycodes": "jp", "limit": 5},
        timeout=10,
        headers={"User-Agent": "RYOH-POS/1.0"},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Geocoding APIエラー")
    results = resp.json()
    if not results:
        raise HTTPException(status_code=404, detail="駅が見つかりません")
    best = results[0]
    return {"latitude": float(best["lat"]), "longitude": float(best["lon"]), "name": best.get("display_name", station_name).split(",")[0]}


# 路線名マスタ
TRAIN_LINE_MASTER = [
    "中央線(快速)", "中央総武線(各停)", "総武線(快速)",
    "山手線", "京浜東北線", "埼京線", "湘南新宿ライン",
    "東海道線", "横須賀線", "南武線", "武蔵野線", "青梅線", "五日市線",
    "京王線", "京王井の頭線", "京王相模原線", "京王高尾線",
    "小田急小田原線", "小田急多摩線", "小田急江ノ島線",
    "東急東横線", "東急田園都市線", "東急目黒線", "東急大井町線", "東急池上線",
    "西武新宿線", "西武池袋線", "西武拝島線",
    "東武東上線", "東武スカイツリーライン", "東武伊勢崎線",
    "東京メトロ丸ノ内線", "東京メトロ銀座線", "東京メトロ日比谷線",
    "東京メトロ東西線", "東京メトロ千代田線", "東京メトロ有楽町線",
    "東京メトロ半蔵門線", "東京メトロ南北線", "東京メトロ副都心線",
    "都営大江戸線", "都営新宿線", "都営三田線", "都営浅草線",
    "つくばエクスプレス", "りんかい線", "東京モノレール",
    "京急本線", "京急空港線",
    "相鉄本線", "相鉄いずみ野線",
]


@router.get("/train-lines")
def get_train_lines(
    q: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
):
    """路線名の候補を返す（部分一致検索対応）"""
    if q:
        return [line for line in TRAIN_LINE_MASTER if q in line]
    return TRAIN_LINE_MASTER


@router.get("/{store_id}", response_model=StoreResponse)
def get_store(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    store = db.query(models.Store).filter(models.Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません")
    return store


@router.post("", response_model=StoreResponse)
def create_store(
    data: StoreCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superadmin),
):
    existing = db.query(models.Store).filter(models.Store.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="このコードは既に使用されています")
    store = models.Store(**data.model_dump())
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@router.put("/{store_id}", response_model=StoreResponse)
def update_store(
    store_id: int,
    data: StoreUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superadmin),
):
    store = db.query(models.Store).filter(models.Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(store, field, value)
    db.commit()
    db.refresh(store)
    return store


@router.delete("/{store_id}")
def delete_store(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_superadmin),
):
    store = db.query(models.Store).filter(models.Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="店舗が見つかりません")
    store.is_active = False
    db.commit()
    return {"message": "店舗を削除しました"}
