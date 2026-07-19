"""管理员审计日志查询。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.database.session import get_db
from app.entity.db_models import OperationLog

router = APIRouter(prefix="/api/audit", tags=["审计日志"])


@router.get("/logs", summary="分页筛选审计日志")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = None,
    module: str | None = None,
    action: str | None = None,
    status: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(OperationLog)
    if user_id is not None:
        query = query.filter(OperationLog.user_id == user_id)
    if module:
        query = query.filter(OperationLog.module == module)
    if action:
        query = query.filter(OperationLog.action == action)
    if status:
        query = query.filter(OperationLog.status == status)
    if start_time:
        query = query.filter(OperationLog.created_at >= start_time)
    if end_time:
        query = query.filter(OperationLog.created_at <= end_time)
    total = query.count()
    rows = query.order_by(OperationLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "username": row.username,
                "module": row.module,
                "action": row.action,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "description": row.description,
                "ip_address": row.ip_address,
                "request_method": row.request_method,
                "request_path": row.request_path,
                "status": row.status,
                "error_message": row.error_message,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }
