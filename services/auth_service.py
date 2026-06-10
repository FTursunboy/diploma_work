import re

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import AuthError, create_access_token, hash_password, verify_password
from database import User


class AuthService:
    def __init__(self, db: Session):
        self._db = db

    def _create_user(self, *, email: str, password: str, role: str) -> User:
        normalized_email = (email or "").strip().lower()
        if len(normalized_email) > 255:
            raise HTTPException(status_code=400, detail="E-mail слишком длинный.")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized_email):
            raise HTTPException(status_code=400, detail="Некорректный e-mail.")

        existing = self._db.scalar(select(User).where((User.email == normalized_email) | (User.username == normalized_email)))
        if existing is not None:
            raise HTTPException(status_code=409, detail="Пользователь с таким e-mail уже существует.")

        try:
            pwd_hash = hash_password(password)
        except AuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        user = User(username=normalized_email, email=normalized_email, password_hash=pwd_hash, role=role)
        self._db.add(user)
        self._db.commit()
        self._db.refresh(user)
        return user

    def register(self, *, email: str, password: str) -> dict:
        users_count = self._db.scalar(select(func.count(User.id)))
        role = "admin" if int(users_count or 0) == 0 else "user"
        user = self._create_user(email=email, password=password, role=role)

        token = create_access_token(user_id=user.id)
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email or user.username,
                "role": user.role,
                "created_at": user.created_at,
            },
        }

    def login(self, *, email: str, password: str) -> dict:
        normalized_email = (email or "").strip().lower()
        user = self._db.scalar(select(User).where((User.email == normalized_email) | (User.username == normalized_email)))
        if user is None or not verify_password(password or "", user.password_hash):
            raise HTTPException(status_code=401, detail="Неверный e-mail или пароль.")

        token = create_access_token(user_id=user.id)
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email or user.username,
                "role": user.role,
                "created_at": user.created_at,
            },
        }

    def list_users(self) -> list[dict]:
        users = self._db.scalars(select(User).order_by(User.created_at.desc(), User.id.desc())).all()
        return [{"id": u.id, "email": u.email or u.username, "role": u.role, "created_at": u.created_at} for u in users]

    def create_user(self, *, email: str, password: str, role: str) -> dict:
        user = self._create_user(email=email, password=password, role=role)
        return {"id": user.id, "email": user.email or user.username, "role": user.role, "created_at": user.created_at}

    def set_user_role(self, *, user_id: int, role: str) -> dict:
        user = self._db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден.")
        user.role = role
        self._db.add(user)
        self._db.commit()
        self._db.refresh(user)
        return {"id": user.id, "email": user.email or user.username, "role": user.role, "created_at": user.created_at}
