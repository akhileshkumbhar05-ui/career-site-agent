from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, autofill, contacts, copilot, email, health, jobs, llm, pipeline, queue, resume, tracker, webapp
from app.config import settings
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


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
app.include_router(queue.router, prefix="/queue", tags=["queue"])
app.include_router(llm.router, prefix="/llm", tags=["llm"])
app.include_router(email.router, prefix="/email", tags=["email"])
app.include_router(autofill.router, prefix="/autofill", tags=["autofill"])
app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(webapp.router, prefix="/webapp", tags=["webapp"])
app.include_router(copilot.router, prefix="/copilot", tags=["copilot"])
