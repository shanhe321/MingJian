"""首次云部署的可选管理员初始化。"""

from sqlalchemy.exc import IntegrityError

from app.config.settings import settings
from app.core.logger import get_logger
from app.core.security import hash_password
from app.database.session import SessionLocal
from app.entity.db_models import Role, User, UserRole


logger = get_logger(__name__)


def ensure_bootstrap_admin() -> bool:
    """仅在系统不存在管理员且显式配置三项凭据时创建或提升管理员。"""
    db = SessionLocal()
    try:
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if admin_role is None:
            logger.warning("数据库尚未初始化 admin 角色，请先执行 Alembic 迁移")
            return False
        if (
            db.query(UserRole)
            .join(User, User.id == UserRole.user_id)
            .filter(UserRole.role_id == admin_role.id, User.is_active.is_(True))
            .first()
        ):
            return False

        username = settings.BOOTSTRAP_ADMIN_USERNAME.strip()
        email = settings.BOOTSTRAP_ADMIN_EMAIL.strip()
        password = settings.BOOTSTRAP_ADMIN_PASSWORD
        if not username or not email or len(password) < 8:
            logger.warning(
                "系统当前没有管理员；请配置 BOOTSTRAP_ADMIN_USERNAME/EMAIL/PASSWORD "
                "或在 backend 目录执行 python -m tools.create_admin"
            )
            return False

        user = db.query(User).filter(User.username == username).first()
        if user is None:
            user = User(
                username=username,
                email=email,
                hashed_password=hash_password(password),
                is_active=True,
                is_superuser=True,
            )
            db.add(user)
            db.flush()
        else:
            user.is_active = True
            user.is_superuser = True
        if not db.query(UserRole).filter(
            UserRole.user_id == user.id, UserRole.role_id == admin_role.id
        ).first():
            db.add(UserRole(user_id=user.id, role_id=admin_role.id))
        db.commit()
        logger.info("首次管理员已初始化: username=%s", username)
        return True
    except IntegrityError:
        db.rollback()
        logger.info("首次管理员已由另一进程完成初始化")
        return False
    finally:
        db.close()
