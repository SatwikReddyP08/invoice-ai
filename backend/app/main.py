from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.core.database import get_db
from app.api.endpoints import invoices

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API for parsing and managing invoices.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS if settings.BACKEND_CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(invoices.router, prefix="/api/v1/invoices", tags=["invoices"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the AI Invoice Processing API (Foundation Stage)"}

@app.get("/db-check")
def check_db_connection(db: Session = Depends(get_db)):
    try:
        # Simple query to ensure connection is working
        result = db.execute(text("SELECT 1")).scalar()
        return {"status": "success", "database": "connected", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
