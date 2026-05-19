from sqlalchemy.orm import Session


class BaseSearchService:
    def __init__(self, db: Session):
        self._db = db

