from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from auth import ALL_ROLES, AuthError, ROLE_ADMIN, ROLE_MODERATOR, decode_access_token
from database import User, get_db


auth_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=401, detail="Не авторизован.")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload.get("sub") or 0)
    except (AuthError, ValueError) as exc:
        raise HTTPException(status_code=401, detail=str(exc) or "Не авторизован.") from exc

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден.")
    return user


def require_roles(*roles: str):
    allowed = {r for r in roles if r}

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Недостаточно прав.")
        return user

    return _dep


require_moderator = require_roles(ROLE_MODERATOR, ROLE_ADMIN)
require_admin = require_roles(ROLE_ADMIN)


def validate_role(role: str) -> str:
    normalized = (role or "").strip().lower()
    if normalized not in ALL_ROLES:
        raise HTTPException(status_code=400, detail=f"Недопустимая роль. Доступно: {', '.join(sorted(ALL_ROLES))}.")
    return normalized

