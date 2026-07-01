# Production MVP Plan

Goal: reduce the manual cycle from 1-2 hours per 5 applications to a daily human-in-the-loop pipeline that finds, evaluates, prepares, tracks, and follows up on strong-fit roles.

## Production Loop

1. Discover profile-matched jobs from approved sources.
2. Parse each official JD and score base resume fit.
3. Tailor the resume only for roles that pass the fit threshold.
4. Send a compact approval alert with score, reason, official link, tailored resume plan, and recruiter outreach draft.
5. Assist application form filling, but keep final review and submit under user control.
6. Log confirmed applications to Google Sheets.
7. Monitor Gmail and backfill recent messages for status changes.
8. Update Google Sheets status and keep an Email Actions audit trail.

## Immediate Build Priorities

1. Job quality gate
   - Added `data/job_search_profile.json` for target titles, relocation, sponsorship constraints, junior experience level, salary handling, and avoid-list terms.
   - Drop noisy leads before n8n alerts through `JobQualityGateService`.
   - Keep invalid ATS boards from wasting scrape time.

2. Application packet builder
   - Added `data/application_profile.json` for form-fill facts, work authorization answers, resume storage paths, and the manual-submit boundary.
   - Added application packet export through `POST /resume/export-application-packet`.
   - For each approved job, generate a record containing the official JD link, base score, tailored score, resume output path, and prefill profile.
   - Export packet artifacts: resume draft HTML, packet JSON, packet summary, form-fill checklist, JD text, and recruiter outreach draft.
   - Make this the handoff object for both manual apply and browser-assisted apply.

3. Recruiter workflow
   - Improve recruiter discovery beyond a generic LinkedIn search URL.
   - Draft short connection notes and longer follow-up messages.
   - Log recruiter targets and outreach status in the workbook.

4. Browser-assisted application support
   - Added a guarded ATS autofill matcher and local Chrome/Edge/Brave unpacked extension under `browser_assist/ats_autofill_extension`.
   - The extension auto-loads the matching packet from local FastAPI, or sends page URL/title/text so FastAPI can prepare a tailored resume and apply plan without logging an application.
   - Profile-only autofill remains a fallback when there is not enough job description text.
   - Start with prefill support for common ATS fields: name, contact info, location, profile links, work authorization, sponsorship where wording is clear, and relocation.
   - Leave EEO, salary, citizenship/security-clearance, signatures, ambiguous sponsorship, resume upload, and final submit under human control.
   - Keep submit manual.
   - Store reusable application profile fields locally, outside Google Sheets.

5. Production controls
   - Added scraper `--max-send`, `--dry-run`, early job quality gating, and JSON scrape reports.
   - Added queue status reports for packet-ready/reviewable items.
   - Keep Gmail status updates dropdown-safe and auditable.

## User Inputs Needed

- Confirm the generated master resume JSON from the May 24, 2026 PDF is accurate.
- Confirm any additional must-have or must-avoid job keywords.
- Confirm any locations to avoid, if any.
- Confirm any additional application profile fields needed for form filling.
- Approved job sources and company target list.
- Recruiter outreach tone and LinkedIn connection note preferences.

## Human Control Boundary

The system can recommend, tailor, prefill, log, and draft outreach. The user should still approve each application and manually submit it, especially on third-party ATS portals.
