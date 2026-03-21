import logging
import os
import re

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base, ensure_sqlite_schema, SessionLocal
from app.api import router
from app import crud

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()

# Load .env from backend directory
_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(_env_path)

app = FastAPI(title="Windsurf Manager", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def _sync_env_accounts():
    """Read WINDSURF_ACCOUNT_* from environment and upsert into DB."""
    accounts = []
    for key, value in sorted(os.environ.items()):
        if not re.match(r"WINDSURF_ACCOUNT_\d+$", key):
            continue
        parts = re.split(r"\s{2,}", value.strip(), maxsplit=1)
        if len(parts) != 2:
            logger.warning("Skipping %s: cannot parse email/password", key)
            continue
        accounts.append((parts[0].strip(), parts[1].strip()))

    if not accounts:
        return

    db = SessionLocal()
    try:
        created = 0
        updated = 0
        for email, password in accounts:
            existing = crud.get_account_by_email(db, email)
            if existing:
                if not existing.encrypted_password:
                    crud.update_account(db, existing.id, password=password)
                    updated += 1
            else:
                name = email.split("@")[0]
                crud.create_account(db, name=name, email=email, password=password)
                created += 1
        logger.info("Env accounts sync: %d created, %d updated (of %d total)", created, updated, len(accounts))
    finally:
        db.close()


@app.on_event("startup")
def startup_sync_accounts():
    _sync_env_accounts()


@app.get("/")
def root():
    return {"message": "Windsurf Manager API", "docs": "/docs"}
