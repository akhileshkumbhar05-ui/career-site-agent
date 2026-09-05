# Production Runbook

This is the daily operating process for CareerSite Agent after the FastAPI, n8n, Apps Script, Discord, and Google Sheets pieces have been tested.

## Production State

Keep these workflows published in n8n:

- `WF2_Incoming_Job_Lead_Processor`
- `WF3_Confirmed_Application_To_Sheets`, if confirmed application logging uses the n8n webhook
- `WF4_Gmail_Status_Monitor`
- `WF6_Queue_Worker_Scheduler`
- `WF5_Email_Backfill_Scanner`

Keep this workflow unpublished:

- `WF1_Manual_FastAPI_Discord_Test`

Old workflows should stay disabled or be deleted after the new workflows are verified:

- `WF2_Lead_Processor`
- `WF3_Post_Application_Logger`

## Required Services

Docker Desktop must be running.

n8n must be reachable at:

```text
http://127.0.0.1:5678
```

FastAPI must be running from the project root on port `8000` (the shared backend port used by the React app and all n8n workflows):

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

FastAPI health should return `ok`:

```text
http://127.0.0.1:8000/health
```

The React frontend runs from `frontend`:

```powershell
cd frontend
npm run dev
```

React should be reachable at:

```text
http://127.0.0.1:5173
```

## Required Configuration

The active environment file is the root `.env`:

```text
D:\Resume Revamp Projects\AgenticAI_Projects\career-site-agent\.env
```

Required values:

```env
GOOGLE_APPS_SCRIPT_URL=https://script.google.com/macros/s/.../exec
N8N_JOB_LEAD_WEBHOOK_URL=http://localhost:5678/webhook/incoming-job-lead
```

Discord can be configured either in `.env` or pasted directly into n8n Discord HTTP Request nodes. In this n8n instance, direct node URLs are safer because `$env` access inside node expressions is blocked.

Email classification status rules are configured in:

```text
D:\Resume Revamp Projects\AgenticAI_Projects\career-site-agent\data\email_status_rules.json
```

The statuses in that file should mirror the dropdown values in the Google Sheet `Status` column. Apps Script also validates against the live sheet dropdown before writing a status.

Job discovery filtering is configured in:

```text
D:\Resume Revamp Projects\AgenticAI_Projects\career-site-agent\data\job_search_profile.json
```

This file controls target role families, junior experience thresholds, relocation preferences, work authorization blockers, citizenship/clearance exclusions, and resume output naming.

Application form-fill facts are configured in:

```text
D:\Resume Revamp Projects\AgenticAI_Projects\career-site-agent\data\application_profile.json
```

This file is the source for reusable profile fields and the manual-submit boundary. The system may prefill application portals, but the user reviews and submits.

## Readiness Check

Run this before a production scrape:

```powershell
.\.venv\Scripts\python.exe scripts\check_production_readiness.py
```

Expected result:

- No failures
- Warnings are acceptable only if they are intentional, such as Discord being pasted directly in n8n instead of stored in `.env`

With Docker running, the readiness command exports the live n8n definitions read-only and verifies:

- WF2, WF3, WF4, WF5, and WF7 are active.
- WF7's pipeline body and Discord summary code match the repository export.
- Direct Apps Script endpoints used by active workflows serve the current script version and all controlled statuses.
- The Gmail Trigger has no polling errors in the previous six minutes.

Live endpoint URLs are never printed; the report uses short SHA-256 fingerprints. Use
`--skip-live-n8n` only when intentionally checking a machine without the local n8n container.

## Daily Workflow

1. Start Docker Desktop.
2. Confirm n8n is running at `http://localhost:5678`.

Always use `localhost` for the n8n editor. Its Google OAuth callback is also on `localhost`; opening
the editor on `127.0.0.1` creates a separate cookie scope and makes the OAuth popup return `Unauthorized`.
3. Start FastAPI for the React app:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

4. Start the React frontend:

```powershell
cd frontend
npm run dev
```

5. Run readiness check:

```powershell
.\.venv\Scripts\python.exe scripts\check_production_readiness.py
```

6. Run the scraper:

```powershell
.\.venv\Scripts\python.exe scripts\scrape_and_send_jobs.py
```

For a controlled production run, prefer a cap:

```powershell
.\.venv\Scripts\python.exe scripts\scrape_and_send_jobs.py --max-send 25
```

For a no-send audit before a real run:

```powershell
.\.venv\Scripts\python.exe scripts\scrape_and_send_jobs.py --dry-run --max-send 25
```

The scraper now applies the same job quality gate before sending leads to n8n, writes scrape reports under `data\outputs\scrape_reports`, and skips leads blocked by seniority, citizenship, clearance, sponsorship, or non-target role filters. Use `--max-jobs-per-company` to keep large boards from consuming the whole run.

7. WF2 queues each incoming lead in SQLite and posts a Discord queue confirmation.
8. WF6 runs every 10 minutes, claims up to 5 queued leads, scores them, exports tailored resume/apply-plan artifacts, renders PDFs, and posts a Discord summary only when work was processed.
9. Review prepared leads under:

```text
D:\Resume Revamp Projects\AgenticAI_Projects\career-site-agent\data\outputs\queue_packets
```

You can also generate a compact review report instead of browsing the queue manually:

```powershell
.\.venv\Scripts\python.exe scripts\queue_status_report.py --limit 50
```

Reports are written under:

```text
D:\Resume Revamp Projects\AgenticAI_Projects\career-site-agent\data\outputs\queue_reports
```

10. Apply only after human review. Browser-assisted prefill is allowed, but final submit stays manual.
   For browser-assisted prefill, load the local Third Eye watcher extension from:

```text
D:\Resume Revamp Projects\AgenticAI_Projects\career-site-agent\browser_assist\ats_autofill_extension
```

   Keep FastAPI running on `8000`, then just browse to any job posting or ATS application page. There is no popup; the watcher panel appears automatically top-right. It continuously sends the current page URL/title/text and form fields to `http://127.0.0.1:8000/autofill/observe`, where Claude classifies the page, understands the JD, and proposes safe fills.
   On a job-description page, click `Tailor resume for this JD` in the panel to generate a tailored resume and apply plan under:

```text
D:\Resume Revamp Projects\AgenticAI_Projects\career-site-agent\data\outputs\autofill_packets
```

   On an application page, click `Fill safe fields` to apply the suggested fills. The watcher fills only high-confidence fields and leaves resume upload, EEO, salary, citizenship/security-clearance, ambiguous sponsorship, signatures, and final submit to you. Nothing is ever submitted automatically.
11. Log confirmed applications through WF3 or the FastAPI `/tracker/log-to-sheets` path. Keep this pointed at the testing Apps Script URL until you intentionally switch to the real documentation sheet.
12. Let WF4 monitor unread Gmail messages and update application statuses in the testing Google Sheet.
13. Keep WF5 paused unless you intentionally need backfill. It can be noisy if the Gmail query is too broad.

The `Jobs Applied` sheet intentionally has no separate `job_id` column. When automation receives a separate job/reference id, FastAPI writes it into the `Role` value, for example `Associate Decision Scientist, Market Share (1027197BR)`. If the role already contains the id, it is not duplicated.

## Webhook URLs

WF2 production job intake:

```text
http://127.0.0.1:5678/webhook/incoming-job-lead
```

WF2 test mode:

```text
http://127.0.0.1:5678/webhook-test/incoming-job-lead
```

WF3 production confirmed application logging:

```text
http://127.0.0.1:5678/webhook/confirmed-application
```

WF3 test mode:

```text
http://127.0.0.1:5678/webhook-test/confirmed-application
```

## Recovery

If WF2 fails at `Process Job in FastAPI`:

- Confirm FastAPI is running.
- Confirm the node URL points to the shared backend port: `http://host.docker.internal:8000/queue/enqueue`. Start FastAPI on `8000` so n8n (in Docker) and the React app reach the same backend.
- Confirm the body fields read from `$json.body`.

If WF6 does not process queued leads:

- Confirm FastAPI is running.
- Confirm WF6 is active in n8n.
- Confirm n8n startup logs include `Activated workflow "WF6_Queue_Worker_Scheduler"`.
- Confirm the `Process Queue in FastAPI` node URL points to the shared backend port: `http://host.docker.internal:8000/queue/process-next`.
- Run this manual worker command from the project root to process the queue without waiting for the schedule:

```powershell
.\.venv\Scripts\python.exe scripts\process_job_queue.py --limit 5 --output-root data\outputs\queue_packets --render-pdf
```

If WF3 does not write to Google Sheets:

- Confirm `.env` contains the current Apps Script Web App URL.
- Restart FastAPI after editing `.env`.
- Confirm `google_cloud/Code.gs` has been deployed as the Apps Script web app.

If WF4 does not publish:

- Open `Gmail Trigger`.
- Set Poll Times to `Every X` minutes with value `10`, or use `Every Minute` temporarily.
- Save and publish again.

If WF4 does not update status:

- Confirm `Update Status in Sheets` uses the current Apps Script Web App URL.
- Confirm the company name extracted from the email matches the company name in the `Jobs Applied` sheet closely enough.
- Check Discord low-confidence alerts for emails that need manual review.

If WF5 backfill is noisy or repeats messages:

- Confirm `Get Recent Gmail Messages` is using a reasonable Gmail search query and limit.
- Confirm `Extract Backfill Email Fields` still has workflow static data enabled; it remembers processed message IDs for 14 days.
- Disable WF5 temporarily if you need to tune the query before it posts more Discord summaries.

If email actions do not appear in Google Sheets:

- Deploy the current `google_cloud/Code.gs` as a new Apps Script web app version.
- Confirm WF4 and WF5 sheet HTTP nodes use the current Apps Script Web App URL.
- Check for an `Email Actions` tab; the script creates it automatically on the first email action write.

If acknowledgement emails reset or spam statuses:

- Confirm `google_cloud/Code.gs` is deployed at v16 or newer.
- Confirm FastAPI is running with the config-driven classifier from `data/email_status_rules.json`.
- WF4 and WF5 should log acknowledgement emails to `Email Actions`, but should not rewrite the `Jobs Applied` status column for them.

## Tailored Resume And Apply Plan Export

The queue worker response includes tailored resume and apply-plan artifact details for actionable leads. WF6 creates those artifacts automatically by calling:

```text
POST http://127.0.0.1:8000/queue/process-next
```

The exporter writes:

- tailored resume draft HTML in the company folder
- `application_packet.json`
- `apply_plan.json`
- `ats_answer_bank.md`
- `application_packet.md`
- `form_fill_checklist.md`
- `job_description.txt`
- `recruiter_outreach.txt`

`apply_plan.json` is the machine-readable handoff for future browser-assisted form filling. It includes job details, scores, selected projects, rewritten bullets, ATS answer bank, recruiter searches, and the manual-submit boundary. `ats_answer_bank.md` is the human-readable version for fast copy/paste during applications.

You can preview how an ATS page would be mapped before using the browser extension:

```powershell
.\.venv\Scripts\python.exe scripts\ats_autofill_preview.py --apply-plan "<path-to-apply_plan.json>" --html-file "<saved-ats-page.html>" --output-json data\outputs\autofill_preview\plan.json
```

The intended PDF path is included in the response. Set `render_pdf` to `true` in the export request to attempt PDF rendering through local Microsoft Edge headless printing. If Edge is unavailable or rendering fails, the response still returns the HTML draft and includes `pdf_error`.

The exporter also returns `quality_passed` and `quality_checks`. These checks verify required resume sections, unresolved template tokens, basic ATS-safe text structure, supported rewritten metrics, PDF existence, and PDF size. Install `pypdf` from `requirements.txt` to enable PDF text extraction checks inside the project virtual environment.

During testing, packet files are written under:

```text
D:\Resume Revamp Projects\AgenticAI_Projects\career-site-agent\data\outputs\queue_packets\<Company>
```

The tailored resume draft HTML and PDF are written directly inside the company folder beside the packet folder. Move WF6's `output_root_override` to the real resume archive only after packet quality is approved.

If the classifier reasoning looks wrong:

- Update `data/email_status_rules.json` instead of editing Python code.
- Keep each rule's `status` empty for log-only or ignored emails.
- Use only statuses that exist in the sheet dropdown; Apps Script will skip invalid statuses.
- Restart FastAPI if it is not running with `--reload`.

## Production Rules

- Keep Google Sheets as the source of truth for confirmed applications.
- Keep the `Email Actions` tab as the audit trail for Gmail-derived updates and manual-review items.
- Let SQLite remain a local cache and processing tracker.
- Do not auto-apply. The system recommends and logs; the user confirms.
- Do not route stale jobs straight to hard rejection unless they are clearly invalid.
- Keep WF1 as a smoke test only.
