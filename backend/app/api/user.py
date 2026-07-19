"""
用户与权限查询 API 路由

接口列表：
  - GET /api/user/list       用户列表
  - GET /api/user/roles      角色列表
  - PUT /api/user/profile    更新个人信息
  - PUT /api/user/password   修改密码
  - PUT /api/user/{id}/status 管理员启用或停用用户
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_admin
from app.database.session import get_db
from app.entity.schemas import RoleAssignmentRequest, UserStatusRequest
from app.services.audit_service import write_audit
from app.services.user_service import user_service

router = APIRouter(prefix="/api/user", tags=["用户管理"])


@router.get("/list", summary="用户列表")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="用户名/邮箱关键词"),
    _current_user=Depends(require_admin),
):
    """获取用户分页列表。"""
    return user_service.list_users(
        page=page,
        page_size=page_size,
        keyword=keyword,
    )


@router.get("/roles", summary="获取所有角色")
async def list_roles(_current_user=Depends(require_admin)):
    """获取系统中的所有角色。"""
    return {"roles": user_service.list_roles()}


@router.put("/{user_id}/roles", summary="管理员分配用户角色")
async def set_user_roles(
    user_id: int,
    payload: RoleAssignmentRequest,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = user_service.set_user_roles(db, user_id, payload.roles)
    write_audit(
        db, user=admin, module="system", action="update_roles",
        target_type="user", target_id=user_id,
        details={"roles": ",".join(sorted(payload.roles))}, request=request,
    )
    db.commit()
    return {
        "message": "角色已更新",
        "user_id": user.id,
        "roles": user_service.get_user_roles(db, user),
    }


@router.put("/{user_id}/status", summary="管理员启用或停用用户")
async def set_user_status(
    user_id: int,
    payload: UserStatusRequest,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = user_service.set_user_status(db, user_id, payload.is_active)
    write_audit(
        db,
        user=admin,
        module="system",
        action="enable_user" if payload.is_active else "disable_user",
        target_type="user",
        target_id=user_id,
        request=request,
    )
    db.commit()
    return {
        "message": "用户已启用" if payload.is_active else "用户已停用",
        "user_id": user.id,
        "is_active": user.is_active,
    }


@router.put("/profile", summary="更新个人信息")
async def update_profile(
    request: Request,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新当前用户的手机号和邮箱。"""
    try:
        result = user_service.update_profile(
            user_id=current_user.id,
            phone=phone,
            email=email,
            db=db,
        )
    except HTTPException as exc:
        db.rollback()
        write_audit(
            db,
            user=current_user,
            module="system",
            action="update_profile",
            target_type="user",
            target_id=current_user.id,
            request=request,
            status="failed",
            error_message=str(exc.detail),
        )
        db.commit()
        raise
    write_audit(
        db,
        user=current_user,
        module="system",
        action="update_profile",
        target_type="user",
        target_id=current_user.id,
        details={
            "updated_phone": phone is not None,
            "updated_email": email is not None,
        },
        request=request,
    )
    db.commit()
    return result


@router.put("/password", summary="修改密码")
async def change_password(
    request: Request,
    old_password: str = Query(..., min_length=1, max_length=128),
    new_password: str = Query(..., min_length=6, max_length=128),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """校验旧密码后修改当前用户密码。"""
    try:
        result = user_service.change_password(
            user_id=current_user.id,
            old_password=old_password,
            new_password=new_password,
            db=db,
        )
    except HTTPException as exc:
        db.rollback()
        write_audit(
            db,
            user=current_user,
            module="auth",
            action="change_password",
            target_type="user",
            target_id=current_user.id,
            request=request,
            status="failed",
            error_message=str(exc.detail),
        )
        db.commit()
        raise
    write_audit(
        db,
        user=current_user,
        module="auth",
        action="change_password",
        target_type="user",
        target_id=current_user.id,
        request=request,
    )
    db.commit()
    return result
