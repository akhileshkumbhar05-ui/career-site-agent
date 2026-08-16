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
Fit Gate skips can return to `fit_checked` only through a human override with a recorded reason.

### 2. Ten-Job Batch Inbox

Implementation status: shipped as the persistent intake queue for the daily application loop.

User payoff:
- Paste or collect 10 Jobright links/JDs and process them as one batch instead of one tab at a time.

Loop pattern:
- Event ingestion plus queue normalization.

Acceptance criteria:
- Accept a batch of job URLs or raw JDs.
- Normalize each item into a loop item.
- Dedupe by canonical link first, then company plus role.
- Return a batch summary with counts: imported, duplicate, invalid.

Implemented behavior:
- The React Batch Inbox accepts up to 10 entries, including bulk-pasted links and per-entry raw JDs.
- Missing company and role labels are inferred from labeled JD text or the canonical URL when possible.
- Mixed batches are partial-success: invalid and duplicate entries do not block valid imports.
- Imported loop items and their source JD text persist in SQLite for the later fit and tailoring loops.
- Importing creates only the `imported` loop state. It does not score, tailor, submit, or write to Google Sheets.

Endpoints:
- `POST /application-loop/batches`
- `GET /application-loop/items`

Likely files:
- `app/api/application_loop.py`
- `app/services/application_loop_service.py`
- `frontend/src/main.jsx`
- `frontend/src/styles.css`

### 3. Fit Gate Agent

Implementation status: shipped as the guarded decision step between inbox import and tailoring.

User payoff:
- Claude quickly says Apply, Maybe, or Skip for each job, with a short reason and risk flags.

Loop pattern:
- LLM judgment loop with deterministic guardrails.

Acceptance criteria:
- Return `apply`, `maybe`, or `skip`.
- Include sponsorship, seniority, location, title-fit, and skills-fit notes.
- Use cheap deterministic filters before Claude.
- Use Claude only for the uncertain or high-value items.

Implemented behavior:
- Batch and per-item runs return `apply`, `maybe`, or `skip` with a score and concise rationale.
- Sponsorship, seniority, location, title fit, and skills fit evidence persist on each loop item.
- Deterministic hard blockers return `skip` without calling Claude.
- URL-only items remain `imported` with `needs_jd`; they do not spend a model call or pretend to be scored.
- Persisted Fit Gate results and the semantic-match cache prevent unchanged jobs from consuming tokens again.
- Human overrides require a reason and are appended to Fit Gate history. Only a human can restore a skipped item.
- The configured Anthropic model is `claude-sonnet-5`; adaptive thinking is disabled for this compact JSON judgment.
- Fit Gate does not tailor, submit, or write to Google Sheets.

Endpoints:
- `POST /application-loop/fit-gate`
- `PUT /application-loop/items/{loop_id}/jd`
- `POST /application-loop/items/{loop_id}/fit-override`

Likely files:
- `app/services/job_quality_gate_service.py`
- `app/services/llm_match_service.py`
- `app/services/application_loop_service.py`
- `tests/test_application_loop_service.py`

### 4. Tailoring Review Loop

Implementation status: shipped as the persisted propose, critique, revise, and approve loop.

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

Implemented behavior:
- Only a Fit Gate `apply` decision can spend the first tailoring call.
- Drafts persist against the application-loop item and can be reopened without another model call.
- The full resume preview is the primary review surface; summary, grounded rewrites, projects, papers, optional cover letter, and per-subsection bullet counts remain editable beside it.
- Preview refreshes are local and free. A new Claude call happens only when Akhilesh submits a revision reason and regenerates the draft.
- Every regeneration records the human revision reason, increments the revision count, and keeps the prior draft reference in history.
- Approval stores the exact reviewed selection and moves the item to `approved_for_apply`; it does not create DOCX or PDF files.
- Sonnet 5 caches the stable resume/profile prompt prefix for batch reuse, uses medium adaptive-thinking effort, and has an 8,192-token response cap.
- Engine provenance and token/cache usage are persisted. A rule-based fallback is never labeled as Claude-authored.

Endpoints:
- `POST /application-loop/items/{loop_id}/tailoring/drafts`
- `GET /application-loop/items/{loop_id}/tailoring/draft`
- `POST /application-loop/items/{loop_id}/tailoring/preview`
- `POST /application-loop/items/{loop_id}/tailoring/approve`

Likely files:
- `app/services/tailoring_review_service.py`
- `app/services/claude_tailoring_service.py`
- `app/schemas/tailoring_review.py`
- `browser_assist/ats_autofill_extension/content.js`
- `tests/test_tailoring_review_service.py`

### 5. Export Handoff Loop

Implementation status: shipped as an approval-gated deterministic export and download handoff.

User payoff:
- After approval, generate DOCX and PDF locally so Word Online becomes optional instead of mandatory.

Loop pattern:
- Human approval gate before side effects.

Acceptance criteria:
- Generate DOCX and PDF only after approval.
- Preserve a stable output folder per company and role.
- Include the JD, tailored resume, apply plan, and optional cover letter.
- Show download links in Third Eye.

Implemented behavior:
- Only the current persisted approval can be exported; the request accepts output location, PDF preference, and explicit human confirmation, but no resume content.
- DOCX is always generated. PDF is generated on request through the existing local Edge renderer.
- The packet keeps the JD, apply plan, resume HTML, quality metadata, and optional approved cover letter beside the resume files.
- The application-loop item persists export version, paths, quality checks, PDF errors, and download routes. Reopening and downloading do not regenerate files.
- A chosen output root still preserves the company and role folder structure. Leaving it blank uses the configured resume directory.
- Starting a new Claude revision clears both the old approval and export handoff.
- The Batch Inbox shows the approved handoff, quality state, output folder, direct DOCX/PDF downloads, and the canonical ATS link.
- Export is deterministic and consumes no Claude tokens.

Endpoints:
- `POST /application-loop/items/{loop_id}/tailoring/export`
- `GET /application-loop/items/{loop_id}/tailoring/export`
- `GET /application-loop/items/{loop_id}/tailoring/download/{docx|pdf}`

Likely files:
- `app/services/application_packet_export_service.py`
- `app/services/resume_render_service.py`
- `browser_assist/ats_autofill_extension/content.js`
- `tests/test_application_packet_export.py`

### 6. Sheets Logging Proposal

Implementation status: shipped as a proposal-then-commit backend loop.

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

What this mini-project teaches:
- Side effects should have separate prepare and commit operations.
- A proposal can contain the exact eight columns while leaving `Date` and `Status` blank until submission.
- Deterministic rules resolve discovery source and final application channel without spending LLM tokens.
- Duplicate checks normalize links and check them before company plus role.
- The FastAPI service and Apps Script both enforce the manual submission gate, so bypassing one layer is not enough.

Endpoints:
- `POST /copilot/prepare-log` returns the canonical row without writing it.
- `POST /copilot/confirm-log` writes only after confirmation, or records the controlled technical-issue status.

The configured Apps Script path writes Google Sheets and mirrors successful writes locally. When Apps Script is
not configured, the confirmed row remains in the local tracker and the response names that destination explicitly.

### 7. ATS Apply Assist Loop

Implementation status: shipped as an approved-export handoff with guarded prefill and an explicit human outcome gate.

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

Implemented behavior:
- ATS Apply Assist can be armed only from an approved application-loop item with an existing DOCX and apply plan. PDF is preferred when available; file upload remains manual.
- The Batch Inbox opens the canonical application URL after arming one correlated Third Eye task. The extension fills only safe text, select, and radio fields without overwriting existing values.
- Sensitive fields are always skipped. Unknown questions, manual uploads, manual-review answers, and protected fields return to the inbox as a review checklist.
- The extension result automatically updates filled, manual, and protected counts on the application-loop item. Reopening the status does not spend a model call.
- The interface keeps resume upload, sensitive answers, final review, and final submit behind a visible human hard stop. No code path clicks submit.
- A portal-failure outcome keeps the item at `ats_opened` and prepares the exact controlled Sheets status `Not Yet Applied Due to Technical Issue`; it never marks the job Applied.
- `submitted_confirmed` still requires a human actor, a written note, and the explicit manual-submission flag. That command prepares an `Applied` row for the separate Sheets logging loop but does not write it.
- Regenerating the approved export invalidates the prior ATS handoff so stale resume and apply-plan paths cannot be reused silently.

Endpoints:
- `POST /application-loop/items/{loop_id}/ats-assist/arm`
- `GET /application-loop/items/{loop_id}/ats-assist`
- `POST /application-loop/items/{loop_id}/ats-assist/outcome`
- `POST /autofill/autopilot/result` records the extension result and synchronizes its correlated application-loop item.

Likely files:
- `app/services/ats_autofill_service.py`
- `app/services/autofill_autopilot_service.py`
- `browser_assist/ats_autofill_extension/content.js`
- `tests/test_ats_autofill.py`

### 8. Recruiter Outreach Batch

Status: shipped.

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

Implemented behavior:
- Up to 10 manually submitted jobs are prepared in one batch and grouped by company in the API response.
- Deterministic LinkedIn people-search URLs include company, role, recruiter, and talent-acquisition terms.
- One Sonnet request drafts all uncached notes in the batch; unchanged jobs reuse their persisted note without another call.
- Each note is grounded in the master-resume evidence and job context, capped at 300 characters, and editable before use.
- If Claude is unavailable or returns an invalid batch, the UI labels the persisted note as a deterministic fallback.
- LinkedIn search, copying, recruiter-name personalization, and final sending remain manual.
- `submitted_confirmed` or `sheet_logged` advances to `recruiter_note_ready` when a note is prepared.
- Only an explicit human send confirmation advances `recruiter_note_ready` to `outreach_done`.

Endpoints:
- `POST /application-loop/recruiter-outreach/batches`
- `PUT /application-loop/items/{loop_id}/recruiter-outreach`
- `POST /application-loop/items/{loop_id}/recruiter-outreach/sent`

Likely files:
- `app/services/recruiter_service.py`
- `app/services/recruiter_outreach_batch_service.py`
- `frontend/src/main.jsx`
- `tests/test_application_recruiter_outreach_loop.py`

### 9. Loop Metrics Dashboard

Status: shipped.

User payoff:
- See where time is being lost: fit checks, tailoring revisions, ATS blockers, Sheets logging, or recruiter outreach.

Loop pattern:
- Feedback loop and continuous improvement.

Acceptance criteria:
- Track timestamps per loop state.
- Show counts for imported, skipped, draft-ready, approved, submitted, logged, and outreach done.
- Show average revision count per resume.
- Show common skip reasons and portal-failure reasons.

Implemented behavior:
- Four local-history windows cover today, 7 days, 30 days, and all time without making a Claude call.
- The milestone funnel counts every state an application reached, including separate skipped exits, rather than only its current state.
- Stage timing uses the first valid chronological transition for each completed pair and reports averages, medians, and sample counts.
- The slowest completed transition is surfaced as the current bottleneck with its evidence count.
- Quality and completion signals include tailoring revisions, tailoring score lift, portal issues, submission rate, post-submit Sheets logging, recruiter outreach, and intake-to-submit time.
- Skip and portal-failure reasons are grouped alongside current-state distribution so recurring blockers remain visible.
- Metrics are derived from the existing persisted application history. The state machine, human gates, Google Sheets format, and workflow behavior are unchanged.

Endpoint:
- `GET /application-loop/metrics?window={today|7d|30d|all}`

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
