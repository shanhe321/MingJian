"""交互式创建或提升管理员：python -m tools.create_admin --username admin --email admin@example.com"""

import argparse
import getpass

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.entity.db_models import Role, User, UserRole


def main() -> None:
    parser = argparse.ArgumentParser(description="创建 RSOD Agent 管理员")
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = getpass.getpass("管理员密码（至少 8 位）: ")
    if len(password) < 8:
        raise SystemExit("密码至少 8 位")

    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == "admin").first()
        if role is None:
            raise SystemExit("admin 角色不存在，请先执行 alembic upgrade head")
        user = db.query(User).filter(User.username == args.username).first()
        if user is None:
            user = User(
                username=args.username,
                email=args.email,
                hashed_password=hash_password(password),
                is_active=True,
                is_superuser=True,
            )
            db.add(user)
            db.flush()
        else:
            user.hashed_password = hash_password(password)
            user.email = args.email
            user.is_active = True
            user.is_superuser = True
        if not db.query(UserRole).filter(
            UserRole.user_id == user.id, UserRole.role_id == role.id
        ).first():
            db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        print(f"管理员已就绪: {args.username}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
