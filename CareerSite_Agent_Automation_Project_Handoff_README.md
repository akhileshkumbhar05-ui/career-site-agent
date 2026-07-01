# CareerSite Agent Automation — Project Handoff README

> **Purpose of this README:** This handoff document captures the known project context for the **CareerSite Agent Automation** project so a new AI assistant, developer, or collaborator can continue the work without losing context.
>
> **Important accuracy note:** This README is exhaustive based on the available project memory, current conversation context, and searchable uploaded files. However, not every full source file from the local repository was available in the accessible context. Where exact full code was not available, this README marks it explicitly as **NOT AVAILABLE IN ACCESSIBLE CONTEXT** instead of inventing code.

---

## 1. Project Overview

### What is this project?

**CareerSite Agent** is a human-in-the-loop agentic AI automation system for the user's personal job application workflow.

The core problem it solves is that the user manually spends time every day:

1. Opening Jobright.ai or other job discovery sources.
2. Opening a job post.
3. Clicking the original / official company job posting link.
4. Copying the official link into a Google Sheets tracker.
5. Filling tracker fields manually:
   - Company Applied
   - Role
   - Salary Quoted while Applying
   - Job Posted On
   - Applied Using
   - Status
   - Link
6. Clicking Apply on the company's official career page.
7. Uploading resume and manually completing ATS forms.
8. Confirming application submission.
9. Finding LinkedIn recruiters or hiring managers from the company.
10. Sending connection requests or post-connection messages.
11. Checking email daily for company notifications.
12. Updating application statuses in the tracker.

CareerSite Agent is being built to reduce this manual bookkeeping and decision-work while keeping the user in control of actual applications.

### What problem does it solve?

It solves the following problems:

- Too much repetitive job application tracking.
- Losing track of which company, role, link, and status belong together.
- Manually copying job data from job boards into Google Sheets.
- Manually deciding whether a job is worth applying to.
- Manually parsing JDs for required skills and missing skills.
- Manually preparing resume tailoring guidance.
- Manually finding recruiters / hiring managers after applying.
- Manually checking email and updating application statuses.
- Avoiding unreliable full automation that could submit incorrect applications.

### End goal / final deliverable

The final deliverable is a working local automation system that supports this workflow:

1. **Job discovery**
   - Pull jobs from sources such as Jobright.ai, official ATS/career sites, Greenhouse, or other configured sources.
   - Prefer official company career-site links over aggregator links.

2. **Canonicalization**
   - Resolve job postings to official company career pages.
   - Normalize company/title/link metadata.

3. **JD parsing**
   - Extract job title, company, location, required skills, preferred skills, years of experience, responsibilities, technologies, and application metadata.

4. **Scoring**
   - Score resume fit against the JD.
   - Identify matched skills and missing skills.
   - Determine whether the job should be considered strong, possible, or weak fit.

5. **Tailoring**
   - If score is below the threshold, generate resume-tailoring guidance.
   - Tailoring should be based on the user's master resume and role-specific profile.

6. **Decision routing**
   - Route job into one of the decision categories:
     - ready / good fit
     - manual review
     - reject / skip
   - Current preference: avoid hard rejection too aggressively; questionable cases should go to manual review.

7. **Human-in-the-loop assisted application**
   - User clicks **Start Apply**.
   - System opens the official company application link or provides the link/instructions.
   - User manually fills and submits the ATS form.
   - User clicks **Confirm Applied** after successful submission.

8. **Google Sheets logging**
   - After confirmation, system logs the application to the user's Google Sheets tracker.
   - The system should preserve the user's existing tracker format, dropdown values, and date-header grouping.

9. **Recruiter discovery and outreach**
   - Find LinkedIn recruiters / hiring managers / company contacts.
   - Generate short tailored LinkedIn connection notes.
   - Prepare post-connection accepted messages if applicable.

10. **Email monitoring and status updates**
   - Check email for application-related notifications.
   - Update tracker status based on emails such as rejection, screening, technical interview, HR interview, offer, etc.

### Intended user / beneficiary

The intended user is **Akhilesh Arunkumar Kumbhar**, a Master of Science in Data Science student at the University of Texas at Arlington, expected graduation May 2026, applying for Data Scientist, Machine Learning Engineer, Data Analyst, and AI/ML roles.

The project is for the user's personal job search workflow.

---

## 2. Current Status

### What phase are we in right now?

The project is in an **active implementation / integration phase**.

The high-level architecture has been decided. Several services and workflows have been built or discussed. The current focus is around:

- wiring n8n Workflow 2,
- integrating Google Sheets correctly,
- improving the assisted application flow,
- making the system operational for the user's daily workflow,
- reducing prototype churn and moving toward a polished everyday tool.

The user recently resumed n8n workflow setup and asked where to add a node in Workflow 2.

### What is fully complete?

The following are considered complete or mostly complete based on project context:

#### Completed conceptually

- Project goal and scope.
- Overall agentic workflow design.
- Decision to use a human-in-the-loop Level 2 assisted application flow.
- Decision to use **Python + FastAPI + n8n** as the core stack.
- Decision to use **Google Sheets** as the operational tracker.
- Decision to use **Discord webhook notifications** for alerts.
- Decision to prefer open-source / zero-cost LLM options where possible.
- Decision to keep official company job links as the canonical application links.
- Decision that **Link** and **Official Posting Link** are effectively the same field and should not be duplicated.
- Decision that fully autonomous application submission is not the right target right now.
- Decision to avoid spending money on LLM APIs if possible.

#### Completed or built in code/workflows

- FastAPI project structure exists.
- FastAPI routers discussed/created:
  - `jobs.py`
  - `resume.py`
  - `contacts.py`
  - `tracker.py`
  - `health.py`
- FastAPI endpoint `/pipeline/process-job` exists.
- FastAPI job-related endpoints exist:
  - `/jobs/normalize`
  - `/jobs/resolve-official`
  - `/jobs/parse-jd`
- Service dependency injection exists in `dependencies.py`.
- Service classes discussed/used:
  - `CanonicalizationService`
  - `JDParserService`
  - `ScoringService`
  - `TailoringService`
  - `DecisionService`
  - `RecruiterService`
  - `TrackerService`
- Streamlit UI exists.
- Streamlit components discussed:
  - `score_card.py`
  - `job_review_panel.py`
  - `recruiter_panel.py`
- Master resume JSON was created:
  - `data/master_resume/master_resume.json`
- Role profile / skill taxonomy work was discussed:
  - `role_profiles.json`
  - skill taxonomy updated
- n8n Workflow 1 manual test harness was built and tested with Discord.
- n8n Workflow 2 automated ingestion / webhook workflow is in progress.
- A webhook payload was tested through PowerShell.
- Greenhouse scraper path discussed:
  - `app/scrapers/ats/greenhouse_scraper.py`
- Job lead sender discussed:
  - `app/scrapers/job_lead_sender.py`
- Scripts discussed:
  - `scripts/send_job_leads.py`
  - `scripts/scrape_and_send_jobs.py`
- Target companies file discussed:
  - `data/target_companies.json`
- Google Sheets tracker exists:
  - `Qualitative Job Application Booklet`
- A testing copy exists:
  - `Qualitative Job Application Booklet – Automation Testing`
- Google Apps Script formatting logic was discussed for date headers and appending rows.

### What is partially done?

#### 1. n8n Workflow 2

Partially done.

Known intended behavior:

- Accept job lead payload through webhook.
- Call FastAPI endpoint.
- Route based on freshness / score / decision.
- Send Discord notification for viable or recent jobs.
- Send stale or uncertain jobs to manual review instead of hard rejection.
- Append job details to Google Sheets.

What remains:

- Final node placement in Workflow 2.
- Confirm whether to publish/activate Workflow 2.
- Confirm production webhook vs test webhook.
- Ensure mapped fields match the user's Google Sheet column names exactly.
- Ensure official link is used as the `Link` field.
- Verify date-header logic in Google Sheets.
- Verify repeated daily appends continue below the correct date header.
- Test with real or semi-real job payloads.

#### 2. Google Sheets tracker integration

Partially done.

Known requirements:

- Use existing tracker format.
- Preserve dropdowns.
- Add bold date header row in format:
  - `mm/dd/yyyy: MM/DD/YYYY`
- Add one blank row after the last date group if needed.
- Continue entries under an existing date header if today's header already exists.
- Append after the last application of that date.
- Use the official company job link as the `Link`.
- Avoid duplicate source/official link columns.

What remains:

- Confirm final Apps Script code or n8n Google Sheets append strategy.
- Confirm exact sheet/tab names in production and testing.
- Confirm exact column order.
- Confirm status dropdown values are respected.
- Confirm whether n8n or Apps Script owns date-header formatting.

#### 3. Streamlit UI

Partially done.

Known issues solved:

- `CanonicalizationService` method changed from `resolve_official(...)` to `resolve(payload)`.
- Streamlit UI needed update to call `resolve(payload)` using `OfficialJobResolutionRequest`.
- Save-to-tracker caused page reset because analysis outputs were only in local variables.
- Fix: store outputs in `st.session_state`.

What remains:

- Ensure Streamlit UI uses the current service signatures.
- Ensure Start Apply / Confirm Applied flow exists cleanly.
- Ensure Save-to-Tracker button does not reset state.
- Ensure Google Sheets logging is connected to the final tracker service.
- Ensure recruiter panel and outreach flow are connected after application confirmation.
- Ensure the UI reflects Level 2 assisted application flow.

#### 4. Scraping / ingestion

Partially done.

Known:

- Greenhouse scraper path exists/discussed.
- Job sender scripts exist/discussed.
- Scraper → webhook → FastAPI → tracker → Discord flow has worked at least as a prototype.
- Jobright.ai is part of the user's manual workflow, but full automated Jobright scraping may not be finalized.

What remains:

- Stabilize scraper sources.
- Avoid violating website terms or fragile scraping.
- Prefer official ATS/career sources.
- Decide source priority list.
- Add deduplication logic.
- Add robust handling for stale/expired postings.

#### 5. LLM / AI layer

Partially done.

Known:

- LLMs / AI are intended for:
  - JD parsing
  - skill extraction
  - scoring
  - resume-job matching
  - tailoring guidance
  - recruiter/outreach message generation
  - email interpretation for status updates
- User wants zero-cost options.
- Open-source/free local models preferred.
- Llama-based systems are acceptable given the user's prior experience with Llama.
- Paid API stack was discussed but rejected because the user does not want to spend money.

What remains:

- Final local model selection.
- Decide whether to use:
  - Ollama
  - llama.cpp
  - local Hugging Face model
  - small local instruction model
  - rule-based fallback for some steps
- Evaluate quality/speed tradeoff on user's machine.
- Create deterministic prompt templates.
- Add validation/guardrails to prevent hallucinated qualifications or invented resume content.

### What has NOT been started yet?

Based on available context, the following are not fully started or not confirmed as implemented:

- Fully automated ATS form filling.
- Browser extension or Playwright/Selenium application assistant for ATS pages.
- Actual automatic application submission.
- Production recruiter search automation.
- LinkedIn API integration.
- Automated sending of LinkedIn connection requests.
- Gmail/email monitoring integration.
- Automated tracker status updates from email.
- Full deployment/hosting beyond local execution.
- User authentication system for a multi-user app.
- Production database beyond Google Sheets / earlier prototype SQLite.
- Robust deduplication across job sources.
- End-to-end scheduled daily job runs.
- Mature logging/observability.
- Test suite.
- Dockerized production deployment.
- Claude-specific agent implementation.

---

## 3. Architecture & Tech Stack

### Core architecture

The architecture is modular and pipeline-based:

```text
Job Source / Scraper / Manual Input
        ↓
n8n Workflow / Webhook
        ↓
FastAPI Backend
        ↓
Canonicalization Service
        ↓
JD Parser Service
        ↓
Scoring Service
        ↓
Tailoring Service
        ↓
Decision Service
        ↓
Streamlit UI / n8n Routing
        ↓
Human Confirmation
        ↓
Google Sheets Tracker
        ↓
Recruiter Discovery + Outreach Drafting
        ↓
Email Monitoring + Status Updates
```

### Tools, libraries, frameworks, APIs, and services

#### Python

Primary implementation language.

Used for:

- FastAPI backend.
- Service classes.
- Scraping.
- JD parsing.
- scoring.
- tailoring.
- tracker integration.
- scripts that send job leads.
- possible future local LLM integration.

#### FastAPI

Backend API layer.

Known endpoints:

- `/pipeline/process-job`
- `/jobs/normalize`
- `/jobs/resolve-official`
- `/jobs/parse-jd`
- `/tracker/add-row`
- `/tracker/update-status`

Known routers:

- `jobs.py`
- `resume.py`
- `contacts.py`
- `tracker.py`
- `health.py`

#### n8n

Workflow orchestration layer.

Used for:

- Webhook ingestion.
- Calling FastAPI.
- Routing decisions.
- Sending Discord notifications.
- Appending to Google Sheets.
- Future scheduling.
- Future email/status workflows.

Known workflows:

- Workflow 1: manual test harness.
- Workflow 2: automated job ingestion / Sheets append flow.

#### Streamlit

Local UI layer.

Used for:

- Reviewing job leads.
- Viewing parsed JD.
- Viewing score card.
- Viewing matched/missing skills.
- Viewing tailoring recommendations.
- Starting assisted application.
- Confirming application submission.
- Saving/logging to tracker.
- Showing recruiter/contact panel.

Known UI components:

- `score_card.py`
- `job_review_panel.py`
- `recruiter_panel.py`

#### Google Sheets

Operational tracker.

Production tracker:

```text
Qualitative Job Application Booklet
```

Testing tracker:

```text
Qualitative Job Application Booklet – Automation Testing
```

Primary application tab/section:

```text
Jobs Applied
```

Other desired sections/tabs:

- Contacts / Referrals
- LinkedIn Outreach
- Referral Status
- Follow-up Messages

#### Google Apps Script

Discussed for advanced tracker formatting.

Used or intended for:

- Appending rows.
- Adding bold date header rows.
- Maintaining date-grouped application entries.
- Preserving tracker formatting and dropdowns.

Exact finalized Apps Script code is **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### Discord Webhooks

Notification layer.

Used for:

- n8n test alerts.
- Fresh/relevant job notifications.
- Manual review alerts.
- End-to-end workflow verification.

#### SQLite

Earlier prototype tracker storage.

Status:

- Previously used for local/in-memory testing.
- Later replaced by Google Sheets as the preferred operational tracker.
- Should not be the final source of truth unless used only for local cache/deduplication.

#### Selenium

Mentioned in user's background and prior projects. Potentially relevant for:

- scraping,
- browser automation,
- future ATS assistance.

No final Selenium-based ATS assistant was confirmed.

#### Greenhouse scraper

Path discussed:

```text
app/scrapers/ats/greenhouse_scraper.py
```

Purpose:

- Scrape or ingest jobs from Greenhouse-hosted company career pages.

#### Local/open-source LLMs

The user prefers not to spend money.

Possible local/open-source options discussed conceptually:

- Llama-based models.
- Ollama / local runner.
- small instruction models.
- rule-based fallback for deterministic parsing/scoring where possible.

No final model is confirmed.

#### Langflow

Discussed and rejected/saved for another project.

Final decision:

```text
Use Python + FastAPI + n8n for CareerSite Agent.
Do not use Langflow for this project right now.
```

#### APIs

General API-driven architecture.

Known API directions:

- FastAPI internal endpoints.
- n8n HTTP Request nodes.
- Google Sheets API or n8n Google Sheets node.
- Discord webhook endpoint.
- Future Gmail/email API.
- Future LinkedIn/contact search is not finalized.

### How components connect

#### Local manual/Streamlit path

```text
User opens Streamlit
    ↓
User pastes job/JD or selects sample job
    ↓
Streamlit calls local services directly or via FastAPI-like services
    ↓
CanonicalizationService resolves official posting
    ↓
JDParserService parses JD
    ↓
ScoringService scores fit
    ↓
TailoringService creates tailoring guidance
    ↓
DecisionService classifies apply/manual_review/skip
    ↓
User reviews output
    ↓
User clicks Start Apply
    ↓
User manually submits official application
    ↓
User clicks Confirm Applied / Save to Tracker
    ↓
TrackerService or n8n/Google Sheets appends row
```

#### n8n automated ingestion path

```text
Job source / script
    ↓
Webhook POST to n8n
    ↓
n8n HTTP Request to FastAPI /pipeline/process-job
    ↓
FastAPI returns normalized/parsing/scoring/decision output
    ↓
n8n IF / routing logic checks decision/freshness
    ↓
Discord alert for actionable jobs
    ↓
Manual review branch for uncertain/stale jobs
    ↓
Google Sheets append for relevant or confirmed rows
```

#### Scraper path

```text
Greenhouse / target ATS page
    ↓
greenhouse_scraper.py
    ↓
job_lead_sender.py or scripts/scrape_and_send_jobs.py
    ↓
n8n webhook
    ↓
FastAPI pipeline
    ↓
Tracker / Discord / UI
```

### Infrastructure details

#### Hosting

Current state:

- Local development.
- FastAPI runs locally.
- Streamlit runs locally.
- n8n runs locally, likely at:

```text
http://localhost:5678
```

Known webhook test endpoint:

```text
http://localhost:5678/webhook-test/incoming-job-lead
```

Production webhook endpoint is likely:

```text
http://localhost:5678/webhook/incoming-job-lead
```

when the workflow is active/published.

#### Database

Current final preference:

- Google Sheets is the source of truth.

Previous prototype:

- SQLite was used earlier.
- SQLite should be removed or limited to local cache if needed.

#### Authentication

Known configured/required credentials:

- Google Sheets OAuth credential in n8n.
- Discord webhook URL.
- Possibly Google Apps Script deployment permissions if Apps Script is used.
- Future Gmail OAuth if email monitoring is implemented.
- No paid LLM API key should be required if using local/open-source LLMs.

---

## 4. File & Folder Structure

> **Important:** This list includes every file/folder that was created, pasted, or discussed in the available context. Some files may exist in the local repo but their full contents were not available in this handoff.

### Root-level likely structure

```text
CareerSite-Agent/
├── app/
├── data/
├── scripts/
├── streamlit_app.py
├── requirements.txt
├── README.md
└── .env
```

Exact root folder name is not confirmed.

### `app/`

Main FastAPI application package.

```text
app/
├── main.py
├── dependencies.py
├── routers/
├── schemas/
├── services/
└── scrapers/
```

#### `app/main.py`

Purpose:

- FastAPI application entrypoint.
- Includes routers.
- Starts API app.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `app/dependencies.py`

Purpose:

- Dependency injection for service classes.

Known services wired or discussed:

```text
get_canonicalization_service
get_jd_parser_service
get_scoring_service
get_tailoring_service
get_decision_service
get_recruiter_service
get_tracker_service
```

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

### `app/routers/`

Router layer for FastAPI endpoints.

```text
app/routers/
├── jobs.py
├── resume.py
├── contacts.py
├── tracker.py
├── health.py
└── pipeline.py
```

`pipeline.py` was implied by `/pipeline/process-job`; exact filename is not fully confirmed but likely exists.

#### `app/routers/jobs.py`

Purpose:

- Job normalization.
- Official job link resolution.
- JD parsing.

Exact code snippet available in Section 6.

#### `app/routers/resume.py`

Purpose:

- Resume-related endpoint(s).
- Likely reads master resume or generates resume outputs.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `app/routers/contacts.py`

Purpose:

- Recruiter/contact-related endpoint(s).

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `app/routers/tracker.py`

Purpose:

- Tracker operations.

Known endpoints discussed:

```text
/tracker/add-row
/tracker/update-status
```

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `app/routers/health.py`

Purpose:

- Health check endpoint.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `app/routers/pipeline.py`

Purpose:

- Pipeline orchestration endpoint.

Known endpoint:

```text
/pipeline/process-job
```

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

### `app/schemas/`

Pydantic schemas.

```text
app/schemas/
└── job.py
```

Known schemas imported in `jobs.py`:

```text
JobLead
OfficialJobResolutionRequest
OfficialJobResolutionResponse
JDParseRequest
ParsedJD
```

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

### `app/services/`

Business logic layer.

```text
app/services/
├── canonicalization_service.py
├── jd_parser_service.py
├── scoring_service.py
├── tailoring_service.py
├── decision_service.py
├── recruiter_service.py
└── tracker_service.py
```

#### `app/services/canonicalization_service.py`

Purpose:

- Resolve aggregator/job lead link to official company posting.
- Normalize official job URL and confidence.

Important signature change:

```python
CanonicalizationService.resolve(payload: OfficialJobResolutionRequest)
```

The UI should **not** call `resolve_official(...)` anymore.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `app/services/jd_parser_service.py`

Purpose:

- Parse job description text.
- Extract structured JD fields.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `app/services/scoring_service.py`

Purpose:

- Compare JD requirements to master resume / skills.
- Produce a fit score.
- Output matched skills and missing items.

Known fields:

```text
matched_skills
missing_items
```

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `app/services/tailoring_service.py`

Purpose:

- Generate resume tailoring recommendations.
- Use master resume and JD gaps.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `app/services/decision_service.py`

Purpose:

- Convert score/freshness/fit into workflow routing decision.
- Decide whether job is ready, manual review, or rejected/skipped.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `app/services/recruiter_service.py`

Purpose:

- Recruiter/contact discovery logic.
- Likely prepares LinkedIn search queries or contact suggestions.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `app/services/tracker_service.py`

Purpose:

- Add rows / update statuses in tracker.
- Initially may have used SQLite.
- Final target should be Google Sheets.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

### `app/scrapers/`

Scraper layer.

```text
app/scrapers/
├── job_lead_sender.py
└── ats/
    └── greenhouse_scraper.py
```

#### `app/scrapers/ats/greenhouse_scraper.py`

Purpose:

- Scrape Greenhouse-hosted job boards or parse Greenhouse job postings.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `app/scrapers/job_lead_sender.py`

Purpose:

- Send scraped job lead payloads into n8n webhook or FastAPI.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

### `scripts/`

Utility scripts.

```text
scripts/
├── send_job_leads.py
└── scrape_and_send_jobs.py
```

#### `scripts/send_job_leads.py`

Purpose:

- Send job leads to webhook/API for testing or batch ingestion.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `scripts/scrape_and_send_jobs.py`

Purpose:

- Run scraper and send results into workflow.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

### `data/`

Project data/config folder.

```text
data/
├── master_resume/
│   └── master_resume.json
├── sample_jobs/
├── target_companies.json
├── role_profiles.json
└── skill_taxonomy.json
```

#### `data/master_resume/master_resume.json`

Purpose:

- Master source of resume truth.
- Contains candidate data for Akhilesh A. Kumbhar.
- Contains:
  - summary variants,
  - education,
  - experience,
  - skills,
  - projects,
  - research papers,
  - role targeting,
  - tailoring rules.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `data/sample_jobs/`

Purpose:

- Sample jobs for Streamlit testing/demo.

Exact files: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `data/target_companies.json`

Purpose:

- List of target companies to scrape or monitor.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `data/role_profiles.json`

Purpose:

- Role-specific matching/tailoring config.
- Used for Data Analyst, Data Scientist, Machine Learning Engineer, AI/ML roles.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `data/skill_taxonomy.json`

Purpose:

- Canonical skill normalization.
- Maps related terms to skill categories.
- Used in scoring and JD parsing.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

### Streamlit files

```text
streamlit_app.py
app/ui/components/score_card.py
app/ui/components/job_review_panel.py
app/ui/components/recruiter_panel.py
```

Exact component folder path is inferred; exact path may differ.

#### `streamlit_app.py`

Purpose:

- Main local UI.
- Lets user review job, parse JD, score fit, tailor resume, and save to tracker.

Known required update:

- Import `OfficialJobResolutionRequest`.
- Build request payload.
- Call `canonicalization_service.resolve(payload)`.
- Store results in `st.session_state` to avoid reset after Save-to-Tracker.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `score_card.py`

Purpose:

- Display fit score.
- Display matched skills/missing items.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `job_review_panel.py`

Purpose:

- Display job details and review/decision UI.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `recruiter_panel.py`

Purpose:

- Display recruiter/contact suggestions and outreach draft.

Exact full content: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

### Configuration files

#### `.env`

Purpose:

- Store local environment variables.

Likely variables:

```text
N8N_WEBHOOK_URL
DISCORD_WEBHOOK_URL
GOOGLE_SHEETS_SPREADSHEET_ID
GOOGLE_SHEETS_TAB_NAME
FASTAPI_BASE_URL
LOCAL_LLM_BASE_URL
```

Exact finalized variable names: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

#### `requirements.txt`

Purpose:

- Python dependencies.

Known likely dependencies:

```text
fastapi
uvicorn
pydantic
streamlit
requests
pandas
beautifulsoup4
selenium
google-api-python-client
google-auth
google-auth-oauthlib
```

Exact finalized dependencies: **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

---

## 5. Decisions & Rationale

### Decision 1: Use Level 2 assisted application flow

Final choice:

```text
Level 2: Assisted application session with explicit confirmation
```

Workflow:

1. System surfaces job.
2. User clicks **Start Apply**.
3. System opens/provides official application link and known details/instructions.
4. User manually submits application.
5. User clicks **Confirm Applied**.
6. System logs to Google Sheets and prepares outreach.

Rationale:

- Reliable.
- Keeps user in control.
- Avoids risky automatic ATS submission.
- Reduces manual bookkeeping.
- Good balance between automation and control.

Rejected approach:

```text
Fully autonomous application submission
```

Reason rejected:

- Too risky.
- ATS pages vary heavily.
- Could submit wrong information.
- User wants control over final submission.

### Decision 2: Use Python + FastAPI + n8n

Final stack:

```text
Python + FastAPI + n8n
```

Rationale:

- Python is best for parsing, scoring, ML/LLM logic, and scraping.
- FastAPI gives clean modular APIs.
- n8n is good for orchestration, scheduling, webhooks, Sheets, Discord, and email workflows.
- Easier to debug than a fully custom workflow engine.

Rejected / deferred:

```text
Langflow
```

Reason:

- Saved for another project.
- The user wanted a practical automation system, not an LLM-flow prototype.

### Decision 3: Use Google Sheets as the source of truth

Final choice:

```text
Google Sheets tracker is the operational database.
```

Rationale:

- User already uses Google Sheets daily.
- Existing tracker has dropdowns/status values.
- Familiar and easy to manually inspect.
- Better for the user's personal workflow than a hidden DB.

Rejected / downgraded:

```text
SQLite as primary tracker
```

Reason:

- Good for testing but not aligned with user's actual daily tracker.
- User prefers everything reflected in the Google Sheet.

### Decision 4: Official company links only

Final choice:

```text
Always log/apply using official company career-site links.
```

Rationale:

- User discovers jobs through Jobright.ai but applies through original job posts.
- Official links are more reliable.
- Avoids relying on aggregator pages.
- Better for deduplication and application proof.

Related decision:

```text
"Link" and "Official Posting Link" are the same in the tracker.
```

Rationale:

- No need for duplicate columns.
- The tracker should store one official application link.

### Decision 5: Avoid paid LLM/API usage

Final preference:

```text
Do not spend money. Prefer open-source/free local LLM options.
```

Rationale:

- User explicitly does not want to spend a single dime.
- Project should be usable for daily job search without recurring API cost.
- Rule-based logic plus small local models may be enough for many tasks.

Rejected:

```text
Paid LLM API stack
```

Reason:

- Cost.

### Decision 6: Use LLMs only where useful

LLMs/AI should be used for:

- JD parsing.
- Skill extraction.
- Job-resume fit scoring support.
- Resume tailoring suggestions.
- LinkedIn message drafting.
- Email interpretation.

LLMs should not be blindly trusted for:

- Application submission.
- Inventing experience.
- Making irreversible status updates without validation.
- Creating fake qualifications.

### Decision 7: Route stale/uncertain jobs to manual review

Final behavior:

```text
Stale or uncertain jobs should go to manual_review, not hard reject, unless clearly invalid.
```

Rationale:

- Avoid missing potentially useful jobs.
- User prefers manual review for borderline cases.
- Freshness alone should not always reject.

### Decision 8: Preserve existing Google Sheet formatting

Final behavior:

- Use date headers.
- Preserve dropdown status values.
- Continue under correct date.
- Do not break existing tracker structure.

Rationale:

- User already has a working tracker format.
- Automation should integrate into the user's current behavior, not force a new structure.

### Decision 9: Use testing copy before production tracker

Testing tracker:

```text
Qualitative Job Application Booklet – Automation Testing
```

Rationale:

- Prevent accidental corruption of production tracker.
- Verify formatting/date-header logic safely.

### Decision 10: The system should support the user's real daily workflow

User's real baseline:

- 1 hour every morning and evening.
- 5 applications per session.
- 10 total applications per day.
- 10 new LinkedIn connections from those companies per day.
- Daily email check for status updates.

Rationale:

- The project is not abstract.
- It should reduce the exact repetitive work the user already performs.

---

## 6. Exact Implementations

> **Important:** This section includes exact available code/snippets. Full files not pasted or accessible are marked honestly.

---

### 6.1 `app/routers/jobs.py` — current available code

Purpose:

- Job normalization.
- Official job resolution.
- JD parsing.

```python
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
    # Remainder of this function was not fully visible in the accessible context.
```

Known issue:

- The pasted file was truncated after `service: JDParserService = Depends(get_jd_parser_service),`.
- The expected final line should likely return `service.parse(payload)` or equivalent, but the exact code is **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

---

### 6.2 Streamlit canonicalization patch — exact logic/pattern discussed

Purpose:

- Update Streamlit code after `CanonicalizationService` signature changed.
- Stop calling `resolve_official(...)`.
- Use `OfficialJobResolutionRequest`.
- Call `canonicalization_service.resolve(payload)`.

```python
from app.schemas.job import OfficialJobResolutionRequest
```

Expected patch pattern:

```python
resolution_payload = OfficialJobResolutionRequest(
    company=job_payload["company"],
    title=job_payload["title"],
    source_url=job_payload["link"],
    description=job_payload.get("description", ""),
)

resolution_result = canonicalization_service.resolve(resolution_payload)
```

Important note:

- Exact surrounding Streamlit code is **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.
- The important finalized change is the method call:
  - use `resolve(payload)`
  - do not use `resolve_official(...)`

---

### 6.3 Streamlit state persistence fix — exact logic/pattern discussed

Problem:

- Save-to-Tracker button caused page reset.
- Cause: analysis outputs were stored only in local variables.
- Fix: persist key outputs in `st.session_state`.

Required session state keys:

```python
st.session_state["job_payload"] = job_payload
st.session_state["resolution_result"] = resolution_result
st.session_state["parsed"] = parsed
st.session_state["score"] = score
st.session_state["tailored"] = tailored
st.session_state["decision"] = decision
```

Expected usage pattern:

```python
if "job_payload" in st.session_state:
    job_payload = st.session_state["job_payload"]

if "resolution_result" in st.session_state:
    resolution_result = st.session_state["resolution_result"]

if "parsed" in st.session_state:
    parsed = st.session_state["parsed"]

if "score" in st.session_state:
    score = st.session_state["score"]

if "tailored" in st.session_state:
    tailored = st.session_state["tailored"]

if "decision" in st.session_state:
    decision = st.session_state["decision"]
```

Important note:

- Exact final Streamlit file content is **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.
- The key implementation requirement is to store all analysis outputs in `st.session_state` before rendering buttons that trigger reruns.

---

### 6.4 n8n webhook test command — PowerShell

Purpose:

- Test n8n incoming job lead webhook from Windows PowerShell.

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:5678/webhook-test/incoming-job-lead -ContentType "application/json" -Body '{
  "job_id": "test-001",
  "company": "Example Company",
  "title": "Machine Learning Engineer",
  "description": "We are looking for a Machine Learning Engineer with Python, SQL, FastAPI, and ML experience.",
  "link": "https://example.com/careers/ml-engineer",
  "source": "manual_test"
}'
```

Important:

- `/webhook-test/...` is for test mode while the workflow editor is listening.
- Production active workflow usually uses `/webhook/...`.

---

### 6.5 Canonical job lead payload schema — practical JSON payload

Purpose:

- Standard job lead payload entering n8n/FastAPI.

```json
{
  "job_id": "string",
  "company": "string",
  "title": "string",
  "description": "string",
  "link": "string",
  "source": "string"
}
```

Known field meanings:

- `job_id`: source-specific job identifier.
- `company`: company name.
- `title`: job title.
- `description`: raw JD text or snippet.
- `link`: official job posting link if available; otherwise source link to be canonicalized.
- `source`: source system such as `jobright`, `greenhouse`, `manual_test`, etc.

---

### 6.6 Google Sheets tracker row schema — user-facing fields

Primary tab/section:

```text
Jobs Applied
```

Known columns:

```text
Company Applied
Role
Salary Quoted while Applying
Job Posted On
Applied Using
Status
Link
```

Known notes:

- `Link` should be the official company application link.
- `Applied Using` should usually be:
  - `Company Website`
- `Job Posted On` may double as source/date semantics depending the existing sheet.
- No separate `Source` column is needed unless user later changes tracker structure.
- `Application Started At` vs `Application Submitted At` was debated; for personal use, one date column is sufficient unless user later wants finer tracking.

---

### 6.7 Google Sheets date header requirement

Purpose:

- Preserve user's tracker grouping by application date.

Required date header format:

```text
mm/dd/yyyy: MM/DD/YYYY
```

Example:

```text
04/10/2026: 04/10/2026
```

Rules:

1. If today's date header already exists:
   - append the new application below the last application under that date.

2. If today's date header does not exist:
   - add a new bold date header row.
   - leave spacing as established in the existing sheet.
   - append today's applications below that header.

3. Date header row should be bold.

4. Existing dropdowns/status values should be preserved.

Exact Apps Script implementation:

```text
NOT AVAILABLE IN ACCESSIBLE CONTEXT
```

---

### 6.8 Google Sheets status values — known dropdown options

Known status values mentioned by the user:

```text
Applied
Screening Interview Call
Technical Interview Call
HR Interview Call
Rejection
Accepted/Offered Job
```

Rule:

- Use these exact values if they match the sheet dropdown.
- Do not invent new statuses without updating the sheet dropdown.

---

### 6.9 FastAPI endpoint list

Known endpoints:

```text
POST /pipeline/process-job
POST /jobs/normalize
POST /jobs/resolve-official
POST /jobs/parse-jd
POST /tracker/add-row
POST /tracker/update-status
```

Known expected behavior:

#### `POST /pipeline/process-job`

Purpose:

- Run complete processing pipeline on a job lead.

Expected stages:

```text
normalize → resolve official → parse JD → score → tailor → decision → response
```

Exact implementation:

```text
NOT AVAILABLE IN ACCESSIBLE CONTEXT
```

#### `POST /jobs/normalize`

Purpose:

- Strip whitespace from company and title.

Exact implementation available in `jobs.py`.

#### `POST /jobs/resolve-official`

Purpose:

- Resolve official company job posting link.

Exact implementation available in `jobs.py` wrapper, but service internals unavailable.

#### `POST /jobs/parse-jd`

Purpose:

- Parse JD into structured output.

Router wrapper partially visible; full implementation unavailable.

#### `POST /tracker/add-row`

Purpose:

- Add a row to tracker.

Exact implementation unavailable.

#### `POST /tracker/update-status`

Purpose:

- Update status in tracker after email/company response.

Exact implementation unavailable.

---

### 6.10 n8n Workflow 1 — manual test harness

Purpose:

- Verify end-to-end connections manually.

Known behavior:

```text
Manual Trigger
    ↓
Set / sample payload
    ↓
HTTP Request to FastAPI or Discord
    ↓
Discord notification
```

Exact exported n8n workflow JSON:

```text
NOT AVAILABLE IN ACCESSIBLE CONTEXT
```

---

### 6.11 n8n Workflow 2 — automated ingestion flow

Purpose:

- Accept incoming job leads and push them through processing/tracker/notification flow.

Known intended structure:

```text
Webhook: incoming-job-lead
    ↓
HTTP Request: call FastAPI /pipeline/process-job
    ↓
Code / Set node: map and normalize output fields if needed
    ↓
IF node: route based on freshness / decision / score
    ├── Fresh or actionable → Discord notification + possibly tracker/manual review
    └── Stale/uncertain → manual_review branch, not hard reject
    ↓
Google Sheets node: append row
```

Important rule from prior discussion:

```text
If job is stale, do not always reject. Route to manual_review unless clearly invalid.
```

Exact exported workflow JSON:

```text
NOT AVAILABLE IN ACCESSIBLE CONTEXT
```

---

### 6.12 n8n Code node logic — reject to manual_review remap

Purpose:

- Prevent stale/rejected items from being lost too aggressively.

Conceptual behavior discussed:

```text
If decision is reject only because of freshness/staleness:
    change decision to manual_review
```

Exact Code node script:

```text
NOT AVAILABLE IN ACCESSIBLE CONTEXT
```

Safe implementation pattern to recreate:

```javascript
const item = $json;

if (item.decision === "reject" && item.reason && item.reason.toLowerCase().includes("stale")) {
  item.decision = "manual_review";
  item.review_reason = "Originally rejected due to freshness/staleness. Routed to manual review to avoid missing a potentially useful role.";
}

return item;
```

Important note:

- The above JavaScript is a safe reconstruction pattern, not confirmed as the exact previous code.

---

### 6.13 Master resume JSON

File:

```text
data/master_resume/master_resume.json
```

Purpose:

- Single source of truth for candidate profile and resume tailoring.

Known contents:

```text
candidate: Akhilesh A. Kumbhar
summary_variants
education
experience
skills
projects
research_papers
role_targeting
tailoring_rules
```

Exact JSON:

```text
NOT AVAILABLE IN ACCESSIBLE CONTEXT
```

---

### 6.14 CareerSite Agent resume/project description

This wording appears in resume materials and can be used as a project description:

```text
CareerSite Agent (Ongoing) | Python, FastAPI, n8n, APIs

Building an agentic AI system to automate job discovery and application workflows, integrating APIs and event-driven orchestration.

Implementing RAG pipelines for job parsing, skill extraction, and resume-job matching to support decision workflows.

Designing modular pipeline architecture and evaluation logic (scoring thresholds, routing) to improve decision consistency and scalability.
```

Alternative concise wording:

```text
Building an agentic AI workflow system for job discovery, JD parsing, resume-job matching, and application tracking with API-driven orchestration.

Designing modular parsing, scoring, and decision services with threshold-based evaluation logic to improve workflow consistency and scalability.
```

---

### 6.15 Daily workflow baseline

User's actual manual process:

```text
Morning session:
- 1 hour
- 5 applications

Evening session:
- 1 hour
- 5 applications

Daily total:
- 10 applications
- 10 new LinkedIn connections from those companies
- daily email check for company notifications
- update Google Sheet statuses accordingly
```

---

### 6.16 Tracker application row mapping

Recommended mapping from processed job output to Google Sheets:

```json
{
  "Company Applied": "{{company}}",
  "Role": "{{title}}",
  "Salary Quoted while Applying": "{{salary_or_blank}}",
  "Job Posted On": "{{posted_date_or_source_value}}",
  "Applied Using": "Company Website",
  "Status": "Applied",
  "Link": "{{official_job_link}}"
}
```

Important:

- Use `official_job_link` if resolved.
- Fallback to `link` only if official resolution is unavailable.
- Do not store aggregator link when official link is available.

---

## 7. Prompts & Agent Instructions

> **Important:** Exact final prompt templates for all agents were not fully available in the accessible context. This section lists every known prompt/instruction category and includes exact text only where available.

### 7.1 Overall agent instruction

Purpose:

- Continue the CareerSite Agent project without losing context.

Known instruction:

```text
Build a human-in-the-loop agentic AI system for job discovery, official career-site resolution, JD parsing, resume-job matching, tailoring guidance, application tracking, recruiter outreach, and email/status monitoring. Use Python + FastAPI + n8n, Google Sheets as the operational tracker, Discord for alerts, and open-source/free LLM options where possible. Preserve the user's existing workflow and tracker format.
```

This is a consolidated project instruction, not known to be a previously saved system prompt.

### 7.2 JD parsing prompt

Purpose:

- Extract structured fields from job descriptions.

Exact finalized prompt:

```text
NOT AVAILABLE IN ACCESSIBLE CONTEXT
```

Known expected output fields:

```text
company
title
location
employment_type
required_skills
preferred_skills
responsibilities
years_experience
education_requirements
tools
technologies
keywords
summary
```

### 7.3 Resume-job scoring prompt

Purpose:

- Compare JD with master resume.

Exact finalized prompt:

```text
NOT AVAILABLE IN ACCESSIBLE CONTEXT
```

Known expected outputs:

```text
score
matched_skills
missing_items
strengths
risks
recommendation
```

### 7.4 Tailoring prompt

Purpose:

- Suggest resume tailoring without fabricating experience.

Exact finalized prompt:

```text
NOT AVAILABLE IN ACCESSIBLE CONTEXT
```

Known rule:

```text
Do not invent skills, employers, experience, publications, or credentials.
Only reframe existing resume evidence.
```

### 7.5 Recruiter outreach prompt

Purpose:

- Generate LinkedIn connection notes and post-acceptance messages.

Exact finalized prompt:

```text
NOT AVAILABLE IN ACCESSIBLE CONTEXT
```

Known style:

- concise,
- recruiter-friendly,
- tailored to role/company,
- usually under 200 characters for connection requests,
- professional but not overly formal,
- mention background briefly,
- share resume if appropriate after connection acceptance.

### 7.6 Email monitoring/status prompt

Purpose:

- Interpret emails and update tracker status.

Exact finalized prompt:

```text
NOT AVAILABLE IN ACCESSIBLE CONTEXT
```

Known statuses to map to:

```text
Applied
Screening Interview Call
Technical Interview Call
HR Interview Call
Rejection
Accepted/Offered Job
```

### 7.7 Claude handoff instruction

Purpose:

- New AI assistant should continue from this README.

Suggested instruction to give Claude:

```text
You are continuing the CareerSite Agent Automation project. Read this README completely before suggesting any implementation. Preserve all decisions already made. Do not redesign the project unless there is a clear technical reason. The user wants practical, step-by-step, ready-to-use code and exact file paths. Prefer free/open-source options and avoid paid APIs. The next task is to continue wiring n8n Workflow 2 and Google Sheets append/status logic.
```

---

## 8. Integrations & Credentials Setup

### Google Sheets

Connected/used:

- Google Sheets tracker.
- n8n Google Sheets node and/or Google Apps Script.

Production spreadsheet:

```text
Qualitative Job Application Booklet
```

Testing spreadsheet:

```text
Qualitative Job Application Booklet – Automation Testing
```

Required permissions:

- Read rows.
- Append rows.
- Update existing rows.
- Preserve or apply formatting.
- Possibly use Apps Script to control date headers and bold formatting.

Credential setup:

- n8n Google Sheets OAuth credential was configured/tested.
- Exact credential name is **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.
- Spreadsheet IDs are **NOT AVAILABLE IN ACCESSIBLE CONTEXT**.

### Discord

Connected/used:

- Discord webhook alerts.

Purpose:

- Notify user of fresh/actionable jobs.
- Test workflow execution.
- Alert for manual review.

Credentials:

```text
DISCORD_WEBHOOK_URL
```

Exact value is intentionally not included.

### n8n

Local URL:

```text
http://localhost:5678
```

Webhook test endpoint:

```text
http://localhost:5678/webhook-test/incoming-job-lead
```

Likely production endpoint after activation:

```text
http://localhost:5678/webhook/incoming-job-lead
```

Configured nodes discussed:

- Webhook
- HTTP Request
- Code
- IF
- Google Sheets
- Discord

Known user question:

- Whether to publish Workflow 2.
- Where to add a node in Workflow 2 UI.

Guidance:

- Use test webhook while developing.
- Publish/activate Workflow 2 only when ready for production-style incoming payloads.
- If using production webhook, workflow must be active.

### FastAPI

Local backend.

Likely base URL:

```text
http://localhost:8000
```

Known endpoints:

```text
/pipeline/process-job
/jobs/normalize
/jobs/resolve-official
/jobs/parse-jd
/tracker/add-row
/tracker/update-status
```

Startup command likely:

```bash
uvicorn app.main:app --reload
```

Exact command was not confirmed in accessible context.

### Streamlit

Local UI.

Likely startup command:

```bash
streamlit run streamlit_app.py
```

Exact command was not confirmed in accessible context.

### Gmail / email monitoring

Planned but not implemented.

Future needs:

- Gmail OAuth.
- Query emails from applied companies.
- Parse subject/body.
- Map status to tracker dropdown.
- Update Google Sheets.

No credential setup confirmed.

### LinkedIn

Planned but not implemented.

Important:

- LinkedIn automation is sensitive and may violate platform rules if automated too aggressively.
- Safer approach:
  - generate search queries,
  - draft messages,
  - user manually sends requests.

No LinkedIn API credentials configured.

### LLM / local model

Planned/partially discussed.

User constraint:

```text
No paid API cost.
```

Possible future setup:

- Ollama local model endpoint.
- llama.cpp.
- Hugging Face local inference.
- Rule-based fallback.

No final model or endpoint confirmed.

---

## 9. Problems Encountered & How They Were Solved

### Problem 1: Streamlit called old canonicalization method

Issue:

- `CanonicalizationService` changed its method signature.
- UI still called an older method like `resolve_official(...)`.

Resolution:

- Import `OfficialJobResolutionRequest`.
- Build payload object.
- Call:

```python
canonicalization_service.resolve(payload)
```

instead of:

```python
canonicalization_service.resolve_official(...)
```

### Problem 2: Save-to-Tracker button reset Streamlit page

Issue:

- Streamlit reruns the script on button clicks.
- Analysis outputs existed only as local variables.
- When user clicked Save-to-Tracker, the page reset and lost parsed/score/tailored/decision state.

Resolution:

- Store all important outputs in `st.session_state`.

Required keys:

```python
st.session_state["job_payload"]
st.session_state["resolution_result"]
st.session_state["parsed"]
st.session_state["score"]
st.session_state["tailored"]
st.session_state["decision"]
```

### Problem 3: SQLite tracker did not match real workflow

Issue:

- Earlier prototype used SQLite.
- User's actual workflow uses Google Sheets.

Resolution:

- Move operational tracker to Google Sheets.
- Keep SQLite only if needed for local cache/testing.

### Problem 4: Google Sheets formatting risk

Issue:

- Simple append could break existing sheet structure.
- User's tracker uses date headers, dropdowns, and specific column layout.

Resolution:

- Use testing copy first:
  - `Qualitative Job Application Booklet – Automation Testing`
- Preserve exact status values.
- Add date-header logic.
- Bold date header rows.
- Continue appending under existing date header.

Exact Apps Script not available in current context.

### Problem 5: Link vs Official Posting Link confusion

Issue:

- There was ambiguity about whether to store both `Link` and `Official Posting Link`.

Resolution:

- Treat them as the same.
- Store only one official company application link in `Link`.

### Problem 6: Source column ambiguity

Issue:

- Whether a separate `Source` column was needed.

Resolution:

- No separate source column needed for current tracker.
- `Job Posted On` may carry existing semantics.
- The key operational link is the official company link.

### Problem 7: Application Started At vs Submitted At

Issue:

- Debated whether to separately track started and submitted timestamps.

Resolution:

- For this personal workflow, one application date/status is enough unless the user later needs more detailed analytics.

### Problem 8: Paid LLM cost concern

Issue:

- Recommended stack with paid LLM APIs would cost money.

Resolution:

- User explicitly rejected paid options.
- Project should use open-source/free options.

### Problem 9: n8n stale-job rejection too aggressive

Issue:

- Freshness filter could reject stale jobs that the user may still want to review.

Resolution:

- Route stale/uncertain jobs to `manual_review` rather than hard rejection.

### Problem 10: n8n test vs production webhook confusion

Issue:

- User tested webhook through `/webhook-test/...`.
- Asked whether to publish Workflow 2.

Resolution:

- Use `/webhook-test/...` while editor is listening in test mode.
- Use `/webhook/...` only after activating/publishing Workflow 2.
- Workflow 2 should be published/activated when ready for non-test runs.

### Problem 11: n8n node placement uncertainty

Issue:

- User asked where to add a node in Workflow 2.

Known guidance:

- A mapping/Code/Set node should usually be placed after the HTTP Request node that receives FastAPI output and before the IF or Google Sheets node, depending on what it transforms.
- If the node remaps `reject` to `manual_review`, place it before the IF node that branches on decision.
- If the node formats fields for Google Sheets, place it immediately before the Google Sheets append node.

Exact screenshot-specific placement is not preserved in this README.

### Problem 12: n8n permission crash / rate limits

Issue:

- n8n permission crash and Discord/n8n rate limits were encountered.

Resolution:

- Not fully documented in accessible context.
- Known workaround: continue with careful test runs, avoid excessive notification loops, and verify node permissions/credentials.

---

## 10. Open Questions & Unresolved Issues

### Architecture / implementation

1. Final local LLM choice is not finalized.
2. Whether to use Ollama, llama.cpp, Hugging Face local inference, or pure rule-based parsing for v1 is unresolved.
3. Exact scoring formula and threshold values are not fully available.
4. Exact decision routing thresholds are not fully available.
5. Exact JD parser schema is not fully available.
6. Exact master resume JSON is not available in this context.
7. Exact role profile JSON and skill taxonomy are not available in this context.
8. Exact Google Apps Script code is not available in this context.
9. Exact n8n Workflow 2 export JSON is not available.
10. Exact Streamlit final code is not available.
11. Exact FastAPI `/pipeline/process-job` implementation is not available.

### Google Sheets

1. Exact production spreadsheet ID is not documented here.
2. Exact testing spreadsheet ID is not documented here.
3. Exact tab names beyond known tracker sections should be verified.
4. Exact column order should be verified against the live sheet.
5. Exact dropdown status list should be verified.
6. Whether Apps Script or n8n should own formatting is not finalized.
7. Whether to log jobs before application or only after Confirm Applied needs final enforcement.
   - User preference seems to favor logging after application confirmation, but job review/manual review rows may also be useful.

### n8n

1. Whether Workflow 2 is already published/activated is unresolved.
2. Exact node currently selected in the user's screenshot is unknown from this README.
3. Exact placement of the current node depends on whether it is:
   - decision remap logic,
   - Google Sheets field mapper,
   - Discord formatter,
   - or FastAPI request node.
4. Production webhook URL should be confirmed after activation.

### Scraping

1. Jobright.ai automated ingestion is not finalized.
2. Greenhouse scraper robustness is unknown.
3. Target company list content is not available.
4. Deduplication is not finalized.
5. Handling closed/expired jobs is not finalized.

### Recruiter/outreach

1. Recruiter discovery not fully implemented.
2. LinkedIn automation approach unresolved.
3. Whether to use manual LinkedIn search URLs or scraping is unresolved.
4. Connection request template is not finalized for the app.
5. Post-connection accepted template is not finalized for the app.

### Email/status monitoring

1. Gmail integration not started/confirmed.
2. Email classification prompt not finalized.
3. Automated status update confidence threshold not finalized.
4. Whether user must confirm status updates before writing to Sheets is unresolved.

### UI

1. Final Start Apply / Confirm Applied UI not confirmed.
2. Final tracker save behavior not confirmed.
3. Final recruiter panel behavior not confirmed.
4. Error handling UX not finalized.

### Deployment

1. No production hosting finalized.
2. Docker setup not confirmed.
3. Background scheduling not finalized.
4. Logging/monitoring not finalized.
5. Test suite not started/confirmed.

---

## 11. Next Steps (Prioritized)

### Exact next task to pick up

Continue with **n8n Workflow 2 wiring**.

Most likely next action:

```text
Add the mapping/remap node in Workflow 2 at the correct location.
```

Placement rule:

1. If the node is for **decision cleanup** such as converting stale `reject` to `manual_review`:
   - place it **after the FastAPI HTTP Request node**
   - and **before the IF node** that branches on decision.

2. If the node is for **Google Sheets row formatting**:
   - place it **after decision routing**
   - and **immediately before the Google Sheets Append Row node**.

3. If the node is for **Discord message formatting**:
   - place it **right before the Discord node**.

Given the latest context, the likely needed placement is:

```text
Webhook → HTTP Request to FastAPI → Code/Set mapping node → IF decision branch → Discord / Google Sheets
```

### Prioritized backlog

#### Priority 1: Stabilize Workflow 2

1. Confirm current n8n Workflow 2 node layout.
2. Add Code/Set node in correct place.
3. Ensure payload from webhook matches FastAPI expected schema.
4. Ensure HTTP Request calls `/pipeline/process-job`.
5. Ensure FastAPI response fields are mapped cleanly.
6. Route stale/uncertain jobs to `manual_review`.
7. Test with sample payload.
8. Confirm Discord message output.
9. Confirm Google Sheets append output in testing sheet.
10. Activate/publish Workflow 2 only after test succeeds.

#### Priority 2: Google Sheets finalization

1. Verify exact production sheet column order.
2. Verify exact dropdown values.
3. Decide whether n8n or Apps Script handles date headers.
4. Implement date-header append logic.
5. Test with `Qualitative Job Application Booklet – Automation Testing`.
6. Confirm formatting:
   - bold date header,
   - correct date format,
   - append under same date,
   - no overwritten rows.
7. Switch to production sheet only after repeated tests.

#### Priority 3: Streamlit Level 2 assisted flow

1. Update `streamlit_app.py` to match `CanonicalizationService.resolve(payload)`.
2. Ensure all state is stored in `st.session_state`.
3. Add or polish **Start Apply** button.
4. Add or polish **Confirm Applied** button.
5. On Confirm Applied, call tracker append.
6. Show success/failure message.
7. Keep analysis visible after saving.

#### Priority 4: Backend pipeline cleanup

1. Review `/pipeline/process-job`.
2. Ensure pipeline returns consistent schema.
3. Add error handling.
4. Add official link fallback logic.
5. Add deduplication fields.
6. Add decision explanations.
7. Add tests for sample payloads.

#### Priority 5: JD parsing and scoring improvement

1. Finalize `ParsedJD` schema.
2. Finalize skill taxonomy.
3. Finalize role profiles.
4. Finalize scoring weights.
5. Add rule-based deterministic parsing where possible.
6. Add local LLM only where rule-based extraction is insufficient.
7. Prevent hallucinated skills.

#### Priority 6: Open-source LLM integration

1. Benchmark one local model.
2. Create a local LLM wrapper service.
3. Add fallback if model unavailable.
4. Test JD parsing and tailoring quality.
5. Keep cost zero.

#### Priority 7: Recruiter/outreach flow

1. Create recruiter search query generator.
2. Create LinkedIn manual search URLs.
3. Generate connection request notes.
4. Generate post-connection accepted messages.
5. Add to Streamlit recruiter panel.
6. Add tracker tab/section for LinkedIn outreach.

#### Priority 8: Email/status monitoring

1. Connect Gmail OAuth.
2. Search emails from applied companies.
3. Parse status emails.
4. Map to tracker statuses.
5. Require confirmation before updating status at first.
6. Later automate high-confidence updates.

#### Priority 9: Scraper/source expansion

1. Stabilize Greenhouse scraper.
2. Add target company list.
3. Add more ATS sources if needed.
4. Add deduplication.
5. Add expired posting handling.
6. Schedule daily runs.

#### Priority 10: Polish and production readiness

1. Add `.env.example`.
2. Add setup instructions.
3. Add error logging.
4. Add retry handling.
5. Add test suite.
6. Add Docker if useful.
7. Add screenshots/gifs if needed.
8. Keep README updated.

---

## 12. Context & Preferences

### User preferences

The user prefers:

- Step-by-step guidance.
- Complete ready-to-use code.
- Exact file paths.
- Exact node placement in n8n.
- Copy-paste runnable commands.
- Avoiding vague advice.
- Avoiding repeated prototype cycles.
- Building toward a polished practical tool.
- Concise but complete explanations.
- Simple wording when possible.
- Skeptical review of assumptions.
- Honest uncertainty when exact details are unavailable.
- Zero-cost / open-source options.
- Human control over final applications.
- Preserving existing Google Sheets workflow.
- Practical automation that fits daily behavior.

### User constraints

Hard constraints:

```text
Do not spend money on LLM APIs.
Do not fully automate final application submission.
Use official company links for applications.
Use Google Sheets as operational tracker.
Preserve existing tracker status dropdowns and format.
Avoid fabricating resume content.
```

### User's daily job application workflow

User normally:

1. Sits for 1 hour in the morning.
2. Applies to 5 jobs.
3. Sits for 1 hour in the evening.
4. Applies to 5 more jobs.
5. Total: 10 applications per day.
6. Sends around 10 LinkedIn connection requests per day from those companies.
7. Checks email daily for applied-company notifications.
8. Updates tracker statuses manually.

### User's tracker

Main tracker:

```text
Qualitative Job Application Booklet
```

Testing copy:

```text
Qualitative Job Application Booklet – Automation Testing
```

Known tracker columns:

```text
Company Applied
Role
Salary Quoted while Applying
Job Posted On
Applied Using
Status
Link
```

Known status values:

```text
Applied
Screening Interview Call
Technical Interview Call
HR Interview Call
Rejection
Accepted/Offered Job
```

### User background relevant to project

The user is:

- Akhilesh Arunkumar Kumbhar.
- MS Data Science student at UT Arlington.
- Expected graduation: May 2026.
- Targets roles such as:
  - Data Scientist,
  - Machine Learning Engineer,
  - Data Analyst,
  - AI/ML Engineer.
- Has experience with:
  - Python,
  - SQL,
  - FastAPI,
  - Streamlit,
  - n8n,
  - RAG pipelines,
  - Llama-based systems,
  - AWS EC2,
  - Docker,
  - Selenium,
  - Power BI,
  - machine learning,
  - recommender systems,
  - computer vision.

### CareerSite Agent resume description

Useful project description:

```text
CareerSite Agent (Ongoing) | Python, FastAPI, n8n, APIs
Building an agentic AI system to automate job discovery and application workflows, integrating APIs and event-driven orchestration.
Implementing RAG pipelines for job parsing, skill extraction, and resume-job matching to support decision workflows.
Designing modular pipeline architecture and evaluation logic (scoring thresholds, routing) to improve decision consistency and scalability.
```

### Communication style for future assistant

A future assistant should:

- Not restart the project from scratch.
- Not re-litigate already-decided architecture unless there is a real reason.
- Continue from the current n8n/Google Sheets integration point.
- Give exact UI/node guidance for n8n.
- Provide full file-level code when editing source files.
- Mark uncertainty clearly.
- Avoid suggesting paid tools.
- Avoid over-automating LinkedIn or ATS submission.
- Preserve the user's existing Google Sheet structure.
- Use the user's language:
  - practical,
  - direct,
  - implementation-first,
  - no unnecessary theory.

---

## Appendix A — Known project memory snapshot

### CareerSite Agent one-line summary

```text
CareerSite Agent is a human-in-the-loop agentic AI workflow system that discovers jobs, resolves official company postings, parses job descriptions, scores resume fit, assists manual applications, logs results to Google Sheets, prepares recruiter outreach, and later monitors email for status updates.
```

### Current most important implementation rule

```text
Do not optimize for full autonomy. Optimize for reliable assisted workflow with explicit user confirmation.
```

### Current most important technical task

```text
Finish n8n Workflow 2 and Google Sheets append integration.
```

### Current most important user constraint

```text
The user does not want to spend money. Use free/open-source/local options wherever possible.
```

---

## Appendix B — Known unavailable items that should be retrieved from local repo

Before making code changes, ask the user to upload or paste these files if needed:

```text
streamlit_app.py
app/main.py
app/dependencies.py
app/routers/jobs.py
app/routers/pipeline.py
app/routers/tracker.py
app/schemas/job.py
app/services/canonicalization_service.py
app/services/jd_parser_service.py
app/services/scoring_service.py
app/services/tailoring_service.py
app/services/decision_service.py
app/services/recruiter_service.py
app/services/tracker_service.py
app/scrapers/ats/greenhouse_scraper.py
app/scrapers/job_lead_sender.py
scripts/send_job_leads.py
scripts/scrape_and_send_jobs.py
data/master_resume/master_resume.json
data/role_profiles.json
data/skill_taxonomy.json
data/target_companies.json
n8n Workflow 1 export JSON
n8n Workflow 2 export JSON
Google Apps Script code
.env.example or environment variable list
requirements.txt
```

---

## Appendix C — Suggested continuation prompt for Claude

Use this prompt when handing off to Claude:

```text
I am working on CareerSite Agent Automation, a human-in-the-loop job application automation project. Read the attached README fully before answering. We are not starting from scratch. The current stack is Python + FastAPI + Streamlit + n8n + Google Sheets + Discord. The user wants zero-cost/open-source options and does not want paid LLM APIs. The current phase is wiring n8n Workflow 2 and Google Sheets append/status logic. Preserve the existing Google Sheets tracker structure and official-company-link rule. Give exact step-by-step implementation guidance, exact node placement, and full file-level code when needed. Do not invent missing code. If a file is needed, ask for that file or clearly mark the assumption.
```
