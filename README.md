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
