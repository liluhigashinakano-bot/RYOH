import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from . import models

SECRET_KEY = os.getenv("SECRET_KEY", "trust-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24時間
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

ADMIN_ROLES = {"administrator", "superadmin"}

ALL_PERMISSIONS = {
    "realtime": {"view": True},
    "pos": {"view": True, "edit": True},
    "customers": {"view": True, "edit": True},
    "employees": {"view": True, "edit": True},
    "accounts": {"view": True, "edit": True},
    "menus": {"view": True, "edit": True},
}


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({**data, "exp": expire, "type": "access"}, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode({**data, "exp": expire, "type": "refresh"}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(models.User).filter(models.User.id == int(user_id), models.User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def is_admin(user: models.User) -> bool:
    return user.role.value in ADMIN_ROLES


def get_effective_permissions(user: models.User, db: Session) -> dict:
    """ユーザーの実効権限を返す（administrator=全権限、ユーザー個別→ロール順でフォールバック）"""
    if is_admin(user):
        return ALL_PERMISSIONS
    # ユーザー個別権限が設定されている場合はそれを使用
    if user.permissions is not None:
        return user.permissions
    # ロール別デフォルト権限を使用
    role_perm = db.query(models.RolePermission).filter_by(role=user.role.value).first()
    if role_perm:
        return role_perm.permissions
    return {}


def require_roles(*roles: models.UserRole):
    def checker(current_user: models.User = Depends(get_current_user)):
        if current_user.role not in roles and current_user.role.value not in ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Permission denied")
        return current_user
    return checker


def require_superadmin(current_user: models.User = Depends(get_current_user)):
    """後方互換性のため残す。administrator/superadmin の両方を受け付ける"""
    if current_user.role.value not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Administrator required")
    return current_user


# 新しい名称
require_administrator = require_superadmin


def require_permission(page: str, perm_type: str):
    """特定ページの権限を要求するDependency"""
    def checker(
        current_user: models.User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if is_admin(current_user):
            return current_user
        perms = get_effective_permissions(current_user, db)
        if not perms.get(page, {}).get(perm_type, False):
            raise HTTPException(status_code=403, detail="Permission denied")
        return current_user
    return checker
