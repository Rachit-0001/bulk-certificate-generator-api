import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (importing registers the tables with SQLAlchemy)
from app.database import Base, engine
from app.routers import certificates
from app.services import certificate_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once on startup: create the SQLite tables and output folder if missing.
    Base.metadata.create_all(bind=engine)
    certificate_service.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Bulk Certificate Generator API",
    description=(
        "Submit a list of recipients, get a job ID back immediately, "
        "and download one PDF certificate per recipient once it is generated."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(certificates.router)


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # 404 and 422 are handled by FastAPI itself; this catches real server bugs.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health", tags=["Health"], summary="Health check")
def health_check() -> dict:
    return {"status": "ok"}
