# CareerSite Agent

CareerSite Agent is a human-in-the-loop agentic AI workflow for job discovery and application operations.
It discovers entry-level roles, resolves them to the company's original career posting, scores resume-job fit,
triggers truthful resume tailoring when needed, tracks opportunities, and surfaces recruiter contacts.

## Tech stack
- Python
- FastAPI
- n8n
- React + Vite
- Google Sheets API (optional)
- browser-assisted autofill extension

## Current scope
This repository is a build-ready scaffold with:
- FastAPI endpoints for jobs, resume scoring, contacts, and tracking
- modular services for scoring, tailoring, parsing, and canonicalization
- a structured master resume JSON
- a profile-aware job quality gate for target roles, junior experience level, relocation, and work authorization constraints
- tailored resume and apply-plan generation for reusable form-fill profile data
- local `Profile/` project-knowledge ingestion for tailoring instructions, base resume, and research/project evidence with credential redaction
- resume draft HTML/DOCX/PDF artifacts, form-fill checklist, JD text, and recruiter outreach draft
- sample job descriptions
- importable n8n workflow exports in `n8n/workflows`
- React daily job-discovery cockpit in `frontend`
- tests and project docs

## High-level workflow
1. Discover jobs from multiple sources
2. Resolve each listing to the official company posting
3. Parse the official JD into structured JSON
4. Apply the job quality gate for title fit, experience level, work authorization blockers, citizenship/clearance exclusions, and relocation preferences
5. Score base resume against the JD
6. Tailor resume when score is between 65 and 84
7. Build a tailored resume/apply-plan artifact with form-fill profile facts
8. Export local artifacts for approved/actionable leads
9. Present recommendation for approval
10. Log to tracker
11. Find recruiter contacts and draft outreach

## Run locally

### Run both at once
After the one-time setup below, launch the backend and frontend together.

Windows (PowerShell), each server in its own window:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
```
Flags: `-NoFrontend`, `-NoBackend`, `-NoReload`, `-BackendPort <n>`, `-FrontendPort <n>`.
The launcher uses the project `.venv` Python and falls back to a local Vite install if `npm` is not on PATH.

macOS/Linux runs the backend only:
```bash
bash scripts/run_local.sh
```

### Backend
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

FastAPI docs:
- `http://127.0.0.1:8000/docs`

### React app
```bash
cd frontend
npm install
npm run dev
```

- `http://127.0.0.1:5173`

The Vite dev server proxies API calls to the backend on port 8000 (the same port the n8n workflows use), so start the backend too whenever you use the job feeds, JD analysis, or log-to-Sheets actions.

n8n workflow exports:
- `n8n/workflows/WF1_Manual_FastAPI_Discord_Test.json`
- `n8n/workflows/WF2_Incoming_Job_Lead_Processor.json`
- `n8n/workflows/WF3_Confirmed_Application_To_Sheets.json`
- `n8n/workflows/WF4_Gmail_Status_Monitor.json`
- `n8n/workflows/WF5_Email_Backfill_Scanner.json`
- `n8n/workflows/WF6_Queue_Worker_Scheduler.json`
- `n8n/workflows/WF7_Career_Agent_Orchestrator.json`

Agent endpoints:
- `GET /agents/capabilities`
- `POST /agents/discover-jobs`
- `POST /agents/score-fit`
- `POST /agents/tailor-resume`
- `POST /agents/autofill`
- `POST /agents/recruiter-outreach`
- `POST /agents/track-email`
- `POST /agents/run-pipeline`

Manual application loop endpoints:
- `POST /copilot/analyze-jd`
- `POST /copilot/prepare-log`
- `POST /copilot/confirm-log`
- `POST /application-loop/batches`
- `GET /application-loop/items`
- `POST /application-loop/fit-gate`
- `PUT /application-loop/items/{loop_id}/jd`
- `POST /application-loop/items/{loop_id}/fit-override`
- `POST /application-loop/items/{loop_id}/tailoring/drafts`
- `GET /application-loop/items/{loop_id}/tailoring/draft`
- `POST /application-loop/items/{loop_id}/tailoring/preview`
- `POST /application-loop/items/{loop_id}/tailoring/approve`
- `POST /application-loop/items/{loop_id}/tailoring/export`
- `GET /application-loop/items/{loop_id}/tailoring/export`
- `GET /application-loop/items/{loop_id}/tailoring/download/{docx|pdf}`

Agent CLI:
```bash
python scripts/run_career_agents.py discover --use-llm --max-enqueue 10
python scripts/run_career_agents.py pipeline --use-llm --process-limit 5 --render-pdf
```

Google Apps Script source:
- `google_cloud/Code.gs`

Email status reasoning rules:
- `data/email_status_rules.json`

Job search and application profile configuration:
- `data/job_search_profile.json`
- `data/application_profile.json`
- `Profile/Instructions.txt` and `Profile/* Summary.txt` for local tailoring evidence

Production readiness check:
```bash
python scripts/check_production_readiness.py
```

Daily production process:
- `docs/production_runbook.md`

Agent architecture:
- `docs/agent_architecture.md`

Loop-engineering mini-project map:
- `docs/loop_engineering_mini_projects.md`

## Project status
Ongoing. This scaffold is intentionally modular so each service can be upgraded without changing the full architecture.
