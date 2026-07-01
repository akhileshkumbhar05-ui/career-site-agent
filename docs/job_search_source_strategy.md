# Job Search Source Strategy

## Goal

Build a Jobright-style job discovery engine for Akhilesh that reduces daily manual job hunting by collecting fresh, relevant, apply-worthy roles before resume tailoring or autofill starts.

## Jobright Product Reference

Jobright is useful as a product reference for how the app should feel:

- Discovery first, resume tailoring second, autofill last.
- Source-level confidence, company context, and fit/risk explanation on every role.
- Separate fresh jobs and already-applied workflows.
- Clear blockers for sponsorship, citizenship, clearance, seniority, and hard experience requirements.

The app must not depend on Jobright private APIs or scrape Jobright public job pages as an active source. Use Jobright only as UX and workflow inspiration.

## Source Tiers

1. Verified ATS APIs
   - Greenhouse public board API
   - Lever public postings API
   - Ashby public posting API
   - Workday public CXS endpoint where company tenant/site is known

2. Curated public daily feeds
   - Simplify public new-grad list

3. Open public job feeds
   - RemoteOK
   - Himalayas
   - The Muse
   - Remotive
   - Arbeitnow

4. Search fallback
   - Search-engine discovery only for ATS-like URLs
   - Fetch page text and run the same gate before recommendation

## Required Normalized Fields

Every job row should carry:

- Stable job identity and source URL
- Company, title, location, work model
- Posted timestamp and freshness confidence
- Full JD text or clear placeholder plus `jd_text_source`
- Source trust tier
- Seniority and years required when available
- Sponsorship, citizen-only, and clearance signals when available
- Quality gate decision, blockers, reasons, and signals
- Discovery score for ranking only

Discovery score must never override a reject decision.

## Current First-Step Implementation

Implemented now:

- Month/day date parsing for public feed rows such as `Jun 05`.
- Structured ranking signals for seniority, H1B sponsor, clearance required, citizen-only, and minimum years.
- Final quality gate override for structured clearance, citizen-only, and hard experience blockers.
- Fresh 24h no longer allows high discovery scores to bypass quality gating.
- Jobright references removed from active discovery. The current source mix is ATS targets, Simplify public new-grad rows, open job feeds, and ATS-like web search fallback.

Next source upgrades:

- Add Ashby board ingestion.
- Add Workday CXS ingestion for known company tenant/site pairs.
- Expand `target_companies.json` into a larger source registry with ATS type, token, source confidence, and crawl cadence.
- Add source health diagnostics in the UI: fetched, parsed, enriched, rejected, recommended.
