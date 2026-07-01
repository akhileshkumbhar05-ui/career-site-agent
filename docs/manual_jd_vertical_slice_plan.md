# Manual JD Vertical Slice Plan

This slice keeps the existing architecture intact and adds a practical paste-JD workflow for daily application review.

## Scope

1. Paste a job description and core job metadata into the React dashboard.
2. Run deterministic JD parsing, quality gate, match scoring, and guarded tailoring.
3. Show a recommendation: apply, manual review, or reject.
4. Generate a safe apply plan that separates autofill-safe profile fields from human-only questions.
5. Log to the legacy Google Sheets row format only after human confirmation, or log a technical issue with the matching controlled status.

## Guardrails

- No direct Jobright scraping.
- No auto-submit path.
- No fabricated resume claims.
- No `Applied` status unless the user confirms manual submission.
- No sheet redesign: the sheet row is exactly:
  `Date, Company Applied, Role, Salary Quoted while Applying, Job Posted On, Applied Using, Status, Link`.
- Duplicate prevention checks canonical `Link` first, then `Company Applied + Role`.
- Every sheet-style write attempt creates a local audit event.

## Next Build Steps

1. Replace rule-based JD extraction with an optional LLM parser adapter behind the same response schema.
2. Connect the confirmed write path to the configured Google Apps Script when credentials are present.
3. Add browser extension handoff for the generated safe apply plan.
4. Add official ATS feed ingestion for Greenhouse, Ashby, Lever, Workday, and selected company APIs.
