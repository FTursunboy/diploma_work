from sqlalchemy import select
from sqlalchemy.orm import Session

from database import AiRequestLog


class AiLogService:
    def __init__(self, db: Session):
        self._db = db

    def create(
        self,
        *,
        operation: str,
        status: str,
        user_id: int | None = None,
        document_id: int | None = None,
        model: str | None = None,
        request_text: str | None = None,
        response_text: str | None = None,
        error_message: str | None = None,
        prompt_tokens: int | None = None,
        total_tokens: int | None = None,
        duration_ms: int | None = None,
    ) -> AiRequestLog:
        item = AiRequestLog(
            user_id=user_id,
            document_id=document_id,
            operation=operation,
            model=model,
            request_text=request_text,
            response_text=response_text,
            status=status,
            error_message=error_message,
            prompt_tokens=prompt_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
        )
        self._db.add(item)
        self._db.commit()
        self._db.refresh(item)
        return item

    def list_logs(self, *, limit: int = 100) -> list[dict]:
        rows = self._db.scalars(select(AiRequestLog).order_by(AiRequestLog.created_at.desc(), AiRequestLog.id.desc()).limit(limit)).all()
        return [
            {
                "id": row.id,
                "user_id": row.user_id,
                "document_id": row.document_id,
                "operation": row.operation,
                "model": row.model,
                "request_text": row.request_text,
                "response_text": row.response_text,
                "status": row.status,
                "error_message": row.error_message,
                "prompt_tokens": row.prompt_tokens,
                "total_tokens": row.total_tokens,
                "duration_ms": row.duration_ms,
                "created_at": row.created_at,
            }
            for row in rows
        ]
