from pathlib import Path

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

from config import load_environment

load_environment()

from database import init_db
from routers.auth import router as auth_router
from routers.documents import router as documents_router
from routers.pages import router as pages_router
from routers.search import router as search_router
from routers.tools import router as tools_router
from services.document_parser_service import resume_pending_document_jobs


app = FastAPI(title="Китобхо API")

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STATIC_DIR = WEB_DIR / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def _startup_init_db() -> None:
    init_db()
    resume_pending_document_jobs()


app.include_router(pages_router)
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(tools_router)
