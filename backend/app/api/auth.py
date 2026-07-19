"""
认证相关 API 路由
- POST /api/auth/register  用户注册
- POST /api/auth/login     用户登录
- GET  /api/auth/me        获取当前用户信息
"""

from typing import Optional

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.config.settings import settings
from app.database.session import get_db
from app.entity.schemas import TokenResponse, UserLogin, UserRegister, UserResponse
from app.services.audit_service import write_audit
from app.services.user_service import user_service
from app.storage.redis_client import redis_client

router = APIRouter(prefix="/api/auth", tags=["认证"])

# OAuth2 密码模式，用于从请求 Header 中提取 Token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """
    从 JWT Token 中解析当前用户
    在需要认证的路由中通过 Depends(get_current_user) 使用
    """
    credentials_exception = HTTPException(
        status_code=401,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not settings.DEBUG and not redis_client.ensure_available():
        raise HTTPException(status_code=503, detail="认证缓存暂时不可用，请稍后重试")
    try:
        payload = decode_access_token(token)
        user_id_str: Optional[str] = payload.get("sub")
        jti: Optional[str] = payload.get("jti")
        if user_id_str is None or jti is None:
            raise credentials_exception
        user_id = int(user_id_str)
        blacklisted = redis_client.exists(f"jwt:blacklist:{jti}")
        expected_version = redis_client.get(user_service.token_version_key(user_id)) or "0"
        if not settings.DEBUG:
            if not redis_client.ensure_available():
                raise HTTPException(status_code=503, detail="认证缓存暂时不可用，请稍后重试")
            # RedisClient 开发态允许内存降级；生产态重连后必须从 Redis 再读一次。
            blacklisted = redis_client.exists(f"jwt:blacklist:{jti}")
            expected_version = redis_client.get(user_service.token_version_key(user_id)) or "0"
            if not redis_client.ensure_available():
                raise HTTPException(status_code=503, detail="认证缓存暂时不可用，请稍后重试")
        if blacklisted or str(payload.get("token_version", "0")) != expected_version:
            raise credentials_exception
    except (JWTError, ValueError):
        raise credentials_exception

    user = user_service.get_user_by_id(db, user_id)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="用户已停用")
    return user


async def require_admin(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """仅允许 admin；is_superuser 只作为历史兼容。"""
    if not getattr(current_user, "is_superuser", False) and "admin" not in user_service.get_user_roles(db, current_user):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(request: UserRegister, http_request: Request, db: Session = Depends(get_db)):
    """
    用户注册

    - **username**: 用户名（3-50 字符）
    - **email**: 邮箱
    - **password**: 密码（至少 6 位）
    """
    user = user_service.register(
        db=db,
        username=request.username,
        email=request.email,
        password=request.password,
    )
    write_audit(
        db, user=user, module="auth", action="register", target_type="user",
        target_id=user.id, details={"username": user.username}, request=http_request,
    )
    db.commit()
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "avatar": user.avatar,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "roles": user_service.get_user_roles(db, user),
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
    }


@router.post("/login", response_model=TokenResponse)
async def login(request: UserLogin, http_request: Request, db: Session = Depends(get_db)):
    """
    用户登录

    - 返回 JWT access_token
    - 后续请求在 Header 中携带：Authorization: Bearer <token>
    """
    try:
        user = user_service.login(
            db=db,
            username=request.username,
            password=request.password,
        )
    except HTTPException as exc:
        db.rollback()
        write_audit(
            db,
            user=None,
            module="auth",
            action="login",
            target_type="user",
            details={"username": request.username},
            request=http_request,
            status="failed",
            error_message=str(exc.detail),
        )
        db.commit()
        raise
    
    access_token = user_service.create_access_token_for_user(user)
    roles = user_service.get_user_roles(db, user)
    write_audit(
        db, user=user, module="auth", action="login", target_type="user",
        target_id=user.id, request=http_request,
    )
    db.commit()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "avatar": user.avatar,
            "roles": roles,
        },
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前登录用户信息（需要 Token 认证）"""
    roles = user_service.get_user_roles(db, current_user)
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "phone": current_user.phone,
        "avatar": current_user.avatar,
        "is_active": current_user.is_active,
        "is_superuser": current_user.is_superuser,
        "roles": roles,
        "last_login_at": current_user.last_login_at,
        "created_at": current_user.created_at,
    }


@router.post("/logout", summary="安全退出")
async def logout(
    request: Request,
    token: str = Depends(oauth2_scheme),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload = decode_access_token(token)
    expires_at = int(payload["exp"])
    ttl = max(1, expires_at - int(datetime.now(timezone.utc).timestamp()))
    if not settings.DEBUG and not redis_client.ensure_available():
        raise HTTPException(status_code=503, detail="认证缓存暂时不可用，请稍后重试")
    blacklist_key = f"jwt:blacklist:{payload['jti']}"
    redis_client.set(blacklist_key, "1", expire=ttl)
    if not settings.DEBUG and (
        not redis_client.ensure_available()
        or not redis_client.exists(blacklist_key)
        or not redis_client.ensure_available()
    ):
        raise HTTPException(status_code=503, detail="认证缓存暂时不可用，请稍后重试")
    write_audit(
        db, user=current_user, module="auth", action="logout",
        target_type="user", target_id=current_user.id, request=request,
    )
    db.commit()
    return {"message": "已安全退出"}
