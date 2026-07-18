"""用户注册、登录、查询、个人信息与密码管理服务。"""

from typing import Optional
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.logger import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.database.session import SessionLocal
from app.entity.db_models import Role, User, UserRole
from app.storage.redis_client import redis_client

logger = get_logger(__name__)


class UserService:
    """用户服务"""

    @staticmethod
    def register(db: Session, username: str, email: str, password: str) -> User:
        """
        用户注册

        Args:
            db: 数据库会话
            username: 用户名
            email: 邮箱
            password: 明文密码

        Returns:
            新创建的用户对象

        Raises:
            HTTPException: 用户名或邮箱已存在
        """
        # 检查用户名是否已存在
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="用户名已存在")

        # 检查邮箱是否已存在
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="邮箱已被注册")

        # 创建新用户
        new_user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
        )
        db.add(new_user)
        db.flush()
        user_role = db.query(Role).filter(Role.name == "user").first()
        if user_role is None:
            user_role = Role(
                name="user", display_name="普通用户", is_system=True,
                description="使用检测、报告、训练、数据集和智能体功能",
            )
            db.add(user_role)
            db.flush()
        db.add(UserRole(user_id=new_user.id, role_id=user_role.id))
        db.commit()
        db.refresh(new_user)

        return new_user

    @staticmethod
    def login(db: Session, username: str, password: str) -> User:
        """
        用户登录

        Args:
            db: 数据库会话
            username: 用户名
            password: 明文密码

        Returns:
            登录成功的用户对象

        Raises:
            HTTPException: 用户名或密码错误
        """
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        if not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="用户已停用")

        from datetime import datetime
        user.last_login_at = datetime.now()
        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def create_access_token_for_user(user: User) -> str:
        """为用户生成 JWT Token"""
        if not settings.DEBUG and not redis_client.ensure_available():
            raise HTTPException(status_code=503, detail="认证缓存暂时不可用，请稍后重试")
        token_version = redis_client.get(UserService.token_version_key(user.id)) or "0"
        if not settings.DEBUG:
            if not redis_client.ensure_available():
                raise HTTPException(status_code=503, detail="认证缓存暂时不可用，请稍后重试")
            token_version = redis_client.get(UserService.token_version_key(user.id)) or "0"
            if not redis_client.ensure_available():
                raise HTTPException(status_code=503, detail="认证缓存暂时不可用，请稍后重试")
        return create_access_token(
            data={"sub": str(user.id), "token_version": token_version}
        )

    @staticmethod
    def token_version_key(user_id: int) -> str:
        return f"jwt:user_version:{user_id}"

    @staticmethod
    def get_user_roles(db: Session, user: User) -> list[str]:
        """获取用户的角色标识列表"""
        return [ur.role.name for ur in getattr(user, "user_roles", [])]

    @staticmethod
    def set_user_roles(db: Session, user_id: int, role_names: list[str]) -> User:
        allowed = {"user", "admin"}
        requested = set(role_names)
        if not requested or not requested.issubset(allowed):
            raise HTTPException(status_code=400, detail="角色只能是 user 或 admin，且至少保留一个角色")
        existing_names = {name for (name,) in db.query(Role.name).filter(Role.name.in_(allowed)).all()}
        for missing in allowed - existing_names:
            db.add(Role(
                name=missing,
                display_name="管理员" if missing == "admin" else "普通用户",
                description="系统内置角色",
                is_system=True,
            ))
        db.flush()
        user = UserService.get_user_by_id(db, user_id)
        current = {
            name for (name,) in db.query(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == user_id)
            .all()
        }
        if "admin" in current and "admin" not in requested:
            admin_role = db.query(Role).filter(Role.name == "admin").first()
            admin_count = (
                db.query(UserRole)
                .join(User, User.id == UserRole.user_id)
                .filter(UserRole.role_id == admin_role.id, User.is_active.is_(True))
                .count()
                if admin_role else 0
            )
            if admin_count <= 1:
                raise HTTPException(status_code=409, detail="不能移除最后一个管理员")
        roles = db.query(Role).filter(Role.name.in_(requested)).all()
        db.query(UserRole).filter(UserRole.user_id == user_id).delete(synchronize_session=False)
        for role in roles:
            db.add(UserRole(user_id=user_id, role_id=role.id))
        user.is_superuser = "admin" in requested
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User:
        """根据 ID 获取用户"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return user

    @staticmethod
    def list_users(
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
    ) -> dict:
        """获取用户分页列表，可按用户名或邮箱搜索。"""
        db = SessionLocal()
        try:
            query = db.query(User)
            if keyword:
                query = query.filter(
                    (User.username.ilike(f"%{keyword}%"))
                    | (User.email.ilike(f"%{keyword}%"))
                )
            total = query.count()
            users = (
                query.order_by(User.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [
                    {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "phone": user.phone,
                        "is_active": user.is_active,
                        "is_superuser": user.is_superuser,
                        "roles": [user_role.role.name for user_role in user.user_roles],
                        "last_login_at": user.last_login_at.isoformat()
                        if user.last_login_at
                        else None,
                        "created_at": user.created_at.isoformat()
                        if user.created_at
                        else None,
                    }
                    for user in users
                ],
            }
        finally:
            db.close()

    @staticmethod
    def list_roles() -> list:
        """获取系统全部角色。"""
        db = SessionLocal()
        try:
            roles = db.query(Role).all()
            return [
                {
                    "id": role.id,
                    "name": role.name,
                    "display_name": role.display_name,
                    "description": role.description,
                    "is_system": role.is_system,
                }
                for role in roles
            ]
        finally:
            db.close()

    @staticmethod
    def set_user_status(db: Session, user_id: int, is_active: bool) -> User:
        """启用/停用用户，并防止停用最后一个可用管理员。"""
        user = UserService.get_user_by_id(db, user_id)
        roles = {
            name
            for (name,) in db.query(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == user_id)
            .all()
        }
        if user.is_active and not is_active and "admin" in roles:
            admin_role = db.query(Role).filter(Role.name == "admin").first()
            active_admins = (
                db.query(UserRole)
                .join(User, User.id == UserRole.user_id)
                .filter(UserRole.role_id == admin_role.id, User.is_active.is_(True))
                .count()
                if admin_role
                else 0
            )
            if active_admins <= 1:
                raise HTTPException(status_code=409, detail="不能停用最后一个管理员")
        if not settings.DEBUG and not redis_client.ensure_available():
            raise HTTPException(status_code=503, detail="认证缓存暂时不可用，请稍后重试")
        if not is_active:
            token_version = str(uuid4())
            redis_client.set(UserService.token_version_key(user_id), token_version)
            if not settings.DEBUG and (
                not redis_client.ensure_available()
                or redis_client.get(UserService.token_version_key(user_id)) != token_version
            ):
                raise HTTPException(status_code=503, detail="认证缓存暂时不可用，请稍后重试")
        user.is_active = is_active
        db.flush()
        return user

    @staticmethod
    def update_profile(
        user_id: int,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        db: Session | None = None,
    ) -> dict:
        """更新当前用户手机号和邮箱。"""
        owns_session = db is None
        db = db or SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="用户不存在")
            if phone is not None:
                user.phone = phone
            if email is not None:
                existing = (
                    db.query(User)
                    .filter(User.email == email, User.id != user_id)
                    .first()
                )
                if existing:
                    raise HTTPException(
                        status_code=400,
                        detail="该邮箱已被其他用户使用",
                    )
                user.email = email
            if owns_session:
                db.commit()
            else:
                db.flush()
            db.refresh(user)
            logger.info("用户 %s 更新了个人信息", user.username)
            return {
                "message": "个人信息已更新",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "phone": user.phone,
                },
            }
        finally:
            if owns_session:
                db.close()

    @staticmethod
    def change_password(
        user_id: int,
        old_password: str,
        new_password: str,
        db: Session | None = None,
    ) -> dict:
        """校验旧密码后修改当前用户密码。"""
        owns_session = db is None
        db = db or SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="用户不存在")
            if not verify_password(old_password, user.hashed_password):
                raise HTTPException(status_code=400, detail="旧密码不正确")
            if not settings.DEBUG and not redis_client.ensure_available():
                raise HTTPException(status_code=503, detail="认证缓存暂时不可用，请稍后重试")
            token_version = str(uuid4())
            version_key = UserService.token_version_key(user_id)
            redis_client.set(version_key, token_version)
            if not settings.DEBUG and (
                not redis_client.ensure_available()
                or redis_client.get(version_key) != token_version
                or not redis_client.ensure_available()
            ):
                raise HTTPException(status_code=503, detail="认证缓存暂时不可用，请稍后重试")
            user.hashed_password = hash_password(new_password)
            if owns_session:
                db.commit()
            else:
                db.flush()
            logger.info("用户 %s 修改了密码", user.username)
            return {"message": "密码修改成功"}
        finally:
            if owns_session:
                db.close()


# 全局单例
user_service = UserService()
