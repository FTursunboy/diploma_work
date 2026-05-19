from pydantic import BaseModel


class FilePathRequest(BaseModel):
    file_path: str
    title: str | None = None
    author: str | None = None
    publisher: str | None = None
    publication_year: int | None = None
    doc_type: str | None = None
    bibliography: str | None = None


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RoleUpdateRequest(BaseModel):
    role: str


class SemanticSearchRequest(BaseModel):
    query: str
    document_id: int | None = None
    limit: int = 10
