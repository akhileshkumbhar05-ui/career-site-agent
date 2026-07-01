# n8n Workflow Overview

This folder contains the active importable n8n workflows for CareerSite Agent.

## Required URLs and secrets

- FastAPI URL from inside n8n: use `http://host.docker.internal:8000` for Docker Desktop, or `http://127.0.0.1:8000` if n8n runs directly on Windows.
- Discord webhook URL: paste directly into Discord HTTP Request nodes if your n8n instance blocks `$env`.
- Google Apps Script web app URL: paste directly into WF4's `Update Status in Sheets` node if your n8n instance blocks `$env`.
- `N8N_JOB_LEAD_WEBHOOK_URL`: Used by `scripts/scrape_and_send_jobs.py`; defaults to `http://localhost:5678/webhook/incoming-job-lead`.

## Workflows

- `WF1_Manual_FastAPI_Discord_Test.json`: manual smoke test for FastAPI processing and Discord notification.
- `WF2_Incoming_Job_Lead_Processor.json`: production lead intake webhook at `/webhook/incoming-job-lead`.
- `WF3_Confirmed_Application_To_Sheets.json`: explicit confirmed-application path that logs to Google Sheets through FastAPI.
- `WF4_Gmail_Status_Monitor.json`: Gmail trigger that classifies unread application emails, updates Sheets status, and logs actions to the `Email Actions` sheet.
- `WF5_Email_Backfill_Scanner.json`: scheduled Gmail backfill scanner for recent read/unread status-change emails that WF4 may miss. It posts summary messages instead of one Discord request per email.
- `WF6_Queue_Worker_Scheduler.json`: background queue worker that claims queued WF2 leads, runs scoring/packet export, renders PDFs, and summarizes processed items in Discord.

## WF2 and WF6 queue flow

WF2 is intentionally lightweight. It accepts production job leads at `/webhook/incoming-job-lead` and enqueues them through FastAPI at `/queue/enqueue`.

WF6 runs every 10 minutes and calls `/queue/process-next` with a batch limit of 5. It processes queued leads into `packet_ready`, `manual_review`, `rejected`, or `failed` states. It only posts a Discord summary when work was processed, so empty queue runs stay quiet.

Packet output is kept under `data/outputs/queue_packets` during testing. Move WF6's `output_root_override` to the real resume archive only after you approve packet quality.

FastAPI writes processed leads to the local SQLite tracker with `Not Applied`. Google Sheets logging is intentionally kept for confirmed applications through WF3 or `/tracker/log-to-sheets`.

The Google Sheet keeps job/reference ids inside the `Role` column instead of a separate column. FastAPI formats confirmed applications as `Role (job_id)` when a separate id is present, matching the manual sheet convention.

To review packet-ready leads without opening SQLite or n8n, run:

```powershell
.\.venv\Scripts\python.exe scripts\queue_status_report.py --limit 50
```

WF6 packet exports include `apply_plan.json` for browser-assisted form filling, `ats_answer_bank.md` for fast copy/paste answers, and `recruiter_outreach.txt` with LinkedIn search targets plus outreach drafts.

## Gmail email action logging

Deploy `google_cloud/Code.gs` v14 before enabling the updated WF4 or WF5 sheet nodes. The Apps Script creates an `Email Actions` tab automatically, validates status updates against the live sheet dropdown, and records every actionable or manual-review email result. Acknowledgement emails are logged but do not rewrite the default `Applied` status.

Email reasoning is configured in `data/email_status_rules.json`. Add or tune rules there so production behavior follows the sheet dropdown values instead of Python code edits.
