from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from routers.dependencies import get_current_user, require_admin, validate_role
from routers.schemas import AdminCreateUserRequest, LoginRequest, RegisterRequest, RoleUpdateRequest
from services.ai_log_service import AiLogService
from services.auth_service import AuthService


router = APIRouter()


@router.post("/auth/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    return AuthService(db).register(email=payload.email, password=payload.password)


@router.post("/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    return AuthService(db).login(email=payload.email, password=payload.password)


@router.get("/auth/me")
def me(current_user=Depends(get_current_user)) -> dict:
    return {
        "id": current_user.id,
        "email": current_user.email or current_user.username,
        "role": current_user.role,
        "created_at": current_user.created_at,
    }


@router.get("/admin/users")
def admin_list_users(db: Session = Depends(get_db), _=Depends(require_admin)) -> list[dict]:
    return AuthService(db).list_users()


@router.post("/admin/users")
def admin_create_user(
    payload: AdminCreateUserRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    role = validate_role(payload.role)
    return AuthService(db).create_user(email=payload.email, password=payload.password, role=role)


@router.put("/admin/users/{user_id}/role")
def admin_set_user_role(
    user_id: int,
    payload: RoleUpdateRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    role = validate_role(payload.role)
    return AuthService(db).set_user_role(user_id=user_id, role=role)


@router.get("/admin/ai-logs")
def admin_ai_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
) -> list[dict]:
    return AiLogService(db).list_logs(limit=min(500, max(1, int(limit or 100))))
