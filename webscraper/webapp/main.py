"""
FastAPI application entry point for the webscraper admin frontend.

Run locally with:

    uvicorn webapp.main:app --reload

Serves:
- ``/login``  -> the login page
- ``/app``    -> the application page (tabbed sections)
- ``/api/...``-> JSON API (auth, users, roles, models, scrape)
- ``/static`` -> CSS / JS assets
"""

import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

# A signing key is required for session tokens. In production it MUST be set via
# the environment so tokens survive restarts and can't be forged. For local dev
# we fall back to an ephemeral random key (invalidates tokens on restart).
if not os.getenv("SECRET_KEY"):
    os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
    logging.getLogger("webapp").warning(
        "SECRET_KEY not set — generated an ephemeral one for this process. "
        "Set SECRET_KEY in the environment for production deployments."
    )

from .db import init_db
from .routers import auth as auth_router
from .routers import models as models_router
from .routers import roles as roles_router
from .routers import scrape as scrape_router
from .routers import users as users_router

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create schema + seed data on startup.
    init_db()
    yield


app = FastAPI(title="Webscraper Admin", lifespan=lifespan)

app.include_router(auth_router.router)
app.include_router(roles_router.router)
app.include_router(users_router.router)
app.include_router(models_router.router)
app.include_router(scrape_router.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/login")


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(_STATIC_DIR / "login.html")


@app.get("/app", include_in_schema=False)
def app_page():
    return FileResponse(_STATIC_DIR / "app.html")


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
