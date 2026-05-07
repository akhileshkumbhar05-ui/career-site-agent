from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import jobs, resume, contacts, tracker, health
from app.config import settings
from app.db import init_db
from app.api import jobs, resume, contacts, tracker, health, pipeline

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(resume.router, prefix="/resume", tags=["resume"])
app.include_router(contacts.router, prefix="/contacts", tags=["contacts"])
app.include_router(tracker.router, prefix="/tracker", tags=["tracker"])
app.include_router(pipeline.router, prefix="/pipeline", tags=["pipeline"])