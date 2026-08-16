# API Contracts

## Jobs
- `POST /jobs/normalize`
- `POST /jobs/resolve-official`
- `POST /jobs/parse-jd`

## Resume
- `POST /resume/score`
- `POST /resume/tailor`
- `POST /resume/decide`
- `POST /resume/export-application-packet`

## React Web App
- `GET /webapp/dashboard`
- `POST /webapp/refresh-main`
- `POST /webapp/refresh-fresh24`
- `POST /webapp/prepare-tailored-resume`
- `POST /webapp/arm-autofill`
- `POST /webapp/already-applied`

`POST /webapp/prepare-packet` remains as a compatibility alias for older scripts, but the React UI should use `prepare-tailored-resume`.

## Application Loop
- `POST /application-loop/batches`
- `GET /application-loop/items`
- `POST /application-loop/fit-gate`
- `POST /application-loop/items/{loop_id}/tailoring/drafts`
- `GET /application-loop/items/{loop_id}/tailoring/draft`
- `POST /application-loop/items/{loop_id}/tailoring/preview`
- `POST /application-loop/items/{loop_id}/tailoring/approve`
- `POST /application-loop/items/{loop_id}/tailoring/export`
- `GET /application-loop/items/{loop_id}/tailoring/export`
- `GET /application-loop/items/{loop_id}/tailoring/download/{docx|pdf}`

Tailoring draft and preview operations do not create resume files. Approval persists the reviewed selection for the later export handoff. The export command accepts only output settings and an explicit human confirmation; resume content is loaded from the current persisted approval. Exporting is deterministic and does not call Claude.

## Autofill
- `POST /autofill/context`
- `POST /autofill/profile-context`
- `POST /autofill/preview-html`
- `POST /autofill/autopilot/arm`
- `POST /autofill/autopilot/context`
- `POST /autofill/autopilot/result`

`/autofill/context` is the primary extension endpoint. It matches an existing apply plan, prepares a tailored resume from a full JD page, or falls back to saved profile answers for application-form pages.

## Contacts
- `POST /contacts/find-recruiter`
- `POST /contacts/draft-outreach`

## Tracker
- `POST /tracker/add-row`
- `POST /tracker/update-status`
