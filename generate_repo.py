from pathlib import Path
import json, textwrap

root = Path('/mnt/data/career-site-agent')
files = {}

def add(path, content):
    files[path] = textwrap.dedent(content).lstrip('\n')

add('README.md', '''
# CareerSite Agent

CareerSite Agent is a human-in-the-loop agentic AI workflow for job discovery and application operations.
It discovers entry-level roles, resolves them to the company's original career posting, scores resume-job fit,
triggers truthful resume tailoring when needed, tracks opportunities, and surfaces recruiter contacts.

## Tech stack
- Python
- FastAPI
- n8n
- Streamlit
- Google Sheets API (optional)
- Playwright (optional, later phase)

## Current scope
This repository is a build-ready scaffold with:
- FastAPI endpoints for jobs, resume scoring, contacts, and tracking
- modular services for scoring, tailoring, parsing, and canonicalization
- a structured master resume JSON
- sample job descriptions
- starter n8n workflow exports
- starter Streamlit demo UI
- tests and project docs

## High-level workflow
1. Discover jobs from multiple sources
2. Resolve each listing to the official company posting
3. Parse the official JD into structured JSON
4. Score base resume against the JD
5. Tailor resume when score is between 65 and 84
6. Present recommendation for approval
7. Log to tracker
8. Find recruiter contacts and draft outreach

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

FastAPI docs:
- `http://127.0.0.1:8000/docs`

Streamlit demo:
```bash
streamlit run ui/streamlit_app.py
```

## Project status
Ongoing. This scaffold is intentionally modular so each service can be upgraded without changing the full architecture.
''')

add('LICENSE', '''
MIT License

Copyright (c) 2026 Akhilesh A. Kumbhar

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
''')

add('.gitignore', '''
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.env
.pytest_cache/
.coverage
htmlcov/
.DS_Store
.vscode/
.idea/
*.log
data/outputs/*
!data/outputs/.gitkeep
ui/.streamlit/
''')

add('.env.example', '''
APP_NAME=CareerSite Agent
APP_ENV=development
APP_DEBUG=true
APP_HOST=0.0.0.0
APP_PORT=8000
LLM_PROVIDER=mock
OPENAI_API_KEY=
GOOGLE_SHEETS_SPREADSHEET_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8501
''')

add('requirements.txt', '''
fastapi
uvicorn[standard]
pydantic>=2
pydantic-settings
python-dotenv
httpx
jinja2
streamlit
pytest
pytest-cov
''')

add('docker-compose.yml', '''
version: "3.9"
services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
''')

add('Dockerfile', '''
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
''')

add('app/main.py', '''
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import jobs, resume, contacts, tracker, health
from app.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")

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
''')

add('app/config.py', '''
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CareerSite Agent"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    llm_provider: str = "mock"
    openai_api_key: str = ""
    google_sheets_spreadsheet_id: str = ""
    google_service_account_json: str = ""
    allowed_origins_raw: str = "http://localhost:3000,http://localhost:8501"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins_raw.split(",") if origin.strip()]


settings = Settings()
''')

add('app/dependencies.py', '''
from functools import lru_cache

from app.services.canonicalization_service import CanonicalizationService
from app.services.decision_service import DecisionService
from app.services.jd_parser_service import JDParserService
from app.services.recruiter_service import RecruiterService
from app.services.scoring_service import ScoringService
from app.services.tailoring_service import TailoringService
from app.services.tracker_service import TrackerService


@lru_cache
def get_jd_parser_service() -> JDParserService:
    return JDParserService()


@lru_cache
def get_scoring_service() -> ScoringService:
    return ScoringService()


@lru_cache
def get_tailoring_service() -> TailoringService:
    return TailoringService()


@lru_cache
def get_decision_service() -> DecisionService:
    return DecisionService()


@lru_cache
def get_canonicalization_service() -> CanonicalizationService:
    return CanonicalizationService()


@lru_cache
def get_recruiter_service() -> RecruiterService:
    return RecruiterService()


@lru_cache
def get_tracker_service() -> TrackerService:
    return TrackerService()
''')

add('app/api/__init__.py', '')
add('app/api/health.py', '''
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok", "service": "CareerSite Agent"}
''')

add('app/api/jobs.py', '''
from fastapi import APIRouter, Depends

from app.dependencies import get_canonicalization_service, get_jd_parser_service
from app.schemas.job import JobLead, OfficialJobResolutionRequest, OfficialJobResolutionResponse, JDParseRequest, ParsedJD
from app.services.canonicalization_service import CanonicalizationService
from app.services.jd_parser_service import JDParserService

router = APIRouter()


@router.post("/normalize", response_model=JobLead)
def normalize_job(job: JobLead) -> JobLead:
    job.company = job.company.strip()
    job.title = job.title.strip()
    return job


@router.post("/resolve-official", response_model=OfficialJobResolutionResponse)
def resolve_official(
    payload: OfficialJobResolutionRequest,
    service: CanonicalizationService = Depends(get_canonicalization_service),
) -> OfficialJobResolutionResponse:
    return service.resolve(payload)


@router.post("/parse-jd", response_model=ParsedJD)
def parse_jd(
    payload: JDParseRequest,
    service: JDParserService = Depends(get_jd_parser_service),
) -> ParsedJD:
    return service.parse(payload)
''')

add('app/api/resume.py', '''
from fastapi import APIRouter, Depends

from app.dependencies import get_decision_service, get_scoring_service, get_tailoring_service
from app.schemas.resume import ResumeDecisionRequest, ResumeDecisionResponse, ResumeScoreRequest, ResumeScoreResponse, ResumeTailorRequest, ResumeTailorResponse
from app.services.decision_service import DecisionService
from app.services.scoring_service import ScoringService
from app.services.tailoring_service import TailoringService

router = APIRouter()


@router.post("/score", response_model=ResumeScoreResponse)
def score_resume(
    payload: ResumeScoreRequest,
    service: ScoringService = Depends(get_scoring_service),
) -> ResumeScoreResponse:
    return service.score(payload)


@router.post("/tailor", response_model=ResumeTailorResponse)
def tailor_resume(
    payload: ResumeTailorRequest,
    service: TailoringService = Depends(get_tailoring_service),
) -> ResumeTailorResponse:
    return service.tailor(payload)


@router.post("/decide", response_model=ResumeDecisionResponse)
def decide_resume_action(
    payload: ResumeDecisionRequest,
    service: DecisionService = Depends(get_decision_service),
) -> ResumeDecisionResponse:
    return service.decide(payload)
''')

add('app/api/contacts.py', '''
from fastapi import APIRouter, Depends

from app.dependencies import get_recruiter_service
from app.schemas.contact import RecruiterLookupRequest, RecruiterLookupResponse, OutreachDraftRequest, OutreachDraftResponse
from app.services.recruiter_service import RecruiterService

router = APIRouter()


@router.post("/find-recruiter", response_model=RecruiterLookupResponse)
def find_recruiter(
    payload: RecruiterLookupRequest,
    service: RecruiterService = Depends(get_recruiter_service),
) -> RecruiterLookupResponse:
    return service.find_recruiter(payload)


@router.post("/draft-outreach", response_model=OutreachDraftResponse)
def draft_outreach(
    payload: OutreachDraftRequest,
    service: RecruiterService = Depends(get_recruiter_service),
) -> OutreachDraftResponse:
    return service.draft_outreach(payload)
''')

add('app/api/tracker.py', '''
from fastapi import APIRouter, Depends

from app.dependencies import get_tracker_service
from app.schemas.tracker import TrackerRowCreateRequest, TrackerRowResponse, TrackerStatusUpdateRequest
from app.services.tracker_service import TrackerService

router = APIRouter()


@router.post("/add-row", response_model=TrackerRowResponse)
def add_row(
    payload: TrackerRowCreateRequest,
    service: TrackerService = Depends(get_tracker_service),
) -> TrackerRowResponse:
    return service.add_row(payload)


@router.post("/update-status", response_model=TrackerRowResponse)
def update_status(
    payload: TrackerStatusUpdateRequest,
    service: TrackerService = Depends(get_tracker_service),
) -> TrackerRowResponse:
    return service.update_status(payload)
''')

add('app/schemas/__init__.py', '')
add('app/schemas/common.py', '''
from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    message: str = Field(..., description="Human-readable response message")
''')

add('app/schemas/job.py', '''
from typing import Optional
from pydantic import BaseModel, Field


class JobLead(BaseModel):
    company: str
    title: str
    discovered_url: str
    source: str
    location: Optional[str] = None
    posted_date: Optional[str] = None


class OfficialJobResolutionRequest(BaseModel):
    company: str
    title: str
    discovered_url: str
    source: str


class OfficialJobResolutionResponse(BaseModel):
    canonical_job_id: str
    official_url: str
    ats_type: str
    status: str
    confidence: float = Field(ge=0.0, le=1.0)


class JDParseRequest(BaseModel):
    job_id: str
    title: str
    company: str
    official_url: Optional[str] = None
    jd_text: str


class ParsedJD(BaseModel):
    job_id: str
    company: str
    title: str
    required_skills: list[str]
    preferred_skills: list[str]
    years_required: Optional[str] = None
    education: Optional[str] = None
    responsibilities: list[str]
    keywords: list[str]
    constraints: list[str]
''')

add('app/schemas/resume.py', '''
from typing import Optional
from pydantic import BaseModel

from app.schemas.job import ParsedJD


class ResumeScoreRequest(BaseModel):
    job_id: str
    resume_version: str = "base_resume_v1"
    parsed_jd: ParsedJD


class ResumeScoreResponse(BaseModel):
    job_id: str
    resume_version: str
    overall_score: int
    required_skills_score: int
    preferred_skills_score: int
    experience_score: int
    education_score: int
    domain_score: int
    constraints_score: int
    missing_items: list[str]
    matched_skills: list[str]
    recommendation: str


class ResumeTailorRequest(BaseModel):
    job_id: str
    resume_version: str = "base_resume_v1"
    parsed_jd: ParsedJD
    current_score: int


class ResumeTailorResponse(BaseModel):
    job_id: str
    source_resume_version: str
    tailored_resume_version: str
    changes_summary: list[str]
    tailored_score: int
    selected_project_ids: list[str]


class ResumeDecisionRequest(BaseModel):
    job_id: str
    base_score: int
    tailored_score: Optional[int] = None


class ResumeDecisionResponse(BaseModel):
    job_id: str
    decision: str
    reason: str
''')

add('app/schemas/contact.py', '''
from typing import Optional
from pydantic import BaseModel


class RecruiterLookupRequest(BaseModel):
    company: str
    title: str
    location: Optional[str] = None


class RecruiterContact(BaseModel):
    name: str
    role: str
    source: str
    profile_url: str
    confidence: float


class RecruiterLookupResponse(BaseModel):
    company: str
    contacts: list[RecruiterContact]


class OutreachDraftRequest(BaseModel):
    company: str
    title: str
    recruiter_name: str


class OutreachDraftResponse(BaseModel):
    subject: str
    body: str
''')

add('app/schemas/tracker.py', '''
from typing import Optional
from pydantic import BaseModel


class TrackerRowCreateRequest(BaseModel):
    company: str
    role: str
    found_via: str
    official_link: str
    status: str = "identified"
    base_match_percent: Optional[int] = None
    tailored_match_percent: Optional[int] = None
    resume_version_used: Optional[str] = None
    notes: Optional[str] = None


class TrackerStatusUpdateRequest(BaseModel):
    company: str
    role: str
    status: str
    notes: Optional[str] = None


class TrackerRowResponse(BaseModel):
    company: str
    role: str
    status: str
    message: str
''')

add('app/services/__init__.py', '')
add('app/services/discovery_service.py', '''
from app.schemas.job import JobLead


class DiscoveryService:
    def normalize(self, job: JobLead) -> JobLead:
        return JobLead(
            company=job.company.strip(),
            title=job.title.strip(),
            discovered_url=job.discovered_url.strip(),
            source=job.source.strip(),
            location=job.location,
            posted_date=job.posted_date,
        )
''')

add('app/services/canonicalization_service.py', '''
from urllib.parse import urlparse

from app.schemas.job import OfficialJobResolutionRequest, OfficialJobResolutionResponse


class CanonicalizationService:
    def resolve(self, payload: OfficialJobResolutionRequest) -> OfficialJobResolutionResponse:
        parsed = urlparse(payload.discovered_url)
        ats_type = self._infer_ats_type(parsed.netloc)
        canonical_job_id = f"{payload.company}_{payload.title}".lower().replace(" ", "_").replace("/", "_")

        official_url = payload.discovered_url
        if "linkedin" in parsed.netloc or "jobright" in parsed.netloc:
            official_url = f"https://careers.{payload.company.lower().replace(' ', '')}.com"

        return OfficialJobResolutionResponse(
            canonical_job_id=canonical_job_id,
            official_url=official_url,
            ats_type=ats_type,
            status="live",
            confidence=0.82,
        )

    @staticmethod
    def _infer_ats_type(host: str) -> str:
        host = host.lower()
        if "greenhouse" in host:
            return "greenhouse"
        if "lever" in host:
            return "lever"
        if "ashby" in host:
            return "ashby"
        return "career_site"
''')

add('app/services/jd_parser_service.py', '''
import re

from app.schemas.job import JDParseRequest, ParsedJD


COMMON_SKILLS = [
    "python", "sql", "machine learning", "deep learning", "fastapi", "aws",
    "docker", "pandas", "scikit-learn", "pytorch", "tensorflow", "llm", "rag",
    "nlp", "computer vision", "streamlit", "power bi", "api", "statistics"
]


class JDParserService:
    def parse(self, payload: JDParseRequest) -> ParsedJD:
        text = payload.jd_text.lower()
        found_skills = [skill for skill in COMMON_SKILLS if skill in text]
        required = found_skills[: max(1, min(6, len(found_skills)))]
        preferred = found_skills[max(1, len(found_skills)//2):]
        responsibilities = self._extract_bullets(payload.jd_text)
        keywords = sorted(set(found_skills + self._extract_keywords(text)))
        years_required = self._extract_years(payload.jd_text)
        education = self._extract_education(text)
        constraints = self._extract_constraints(text)

        return ParsedJD(
            job_id=payload.job_id,
            company=payload.company,
            title=payload.title,
            required_skills=required,
            preferred_skills=preferred,
            years_required=years_required,
            education=education,
            responsibilities=responsibilities,
            keywords=keywords,
            constraints=constraints,
        )

    @staticmethod
    def _extract_bullets(text: str) -> list[str]:
        lines = [line.strip('-• \t') for line in text.splitlines() if line.strip()]
        return lines[:8]

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        phrases = []
        for phrase in ["entry level", "new grad", "1+ years", "communication", "experimentation", "deployment"]:
            if phrase in text:
                phrases.append(phrase)
        return phrases

    @staticmethod
    def _extract_years(text: str) -> str | None:
        match = re.search(r"(\d+\+?\s+years?)", text, flags=re.IGNORECASE)
        return match.group(1) if match else None

    @staticmethod
    def _extract_education(text: str) -> str | None:
        if "master" in text:
            return "master's"
        if "bachelor" in text:
            return "bachelor's"
        return None

    @staticmethod
    def _extract_constraints(text: str) -> list[str]:
        constraints = []
        for phrase in ["visa", "sponsorship", "hybrid", "remote", "onsite", "relocation"]:
            if phrase in text:
                constraints.append(phrase)
        return constraints
''')

add('app/services/scoring_service.py', '''
import json
from pathlib import Path

from app.core.score_calculator import weighted_score
from app.core.skill_mapper import normalize_skills
from app.schemas.resume import ResumeScoreRequest, ResumeScoreResponse


class ScoringService:
    def __init__(self) -> None:
        self.master_resume = self._load_master_resume()

    def score(self, payload: ResumeScoreRequest) -> ResumeScoreResponse:
        resume_skills = self._flatten_resume_skills()
        jd_required = normalize_skills(payload.parsed_jd.required_skills)
        jd_preferred = normalize_skills(payload.parsed_jd.preferred_skills)

        matched_required = [skill for skill in jd_required if skill in resume_skills]
        matched_preferred = [skill for skill in jd_preferred if skill in resume_skills]
        missing_items = [skill for skill in jd_required if skill not in resume_skills]

        required_score = self._ratio_score(len(matched_required), len(jd_required))
        preferred_score = self._ratio_score(len(matched_preferred), len(jd_preferred))
        experience_score = self._experience_score(payload.parsed_jd.keywords)
        education_score = 95
        domain_score = self._domain_score(payload.parsed_jd.title)
        constraints_score = 100

        overall = weighted_score(
            required_skills_score=required_score,
            preferred_skills_score=preferred_score,
            experience_score=experience_score,
            education_score=education_score,
            domain_score=domain_score,
            constraints_score=constraints_score,
        )

        recommendation = "apply_now" if overall >= 85 else "tailor_resume" if overall >= 65 else "manual_review"

        return ResumeScoreResponse(
            job_id=payload.job_id,
            resume_version=payload.resume_version,
            overall_score=overall,
            required_skills_score=required_score,
            preferred_skills_score=preferred_score,
            experience_score=experience_score,
            education_score=education_score,
            domain_score=domain_score,
            constraints_score=constraints_score,
            missing_items=missing_items,
            matched_skills=sorted(set(matched_required + matched_preferred)),
            recommendation=recommendation,
        )

    @staticmethod
    def _ratio_score(matched: int, total: int) -> int:
        if total <= 0:
            return 80
        return round((matched / total) * 100)

    def _experience_score(self, keywords: list[str]) -> int:
        project_tags = {tag for project in self.master_resume.get("projects", []) for tag in project.get("tags", [])}
        overlap = len([key for key in keywords if key in project_tags])
        return min(95, 60 + overlap * 8)

    def _domain_score(self, title: str) -> int:
        lowered = title.lower()
        if any(token in lowered for token in ["ai", "ml", "machine learning", "data scientist"]):
            return 90
        return 75

    def _flatten_resume_skills(self) -> set[str]:
        skills = set()
        for value in self.master_resume.get("skills", {}).values():
            for item in value:
                skills.add(item.lower())
        for project in self.master_resume.get("projects", []):
            for tag in project.get("tags", []):
                skills.add(tag.lower())
            for tech in project.get("tech_stack", []):
                skills.add(tech.lower())
        return skills

    @staticmethod
    def _load_master_resume() -> dict:
        path = Path("data/master_resume/master_resume.json")
        return json.loads(path.read_text())
''')

add('app/services/tailoring_service.py', '''
import json
from pathlib import Path

from app.schemas.resume import ResumeTailorRequest, ResumeTailorResponse


class TailoringService:
    def __init__(self) -> None:
        self.master_resume = json.loads(Path("data/master_resume/master_resume.json").read_text())

    def tailor(self, payload: ResumeTailorRequest) -> ResumeTailorResponse:
        target_keywords = {item.lower() for item in payload.parsed_jd.required_skills + payload.parsed_jd.preferred_skills}
        ranked_projects = []
        for project in self.master_resume.get("projects", []):
            tags = {tag.lower() for tag in project.get("tags", [])}
            score = len(tags.intersection(target_keywords))
            ranked_projects.append((score, project["id"]))
        ranked_projects.sort(reverse=True)
        selected = [project_id for score, project_id in ranked_projects[:3] if score >= 0]
        tailored_score = min(95, payload.current_score + 10)

        changes = [
            "Updated summary variant to align with role intent.",
            "Reordered projects to prioritize the most relevant project experience.",
            "Rewrote selected bullets using JD-aligned terminology without changing facts.",
        ]

        return ResumeTailorResponse(
            job_id=payload.job_id,
            source_resume_version=payload.resume_version,
            tailored_resume_version=f"{payload.job_id}_tailored_v1",
            changes_summary=changes,
            tailored_score=tailored_score,
            selected_project_ids=selected,
        )
''')

add('app/services/decision_service.py', '''
from app.schemas.resume import ResumeDecisionRequest, ResumeDecisionResponse


class DecisionService:
    def decide(self, payload: ResumeDecisionRequest) -> ResumeDecisionResponse:
        final_score = payload.tailored_score if payload.tailored_score is not None else payload.base_score

        if final_score >= 85:
            return ResumeDecisionResponse(job_id=payload.job_id, decision="apply_now", reason="Fit score meets the apply threshold.")
        if 65 <= final_score < 85:
            return ResumeDecisionResponse(job_id=payload.job_id, decision="manual_review", reason="Role may be salvageable, but still needs review.")
        return ResumeDecisionResponse(job_id=payload.job_id, decision="reject", reason="Fit score is too low for a targeted application.")
''')

add('app/services/recruiter_service.py', '''
from app.schemas.contact import (
    OutreachDraftRequest,
    OutreachDraftResponse,
    RecruiterContact,
    RecruiterLookupRequest,
    RecruiterLookupResponse,
)


class RecruiterService:
    def find_recruiter(self, payload: RecruiterLookupRequest) -> RecruiterLookupResponse:
        contacts = [
            RecruiterContact(
                name=f"{payload.company} Talent Acquisition",
                role="Talent Acquisition",
                source="company careers page",
                profile_url=f"https://www.linkedin.com/search/results/people/?keywords={payload.company}%20recruiter",
                confidence=0.55,
            )
        ]
        return RecruiterLookupResponse(company=payload.company, contacts=contacts)

    def draft_outreach(self, payload: OutreachDraftRequest) -> OutreachDraftResponse:
        subject = f"Interest in {payload.title} at {payload.company}"
        body = (
            f"Hi {payload.recruiter_name},\n\n"
            f"I recently came across the {payload.title} role at {payload.company} and wanted to reach out. "
            "My background includes applied machine learning, analytics, and deployment-focused AI systems. "
            "I would value the opportunity to learn more about what the team is looking for in strong candidates.\n\n"
            "Best regards,\nAkhilesh Kumbhar"
        )
        return OutreachDraftResponse(subject=subject, body=body)
''')

add('app/services/tracker_service.py', '''
from app.schemas.tracker import TrackerRowCreateRequest, TrackerRowResponse, TrackerStatusUpdateRequest


class TrackerService:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict] = {}

    def add_row(self, payload: TrackerRowCreateRequest) -> TrackerRowResponse:
        key = (payload.company, payload.role)
        self._store[key] = payload.model_dump()
        return TrackerRowResponse(
            company=payload.company,
            role=payload.role,
            status=payload.status,
            message="Tracker row added locally. Replace with Google Sheets integration later.",
        )

    def update_status(self, payload: TrackerStatusUpdateRequest) -> TrackerRowResponse:
        key = (payload.company, payload.role)
        current = self._store.get(key, {"company": payload.company, "role": payload.role})
        current["status"] = payload.status
        current["notes"] = payload.notes
        self._store[key] = current
        return TrackerRowResponse(
            company=payload.company,
            role=payload.role,
            status=payload.status,
            message="Tracker status updated locally. Replace with Google Sheets integration later.",
        )
''')

add('app/services/resume_render_service.py', '''
from pathlib import Path
from jinja2 import Template


class ResumeRenderService:
    def render_html(self, output_path: str, candidate: dict, selected_projects: list[dict]) -> str:
        template_path = Path("templates/resume_template.html")
        template = Template(template_path.read_text())
        rendered = template.render(candidate=candidate, projects=selected_projects)
        Path(output_path).write_text(rendered)
        return output_path
''')

add('app/clients/__init__.py', '')
add('app/clients/llm_client.py', '''
class LLMClient:
    def complete(self, prompt: str) -> str:
        return f"MOCK_RESPONSE: {prompt[:120]}"
''')

add('app/clients/sheets_client.py', '''
class SheetsClient:
    def append_row(self, row: dict) -> dict:
        return {"status": "mocked", "row": row}
''')

add('app/clients/browser_client.py', '''
class BrowserClient:
    def open_url(self, url: str) -> dict:
        return {"status": "mocked", "url": url}
''')

add('app/clients/job_source_client.py', '''
class JobSourceClient:
    def fetch_jobs(self) -> list[dict]:
        return []
''')

add('app/core/__init__.py', '')
add('app/core/constants.py', '''
DEFAULT_APPLY_THRESHOLD = 85
DEFAULT_TAILOR_MIN = 65
''')

add('app/core/skill_mapper.py', '''
def normalize_skills(skills: list[str]) -> list[str]:
    return [skill.strip().lower() for skill in skills if skill.strip()]
''')

add('app/core/score_calculator.py', '''
def weighted_score(
    *,
    required_skills_score: int,
    preferred_skills_score: int,
    experience_score: int,
    education_score: int,
    domain_score: int,
    constraints_score: int,
) -> int:
    total = (
        required_skills_score * 0.35
        + preferred_skills_score * 0.15
        + experience_score * 0.25
        + education_score * 0.10
        + domain_score * 0.10
        + constraints_score * 0.05
    )
    return round(total)
''')

add('app/core/resume_selector.py', '''
def select_summary_variant(title: str) -> str:
    lowered = title.lower()
    if "data scientist" in lowered:
        return "data_scientist"
    if "machine learning" in lowered or "ml engineer" in lowered:
        return "ml_engineer"
    return "ai_engineer"
''')

add('app/core/text_cleaner.py', '''
def clean_text(text: str) -> str:
    return " ".join(text.split())
''')

add('app/core/validators.py', '''
def is_valid_score(score: int) -> bool:
    return 0 <= score <= 100
''')

add('app/core/logger.py', '''
import logging


def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO)
    return logging.getLogger(name)
''')

add('app/prompts/jd_parsing_prompt.txt', '''
Extract structured fields from the job description.
Return required skills, preferred skills, years required, education, responsibilities, and constraints.
Do not invent values not supported by the text.
''')

add('app/prompts/tailoring_prompt.txt', '''
Tailor the resume truthfully.
Allowed actions: reorder, rewrite for clarity, emphasize relevant project evidence.
Forbidden actions: invent skills, invent metrics, invent experience.
''')

add('app/prompts/outreach_prompt.txt', '''
Write a short recruiter outreach message.
Keep the tone professional and specific to the role.
Do not overclaim qualifications.
''')

add('app/prompts/evaluation_prompt.txt', '''
Evaluate whether the generated score explanation matches the underlying structured evidence.
Flag unsupported claims.
''')

# data files
master_resume = {
  "candidate": {
    "full_name": "Akhilesh A. Kumbhar",
    "location": "Arlington, TX",
    "email": "akhileshkumbhar0405@gmail.com",
    "phone": "+1(346)592-3971",
    "headline": "Data Scientist and Machine Learning Engineer",
    "base_summary": "Data Scientist and Machine Learning Engineer with 1+ years of experience building end-to-end ML systems, from data modeling and experimentation to scalable cloud-based inference. Delivered production-ready solutions across recommender systems, RAG-based analytics, time-series forecasting, and computer vision, with a strong focus on performance, latency optimization, and real-world impact. Skilled in translating complex data into interpretable insights that drive measurable business outcomes."
  },
  "summary_variants": {
    "data_scientist": "Data Scientist with 1+ years of experience building end-to-end machine learning and analytics solutions across recommender systems, forecasting, healthcare data, and decision-support applications.",
    "ml_engineer": "Machine Learning Engineer with 1+ years of experience building and deploying end-to-end ML systems across recommender systems, computer vision, forecasting, and cloud-based inference.",
    "ai_engineer": "AI Engineer with experience building applied AI systems spanning RAG-based analytics, recommendation engines, forecasting pipelines, and computer vision applications."
  },
  "education": [
    {"degree": "Master of Science in Data Science", "institution": "University of Texas at Arlington", "expected_graduation": "May 2026", "gpa": "3.89"},
    {"degree": "Bachelor of Engineering in Electronics and Communications", "institution": "KLE Technological University", "gpa": "7.56"}
  ],
  "skills": {
    "programming_languages": ["Python", "SQL", "Java", "MATLAB", "HTML", "CSS"],
    "machine_learning_and_ai": ["Scikit-learn", "NumPy", "Pandas", "PyTorch", "TensorFlow", "Time Series Forecasting", "Computer Vision", "Recommender Systems", "RAG", "Prompt Engineering", "LangChain"],
    "data_visualization": ["Power BI"],
    "databases": ["SQL", "MySQL"],
    "cloud": ["AWS EC2"],
    "tools": ["BeautifulSoup", "Selenium", "Streamlit", "OpenCV", "ByteTrack", "Prophet", "SentenceTransformers"],
    "ai_tools": ["ChatGPT", "Llama"]
  },
  "projects": [
    {"id": "otto_recommender", "name": "OTTO Session-Based Recommender System", "tags": ["recommender_systems", "ranking", "feature_engineering", "streamlit", "deployment", "inference_optimization"], "tech_stack": ["Python", "Pandas", "Scikit-learn", "Streamlit"], "bullets": ["Built a two-stage recommendation pipeline for next-item interaction prediction.", "Engineered behavioral features for low-latency inference.", "Deployed a Streamlit UI on Hugging Face Spaces."]},
    {"id": "erev_copilot", "name": "EREV Copilot - EV Range Analytics RAG Dashboard", "tags": ["rag", "llm", "retrieval", "analytics", "streamlit", "aws", "deployment", "latency_optimization", "decision_support"], "tech_stack": ["RAG", "Llama", "SentenceTransformers", "Streamlit", "AWS EC2"], "bullets": ["Developed retrieval-augmented analytics over EV-VMT reports.", "Optimized chunking, embeddings, and prompt design for CPU-only deployment.", "Built a multi-tab dashboard for scenario analysis."]},
    {"id": "traffic_analysis_tta", "name": "Vehicle Corridor Traffic Analysis with Test-Time Domain Adaptation", "tags": ["computer_vision", "object_detection", "tracking", "domain_adaptation", "edge_ai", "latency", "deployment_evaluation"], "tech_stack": ["YOLOv8n", "ByteTrack", "PyTorch", "OpenCV"], "bullets": ["Fine-tuned YOLOv8n on VisDrone.", "Built an end-to-end traffic analytics pipeline.", "Evaluated GPU and CPU deployment performance."]},
    {"id": "cocoa_leaf_disease", "name": "Cocoa Leaf Disease Detection using Deep Learning", "tags": ["computer_vision", "deep_learning", "semi_supervised_learning", "streamlit", "diagnostic_ai", "mobile_inference"], "tech_stack": ["TensorFlow", "Keras", "EfficientNet-B0", "Streamlit"], "bullets": ["Built a disease classification pipeline with pseudo-labeling.", "Developed a real-time diagnostic web app.", "Optimized inference for low-resource environments."]},
    {"id": "water_usage_forecasting", "name": "Water Usage Forecasting with Time-Series Modeling", "tags": ["time_series", "forecasting", "model_selection", "aws", "deployment", "evaluation"], "tech_stack": ["Prophet", "Scikit-learn", "AWS EC2"], "bullets": ["Implemented a forecasting workflow with validation and diagnostics.", "Selected a stable production model.", "Deployed on EC2 for on-demand inference."]}
  ]
}

add('data/master_resume/master_resume.json', json.dumps(master_resume, indent=2))

skill_taxonomy = {
    "python": ["python"],
    "machine learning": ["ml", "machine learning"],
    "llm": ["llm", "large language model", "language model"],
    "rag": ["rag", "retrieval augmented generation", "retrieval-augmented generation"],
    "computer vision": ["computer vision", "cv", "object detection"],
    "forecasting": ["forecasting", "time series", "prophet"],
    "deployment": ["deployment", "aws ec2", "streamlit", "fastapi"],
}
add('data/master_resume/skill_taxonomy.json', json.dumps(skill_taxonomy, indent=2))

role_profiles = {
    "data_scientist": {"priority_tags": ["analytics", "forecasting", "experimentation", "statistics"]},
    "ml_engineer": {"priority_tags": ["deployment", "latency", "pipelines", "evaluation"]},
    "ai_engineer": {"priority_tags": ["rag", "llm", "tool_use", "workflow_automation"]},
}
add('data/master_resume/role_profiles.json', json.dumps(role_profiles, indent=2))

bullet_bank = {
    "deployment": [
        "Optimized model and pipeline behavior for constrained deployment environments.",
        "Built user-facing interfaces around inference workflows."
    ],
    "analytics": [
        "Translated technical outputs into decision-support insights.",
        "Used evaluation metrics to guide practical model selection."
    ]
}
add('data/master_resume/bullet_bank.json', json.dumps(bullet_bank, indent=2))

for i, sample in enumerate([
    {
        "job_id": "sample_ds_001",
        "company": "ExampleAI",
        "title": "Entry-Level Data Scientist",
        "jd_text": "Bachelor's or Master's degree in Data Science, Computer Science, or related field. 1+ years of experience in Python, SQL, machine learning, and experimentation. Preferred: AWS, Power BI, deployment exposure."
    },
    {
        "job_id": "sample_mle_001",
        "company": "DeployML",
        "title": "Machine Learning Engineer I",
        "jd_text": "Looking for 1+ years of experience with Python, scikit-learn, PyTorch, FastAPI, Docker, and AWS. Experience deploying ML systems is a plus."
    },
    {
        "job_id": "sample_ai_001",
        "company": "AgentWorks",
        "title": "AI Engineer",
        "jd_text": "Build AI workflows using LLMs, RAG, APIs, and human-in-the-loop systems. Strong Python skills required. Experience with workflow automation is preferred."
    },
], start=1):
    add(f'data/sample_jobs/sample_jd_{i}.json', json.dumps(sample, indent=2))

add('data/outputs/.gitkeep', '')
add('data/outputs/tailored_resumes/.gitkeep', '')
add('data/outputs/parsed_jds/.gitkeep', '')
add('data/outputs/score_reports/.gitkeep', '')

# n8n files
add('n8n/workflows/daily_job_discovery.json', json.dumps({
    "name": "daily_job_discovery",
    "description": "Starter n8n workflow placeholder for scheduled job discovery and official-link resolution.",
    "nodes": [],
    "connections": {}
}, indent=2))
add('n8n/workflows/scoring_and_tailoring.json', json.dumps({
    "name": "scoring_and_tailoring",
    "description": "Starter n8n workflow placeholder for score -> tailor -> rescore branching.",
    "nodes": [],
    "connections": {}
}, indent=2))
add('n8n/workflows/approval_and_tracking.json', json.dumps({
    "name": "approval_and_tracking",
    "description": "Starter n8n workflow placeholder for approval gates and tracker updates.",
    "nodes": [],
    "connections": {}
}, indent=2))
add('n8n/workflows/recruiter_followup.json', json.dumps({
    "name": "recruiter_followup",
    "description": "Starter n8n workflow placeholder for recruiter discovery and outreach drafting.",
    "nodes": [],
    "connections": {}
}, indent=2))

add('n8n/docs/workflow_overview.md', '''
# n8n Workflow Overview

## 1. Daily job discovery
- Trigger on schedule
- Pull candidate job leads
- Call `/jobs/normalize`
- Call `/jobs/resolve-official`
- Filter live official postings
- Call `/jobs/parse-jd`
- Call `/resume/score`

## 2. Scoring and tailoring
- If score >= 85, queue for approval
- If 65 to 84, call `/resume/tailor`, then `/resume/decide`
- If below 65, mark for reject/manual review

## 3. Approval and tracking
- Send summary to user
- On approval, call `/tracker/add-row`
- On rejection, call `/tracker/update-status`

## 4. Recruiter follow-up
- Call `/contacts/find-recruiter`
- Call `/contacts/draft-outreach`
- Attach draft to tracker or UI
''')

add('n8n/docs/node_explanations.md', '''
# Node Explanations

- **Schedule Trigger**: starts the daily discovery workflow
- **HTTP Request**: calls FastAPI endpoints
- **IF Node**: branches by score band or approval state
- **Set Node**: shapes payloads for tracker and notifications
- **Google Sheets Node**: later replacement for mock tracker storage
''')
add('n8n/screenshots/.gitkeep', '')

# templates
add('templates/resume_template.html', '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Tailored Resume</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 40px; color: #222; }
    h1, h2 { margin-bottom: 6px; }
    ul { margin-top: 4px; }
  </style>
</head>
<body>
  <h1>{{ candidate.full_name }}</h1>
  <p>{{ candidate.headline }}</p>
  <p>{{ candidate.base_summary }}</p>

  <h2>Selected Projects</h2>
  {% for project in projects %}
  <div>
    <strong>{{ project.name }}</strong>
    <ul>
      {% for bullet in project.bullets %}
      <li>{{ bullet }}</li>
      {% endfor %}
    </ul>
  </div>
  {% endfor %}
</body>
</html>
''')

add('templates/resume_template.docx', 'Placeholder file. Replace with an actual DOCX template later.')
add('templates/outreach_email.txt', '''
Subject: Interest in {{ title }} at {{ company }}

Hi {{ recruiter_name }},

I recently came across the {{ title }} role at {{ company }} and wanted to reach out.
My background includes applied machine learning, analytics, and deployment-focused AI systems.
I would value the opportunity to learn more about what the team is looking for in strong candidates.

Best regards,
Akhilesh Kumbhar
''')

# tests
add('tests/__init__.py', '')
add('tests/test_health.py', '''
from fastapi.testclient import TestClient
from app.main import app


def test_health():
    client = TestClient(app)
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
''')

add('tests/test_jd_parser.py', '''
from app.schemas.job import JDParseRequest
from app.services.jd_parser_service import JDParserService


def test_jd_parser_extracts_required_skills():
    service = JDParserService()
    payload = JDParseRequest(
        job_id='test_job',
        title='Data Scientist',
        company='Example',
        jd_text='Need Python, SQL, machine learning, and AWS experience. Bachelor degree required.'
    )
    parsed = service.parse(payload)
    assert 'python' in parsed.required_skills
    assert parsed.education is not None
''')

add('tests/test_scoring.py', '''
from app.schemas.job import ParsedJD
from app.schemas.resume import ResumeScoreRequest
from app.services.scoring_service import ScoringService


def test_scoring_returns_valid_score():
    service = ScoringService()
    payload = ResumeScoreRequest(
        job_id='job1',
        parsed_jd=ParsedJD(
            job_id='job1',
            company='Example',
            title='AI Engineer',
            required_skills=['python', 'rag'],
            preferred_skills=['fastapi'],
            years_required='1+ years',
            education="master's",
            responsibilities=['Build AI workflows'],
            keywords=['rag', 'deployment'],
            constraints=[]
        )
    )
    result = service.score(payload)
    assert 0 <= result.overall_score <= 100
''')

add('tests/test_tailoring.py', '''
from app.schemas.job import ParsedJD
from app.schemas.resume import ResumeTailorRequest
from app.services.tailoring_service import TailoringService


def test_tailoring_increases_score():
    service = TailoringService()
    payload = ResumeTailorRequest(
        job_id='job2',
        parsed_jd=ParsedJD(
            job_id='job2',
            company='Example',
            title='Machine Learning Engineer',
            required_skills=['python', 'aws', 'deployment'],
            preferred_skills=['fastapi'],
            years_required='1+ years',
            education="master's",
            responsibilities=['Deploy ML systems'],
            keywords=['deployment', 'evaluation'],
            constraints=[]
        ),
        current_score=74
    )
    result = service.tailor(payload)
    assert result.tailored_score > payload.current_score
''')

add('tests/test_decision.py', '''
from app.schemas.resume import ResumeDecisionRequest
from app.services.decision_service import DecisionService


def test_decision_apply_now():
    service = DecisionService()
    result = service.decide(ResumeDecisionRequest(job_id='job3', base_score=88))
    assert result.decision == 'apply_now'
''')

add('tests/test_tracker.py', '''
from app.schemas.tracker import TrackerRowCreateRequest, TrackerStatusUpdateRequest
from app.services.tracker_service import TrackerService


def test_tracker_add_and_update():
    service = TrackerService()
    add_result = service.add_row(
        TrackerRowCreateRequest(
            company='Example',
            role='AI Engineer',
            found_via='Job board',
            official_link='https://careers.example.com/job1'
        )
    )
    assert add_result.status == 'identified'

    update_result = service.update_status(
        TrackerStatusUpdateRequest(company='Example', role='AI Engineer', status='applied')
    )
    assert update_result.status == 'applied'
''')

# docs
add('docs/architecture.md', '''
# Architecture

## Layers
- **Python**: business logic, scoring, tailoring, parsing, recruiter lookup helpers
- **FastAPI**: API layer exposing reusable services
- **n8n**: orchestration, scheduling, approvals, notifications, tracking
- **Streamlit**: optional demo UI

## Main flow
1. Discover jobs
2. Resolve to official career site posting
3. Parse JD
4. Score resume
5. Tailor if score is between 65 and 84
6. Decide action
7. Track opportunity
8. Find recruiter and draft outreach
''')

add('docs/api_contracts.md', '''
# API Contracts

## Jobs
- `POST /jobs/normalize`
- `POST /jobs/resolve-official`
- `POST /jobs/parse-jd`

## Resume
- `POST /resume/score`
- `POST /resume/tailor`
- `POST /resume/decide`

## Contacts
- `POST /contacts/find-recruiter`
- `POST /contacts/draft-outreach`

## Tracker
- `POST /tracker/add-row`
- `POST /tracker/update-status`
''')

add('docs/scoring_logic.md', '''
# Scoring Logic

## Weights
- Required skills: 35
- Preferred skills: 15
- Relevant experience/projects: 25
- Education alignment: 10
- Role/domain alignment: 10
- Constraints fit: 5

## Score bands
- 85 to 100: apply now
- 65 to 84: tailor then review
- below 65: reject or manual review

## Principle
The score must be grounded in structured signals and only explained by an LLM if needed.
''')

add('docs/tailoring_rules.md', '''
# Tailoring Rules

## Allowed
- reorder bullets
- prioritize relevant projects
- switch summary variant
- rewrite wording for clarity

## Forbidden
- invent skills
- invent experience
- change metrics without support
- imply production scope not present in the source resume
''')

add('docs/setup_guide.md', '''
# Setup Guide

1. Create and activate a virtual environment
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env`
4. Run API: `uvicorn app.main:app --reload`
5. Run tests: `pytest`
6. Run Streamlit demo: `streamlit run ui/streamlit_app.py`
''')

add('docs/demo_walkthrough.md', '''
# Demo Walkthrough

1. Submit a sample JD to `/jobs/parse-jd`
2. Score the master resume with `/resume/score`
3. Tailor if needed with `/resume/tailor`
4. Decide with `/resume/decide`
5. Add to tracker with `/tracker/add-row`
6. Find recruiter and draft outreach
''')

add('docs/roadmap.md', '''
# Roadmap

## Phase 1
- scoring and tailoring
- FastAPI endpoints
- sample UI

## Phase 2
- official-link resolver upgrades
- Google Sheets integration
- recruiter search improvements

## Phase 3
- n8n workflow execution
- browser-assisted application support
- evaluation dashboard
''')

# scripts
add('scripts/seed_sample_data.py', '''
from pathlib import Path
import json

sample_dir = Path('data/sample_jobs')
for path in sample_dir.glob('sample_jd_*.json'):
    data = json.loads(path.read_text())
    print(f"Loaded {data['job_id']} - {data['title']}")
''')

add('scripts/run_local.sh', '''
#!/usr/bin/env bash
set -e
uvicorn app.main:app --reload
''')

add('scripts/export_tailored_resume.py', '''
import json
from pathlib import Path

from app.services.resume_render_service import ResumeRenderService

master_resume = json.loads(Path('data/master_resume/master_resume.json').read_text())
projects = master_resume.get('projects', [])[:3]
service = ResumeRenderService()
output = service.render_html('data/outputs/tailored_resumes/sample_tailored_resume.html', master_resume['candidate'], projects)
print(f'Rendered to {output}')
''')

# UI
add('ui/streamlit_app.py', '''
import json
from pathlib import Path

import streamlit as st

from app.schemas.job import JDParseRequest
from app.schemas.resume import ResumeScoreRequest, ResumeTailorRequest
from app.services.jd_parser_service import JDParserService
from app.services.scoring_service import ScoringService
from app.services.tailoring_service import TailoringService
from ui.components.score_card import render_score_card
from ui.components.job_review_panel import render_job_review_panel
from ui.components.recruiter_panel import render_recruiter_panel

st.set_page_config(page_title='CareerSite Agent', layout='wide')
st.title('CareerSite Agent Demo')

sample_jobs = sorted(Path('data/sample_jobs').glob('sample_jd_*.json'))
selected_path = st.selectbox('Choose a sample JD', sample_jobs, format_func=lambda p: p.name)
job = json.loads(Path(selected_path).read_text())

parser = JDParserService()
scoring = ScoringService()
tailoring = TailoringService()

parsed = parser.parse(JDParseRequest(**job))
score = scoring.score(ResumeScoreRequest(job_id=job['job_id'], parsed_jd=parsed))

left, right = st.columns(2)
with left:
    render_job_review_panel(job, parsed)
with right:
    render_score_card(score)

if score.overall_score < 85 and score.overall_score >= 65:
    tailored = tailoring.tailor(ResumeTailorRequest(job_id=job['job_id'], parsed_jd=parsed, current_score=score.overall_score))
    st.subheader('Tailoring Preview')
    st.write(tailored.model_dump())

render_recruiter_panel(job['company'], job['title'])
''')

add('ui/components/score_card.py', '''
import streamlit as st


def render_score_card(score) -> None:
    st.subheader('Resume Fit Score')
    st.metric('Overall Match', f"{score.overall_score}%")
    st.write({
        'required_skills_score': score.required_skills_score,
        'preferred_skills_score': score.preferred_skills_score,
        'experience_score': score.experience_score,
        'education_score': score.education_score,
        'domain_score': score.domain_score,
        'constraints_score': score.constraints_score,
    })
    st.write('Matched Skills:', score.matched_skills)
    st.write('Missing Items:', score.missing_items)
''')

add('ui/components/job_review_panel.py', '''
import streamlit as st


def render_job_review_panel(job: dict, parsed) -> None:
    st.subheader('Job Review')
    st.write({'company': job['company'], 'title': job['title'], 'job_id': job['job_id']})
    st.write('Required Skills:', parsed.required_skills)
    st.write('Preferred Skills:', parsed.preferred_skills)
    st.write('Responsibilities:', parsed.responsibilities)
''')

add('ui/components/recruiter_panel.py', '''
import streamlit as st


def render_recruiter_panel(company: str, title: str) -> None:
    st.subheader('Recruiter Discovery')
    st.write({
        'company': company,
        'title': title,
        'note': 'Connect recruiter lookup here through the contacts API.'
    })
''')

for path, content in files.items():
    full = root / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)

print(f"Wrote {len(files)} files")
