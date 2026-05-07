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
