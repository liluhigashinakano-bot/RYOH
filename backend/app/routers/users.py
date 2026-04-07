from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from ..database import get_db
from .. import models
from ..auth import get_current_user, require_administrator, require_permission, get_effective_permissions, is_admin, get_password_hash

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    role: models.UserRole = models.UserRole.staff
    store_id: Optional[int] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[models.UserRole] = None
    store_id: Optional[int] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    store_id: Optional[int]
    is_active: bool
    permissions: Optional[dict] = None

    class Config:
        from_attributes = True


@router.get("")
def get_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_permission("accounts", "view")),
):
    users = db.query(models.User).filter(models.User.is_active == True).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "role": str(u.role),
            "store_id": u.store_id,
            "is_active": u.is_active,
            "permissions": u.permissions,
        }
        for u in users
    ]


@router.post("")
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_permission("accounts", "edit")),
):
    if db.query(models.User).filter(models.User.email == data.email).first():
        raise HTTPException(status_code=400, detail="このメールアドレスは既に登録されています")
    # administratorロールを作成できるのはadministratorのみ
    if str(data.role) in ("administrator", "superadmin") and not is_admin(current_user):
        raise HTTPException(status_code=403, detail="administratorロールの作成権限がありません")
    user = models.User(
        email=data.email,
        password_hash=get_password_hash(data.password),
        name=data.name,
        role=data.role,
        store_id=data.store_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name, "role": str(user.role), "store_id": user.store_id, "is_active": user.is_active, "permissions": user.permissions}


@router.put("/{user_id}")
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_permission("accounts", "edit")),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    update_data = data.model_dump(exclude_none=True)
    if "password" in update_data:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))
    for field, value in update_data.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name, "role": str(user.role), "store_id": user.store_id, "is_active": user.is_active, "permissions": user.permissions}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_administrator),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="自分自身は削除できません")
    user.is_active = False
    db.commit()
    return {"message": "ユーザーを削除しました"}


@router.post("/{user_id}/permissions")
def update_user_permissions(
    user_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_permission("accounts", "edit")),
):
    """ユーザー個別権限を設定（nullでロール権限にリセット）"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    # administratorの権限は変更不可
    if is_admin(user):
        raise HTTPException(status_code=400, detail="administratorの権限は変更できません")
    # data.permissions = None でリセット
    perms = data.get("permissions")
    user.permissions = perms
    db.commit()
    return {"message": "権限を更新しました", "permissions": user.permissions}


@router.get("/role-permissions")
def get_role_permissions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_permission("accounts", "view")),
):
    """ロール別デフォルト権限一覧"""
    records = db.query(models.RolePermission).all()
    return {r.role: r.permissions for r in records}


@router.post("/role-permissions/{role}")
def update_role_permissions(
    role: str,
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_administrator),
):
    """ロール別デフォルト権限を更新（administratorのみ）"""
    record = db.query(models.RolePermission).filter_by(role=role).first()
    if not record:
        record = models.RolePermission(role=role, permissions={})
        db.add(record)
    record.permissions = data.get("permissions", {})
    db.commit()
    return {"message": "ロール権限を更新しました", "role": role, "permissions": record.permissions}
