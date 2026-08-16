# Loop Engineering Mini-Projects

This project should grow as a set of small, useful human-in-the-loop systems. The target is not a fully autonomous job bot. The target is to reduce Akhilesh's weekday application cycle time while preserving the manual judgment, final edits, and final submit boundary that already make the process trustworthy.

Core rule:

> Automation prepares. Akhilesh commits.

Every mini-project below should be shippable on its own, teach a specific agentic AI or loop-engineering pattern, and leave the repo in a better state after one focused commit.

## Current Manual Loop

1. Pull candidate jobs from Jobright.
2. Ask Claude whether the JD is worth applying to.
3. If yes, ask Claude to tailor the base resume to the JD.
4. Review the draft.
5. Ask Claude to revise when the draft is weak or misweighted.
6. Download the final tailored resume.
7. Upload to Word Online.
8. Make cosmetic edits.
9. Export PDF.
10. Apply manually in the ATS.
11. Log the job in Google Sheets while tailoring or applying.
12. After about 10 applications, search LinkedIn for recruiters.
13. Ask Claude to tailor a recruiter connection note.
14. Send the connection request manually.
15. Repeat the loop for the next batch.

## Loop Design Principles

- Keep the user's review step explicit.
- Keep final ATS submit manual.
- Prefer proposals over silent writes.
- Preserve the Google Sheets schema exactly.
- Use Claude where language quality, judgment, or ambiguity matters.
- Use deterministic code for state, exports, validation, dedupe, and guardrails.
- Make every agent return structured data plus a human-readable reason.
- Treat every rejected, revised, approved, or submitted item as training signal for the next loop.

## GitHub Shipping Protocol

After each mini-project:

1. Inspect `git status --short --branch`.
2. Stage only the files changed for that mini-project.
3. Run the smallest relevant test or syntax check.
4. Commit with a clear user-authored project message.
5. Push to `origin/main`, unless a branch/PR is explicitly requested.
6. Record what changed and what was verified in the task response.

## Today-Friendly Mini-Projects

### 1. Application Loop State Model

Implementation status: shipped as the deterministic foundation for later loops.

User payoff:
- A single shared vocabulary for where each job is in the process.
- Prevents the backend, Third Eye, n8n, and Sheets from inventing conflicting statuses.

Loop pattern:
- State machine with human gates.

Suggested states:
- `imported`
- `fit_checked`
- `skipped`
- `draft_ready`
- `revision_requested`
- `approved_for_apply`
- `ats_opened`
- `submitted_confirmed`
- `sheet_logged`
- `recruiter_note_ready`
- `outreach_done`

Acceptance criteria:
- Add a typed schema for loop state.
- Add transition validation.
- Block `submitted_confirmed` unless the request includes human confirmation.
- Add tests for allowed and blocked transitions.

Likely files:
- `app/schemas/application_loop.py`
- `app/services/application_loop_service.py`
- `tests/test_application_loop_service.py`

What this mini-project teaches:
- Agent orchestration needs explicit state, not a pile of loosely related automation flags.
- The transition table is deterministic; no LLM is needed to decide whether a transition is legal.
- Every transition creates an audit event, so later metrics can measure revision cycles and waiting time.
- `submitted_confirmed` is a human-only gate. An agent or scheduled workflow cannot claim an application was submitted.

Implemented transition loop:

```text
imported -> fit_checked -> draft_ready -> approved_for_apply -> ats_opened
              |                ^  |                |               |
              |                |  v                v               v
              +-> skipped      +-- revision_requested      submitted_confirmed
                                                               |
                                              +----------------+----------------+
                                              v                                 v
                                         sheet_logged -> recruiter_note_ready -> outreach_done
```

`approved_for_apply` can also move directly to `submitted_confirmed` when Akhilesh applies
without using the ATS assistant. Pre-submission states may move to `skipped` when new evidence
changes the decision.

### 2. Ten-Job Batch Inbox

User payoff:
- Paste or collect 10 Jobright links/JDs and process them as one batch instead of one tab at a time.

Loop pattern:
- Event ingestion plus queue normalization.

Acceptance criteria:
- Accept a batch of job URLs or raw JDs.
- Normalize each item into a loop item.
- Dedupe by canonical link first, then company plus role.
- Return a batch summary with counts: imported, duplicate, invalid.

Likely files:
- `app/api/application_loop.py`
- `app/services/application_loop_service.py`
- `frontend/src/main.jsx`
- `frontend/src/styles.css`

### 3. Fit Gate Agent

User payoff:
- Claude quickly says Apply, Maybe, or Skip for each job, with a short reason and risk flags.

Loop pattern:
- LLM judgment loop with deterministic guardrails.

Acceptance criteria:
- Return `apply`, `maybe`, or `skip`.
- Include sponsorship, seniority, location, title-fit, and skills-fit notes.
- Use cheap deterministic filters before Claude.
- Use Claude only for the uncertain or high-value items.

Likely files:
- `app/services/job_quality_gate_service.py`
- `app/services/llm_match_service.py`
- `app/services/application_loop_service.py`
- `tests/test_application_loop_service.py`

### 4. Tailoring Review Loop

User payoff:
- Resume drafts become interactive: accept, revise with instructions, change bullet counts per subsection, regenerate, then approve.

Loop pattern:
- Propose, critique, revise, approve.

Acceptance criteria:
- Preserve user-selected bullet counts per subsection.
- Keep resume bullets in Google XYZ format.
- Ground every bullet to master resume, projects, work experience, or publications.
- Add a revision reason log so repeated fixes become visible.
- No file export until approval.

Likely files:
- `app/services/tailoring_review_service.py`
- `app/services/claude_tailoring_service.py`
- `app/schemas/tailoring_review.py`
- `browser_assist/ats_autofill_extension/content.js`
- `tests/test_tailoring_review_service.py`

### 5. Export Handoff Loop

User payoff:
- After approval, generate DOCX and PDF locally so Word Online becomes optional instead of mandatory.

Loop pattern:
- Human approval gate before side effects.

Acceptance criteria:
- Generate DOCX and PDF only after approval.
- Preserve a stable output folder per company and role.
- Include the JD, tailored resume, apply plan, and optional cover letter.
- Show download links in Third Eye.

Likely files:
- `app/services/application_packet_export_service.py`
- `app/services/resume_render_service.py`
- `browser_assist/ats_autofill_extension/content.js`
- `tests/test_application_packet_export.py`

### 6. Sheets Logging Proposal

User payoff:
- The row is ready while the resume is being tailored, but it is not marked Applied until Akhilesh confirms manual submission.

Loop pattern:
- Proposal then commit.

Acceptance criteria:
- Produce a Google Sheets row preview using the exact canonical columns.
- Use `Status = Not Yet Applied Due to Technical Issue` for portal failures.
- Use `Applied Using = Company Website` for ATS/company career pages.
- Do not write `Status = Applied` without manual submit confirmation.
- Dedupe by link first, then company plus role.

Likely files:
- `app/services/tracker_service.py`
- `app/services/copilot_service.py`
- `google_cloud/Code.gs`
- `tests/test_tracker.py`

### 7. ATS Apply Assist Loop

User payoff:
- Open the ATS, prefill safe fields, surface unknown questions, and keep final submit manual.

Loop pattern:
- Controlled autonomy with a hard stop.

Acceptance criteria:
- Detect safe fields and prefill them.
- Never fill sensitive fields unless explicitly approved.
- Never click final submit.
- Show unknown questions as a review checklist.
- Record portal failures as a technical issue proposal for Sheets.

Likely files:
- `app/services/ats_autofill_service.py`
- `app/services/autofill_autopilot_service.py`
- `browser_assist/ats_autofill_extension/content.js`
- `tests/test_ats_autofill.py`

### 8. Recruiter Outreach Batch

User payoff:
- After 10 applications, generate recruiter search links and tailored connection notes in one batch.

Loop pattern:
- Batch post-processing loop.

Acceptance criteria:
- Group applied jobs by company.
- Generate LinkedIn recruiter search URLs.
- Draft one concise connection note per recruiter/company/role.
- Keep send action manual.
- Track outreach done separately from application submitted.

Likely files:
- `app/services/recruiter_service.py`
- `app/services/recruiter_outreach_agent.py`
- `frontend/src/main.jsx`
- `tests/test_career_agents.py`

### 9. Loop Metrics Dashboard

User payoff:
- See where time is being lost: fit checks, tailoring revisions, ATS blockers, Sheets logging, or recruiter outreach.

Loop pattern:
- Feedback loop and continuous improvement.

Acceptance criteria:
- Track timestamps per loop state.
- Show counts for imported, skipped, draft-ready, approved, submitted, logged, and outreach done.
- Show average revision count per resume.
- Show common skip reasons and portal-failure reasons.

Likely files:
- `app/services/application_loop_service.py`
- `app/api/application_loop.py`
- `frontend/src/main.jsx`
- `frontend/src/styles.css`

## Recommended Build Order

For the next working session, ship in this order:

1. Application Loop State Model
2. Sheets Logging Proposal
3. Ten-Job Batch Inbox
4. Fit Gate Agent
5. Tailoring Review Loop
6. Export Handoff Loop
7. Recruiter Outreach Batch
8. Loop Metrics Dashboard

The first two are the foundation. They protect your manual system from being broken by later automation.

## What Makes This Repo More Than Another AI-Coded Project

- It models a real recurring human workflow.
- It has explicit human gates.
- It treats manual edits and re-prompts as product signals.
- It uses AI where AI is useful and deterministic code where reliability matters.
- It produces useful artifacts even when the user chooses not to apply.
- It preserves the user's existing Google Sheets system instead of forcing a redesign.
- It demonstrates orchestration across FastAPI, n8n, browser extension, local files, and Google Sheets.
