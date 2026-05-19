from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import FileResponse


router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"


def _serve_web_page(filename: str) -> FileResponse:
    path = WEB_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Страница не найдена.")
    return FileResponse(str(path), media_type="text/html")


@router.get("/login", include_in_schema=False)
def login_page():
    return _serve_web_page("login.html")


@router.get("/register", include_in_schema=False)
def register_page():
    return _serve_web_page("register.html")


@router.get("/viewer", include_in_schema=False)
def viewer_page():
    return _serve_web_page("viewer.html")


@router.get("/admin", include_in_schema=False)
def admin_page():
    return _serve_web_page("admin.html")


@router.get("/", include_in_schema=False)
def root(request: Request):
    accept = request.headers.get("accept", "")
    index_file = WEB_DIR / "index.html"
    if "text/html" in accept and index_file.exists():
        return FileResponse(str(index_file), media_type="text/html")
    return {"message": "Book Parser API is running"}

