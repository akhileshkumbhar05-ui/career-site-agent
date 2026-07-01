from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.dependencies import (
    get_autofill_context_service,
    get_job_feed_service,
    get_job_queue_service,
    get_llm_match_service,
    get_tracker_service,
)
from app.schemas.ats_autofill import AutofillContextRequest
from app.services.autofill_context_service import AutofillContextService
from app.services.job_feed_service import JobFeedService
from app.services.job_queue_service import JobQueueService
from app.services.job_visibility_service import JobVisibilityService
from app.services.llm_match_service import LLMMatchService
from app.services.tracker_service import TrackerService

router = APIRouter()

OUTPUT_ROOT = "data/outputs/autofill_packets"
APPLICATION_PROFILE_PATH = Path("data/application_profile.json")
BASE_PACKET_ROOTS = [
    Path("data/outputs/autofill_packets"),
    Path("data/outputs/agent_packets"),
    Path("data/outputs/queue_packets"),
    Path("data/outputs/queue_packets_test"),
]


class DashboardJobRow(BaseModel):
    key: str
    job: dict[str, Any]
    analysis: dict[str, Any]
    url: str = ""
    hidden: bool = False
    hidden_reason: str = ""
    applied: bool = False


class DashboardResponse(BaseModel):
    feed: Literal["recommended", "fresh24", "applied"]
    generated_at: str
    jobs: list[DashboardJobRow]
    stats: dict[str, Any]
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    packets: list[dict[str, Any]] = Field(default_factory=list)


class RefreshMainRequest(BaseModel):
    max_companies: int = Field(default=8, ge=1, le=40)
    max_jobs_per_company: int = Field(default=8, ge=1, le=25)
    include_rejected: bool = False
    include_web: bool = True
    web_max_results: int = Field(default=35, ge=1, le=100)
    include_sponsors: bool = True
    sponsor_max_companies: int = Field(default=12, ge=0, le=100)
    sponsor_max_results: int = Field(default=15, ge=0, le=100)


class RefreshRecentRequest(BaseModel):
    hours: int = Field(default=24, ge=1, le=168)
    max_results: int = Field(default=30, ge=5, le=80)
    max_target_companies: int = Field(default=8, ge=0, le=40)
    include_rejected: bool = False


class JobActionRequest(BaseModel):
    job: dict[str, Any]
    reason: str = "already_applied"


class PreparePacketRequest(BaseModel):
    job: dict[str, Any]
    render_pdf: bool = True


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    feed: Literal["recommended", "fresh24", "applied"] = "recommended",
    search: str = "",
    min_score: int = 60,
    show_reviews: bool = True,
    show_hidden: bool = False,
    use_llm: bool = True,
    limit: int = 30,
    feed_service: JobFeedService = Depends(get_job_feed_service),
    match_service: LLMMatchService = Depends(get_llm_match_service),
    queue_service: JobQueueService = Depends(get_job_queue_service),
    tracker_service: TrackerService = Depends(get_tracker_service),
) -> DashboardResponse:
    visibility = JobVisibilityService()
    tracker_rows = _tracker_rows(tracker_service)
    if feed == "fresh24":
        raw_jobs = _fresh_jobs(feed_service)
        diagnostics = _fresh_diagnostics(feed_service)
    elif feed == "applied":
        raw_jobs = _applied_jobs(visibility)
        diagnostics = []
    else:
        raw_jobs = _all_jobs(feed_service, queue_service)
        diagnostics = _main_diagnostics(feed_service)
    rows, hidden_count, skipped_count = _analyzed_rows(
        raw_jobs,
        feed_service=feed_service,
        match_service=match_service,
        visibility=visibility,
        tracker_rows=tracker_rows,
        search=search,
        min_score=0 if feed == "applied" else min_score,
        show_reviews=True if feed == "applied" else show_reviews,
        show_hidden=True if feed == "applied" else show_hidden,
        use_llm=use_llm,
        limit=limit,
        include_skips=feed == "applied",
    )
    return DashboardResponse(
        feed=feed,
        generated_at=datetime.now(UTC).isoformat(),
        jobs=rows,
        diagnostics=diagnostics,
        packets=_packet_rows(),
        stats={
            "raw_count": len(raw_jobs),
            "visible_count": max(0, len(raw_jobs) - hidden_count),
            "returned_count": len(rows),
            "hidden_count": hidden_count,
            "skipped_count": skipped_count,
            "packet_count": len(_packet_rows()),
        },
    )


@router.post("/refresh-main")
def refresh_main(
    payload: RefreshMainRequest,
    feed_service: JobFeedService = Depends(get_job_feed_service),
) -> dict[str, Any]:
    return feed_service.refresh_live_jobs(
        max_companies=payload.max_companies,
        max_jobs_per_company=payload.max_jobs_per_company,
        include_rejected=payload.include_rejected,
        include_web=payload.include_web,
        web_max_results=payload.web_max_results,
        include_sponsors=payload.include_sponsors,
        sponsor_max_companies=payload.sponsor_max_companies,
        sponsor_max_results=payload.sponsor_max_results,
    )


@router.post("/refresh-fresh24")
def refresh_fresh24(
    payload: RefreshRecentRequest,
    feed_service: JobFeedService = Depends(get_job_feed_service),
) -> dict[str, Any]:
    return feed_service.refresh_recent_jobs(
        hours=payload.hours,
        max_results=payload.max_results,
        max_target_companies=payload.max_target_companies,
        include_rejected=payload.include_rejected,
        include_targets=True,
    )


@router.post("/hide")
def hide_job(payload: JobActionRequest) -> dict[str, Any]:
    return JobVisibilityService().mark_hidden(payload.job, reason=payload.reason)


@router.post("/already-applied")
def already_applied(payload: JobActionRequest) -> dict[str, Any]:
    return JobVisibilityService().mark_applied(payload.job)


@router.post("/prepare-tailored-resume")
def prepare_tailored_resume(
    payload: PreparePacketRequest,
    feed_service: JobFeedService = Depends(get_job_feed_service),
    context_service: AutofillContextService = Depends(get_autofill_context_service),
) -> dict[str, Any]:
    job = feed_service.ensure_jd_text(payload.job)
    context = context_service.load_or_prepare(
        AutofillContextRequest(
            url=JobVisibilityService().resolve_url(job),
            page_title=f"{job.get('title', '')} | {job.get('company', '')}",
            page_text=str(job.get("jd_text") or ""),
            company=str(job.get("company") or ""),
            role=str(job.get("title") or ""),
            source=str(job.get("source") or "website_feed"),
            output_root_override="",
            force_prepare=True,
            render_pdf=payload.render_pdf,
        )
    )
    return context.model_dump()


@router.post("/prepare-packet")
def prepare_packet(
    payload: PreparePacketRequest,
    feed_service: JobFeedService = Depends(get_job_feed_service),
    context_service: AutofillContextService = Depends(get_autofill_context_service),
) -> dict[str, Any]:
    return prepare_tailored_resume(payload, feed_service=feed_service, context_service=context_service)


@router.get("/packets")
def packets() -> list[dict[str, Any]]:
    return _packet_rows()


def _all_jobs(feed: JobFeedService, queue: JobQueueService) -> list[dict[str, Any]]:
    return _dedupe_jobs([*feed.load_cached_jobs(limit=250), *feed.load_cached_scraped_jobs(limit=500), *_queue_jobs(queue)])


def _fresh_jobs(feed: JobFeedService) -> list[dict[str, Any]]:
    return _dedupe_jobs(feed.load_cached_recent_jobs(limit=250))


def _applied_jobs(visibility: JobVisibilityService) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for record in visibility.applied_jobs():
        job = record.get("job") if isinstance(record.get("job"), dict) else {}
        job = dict(job)
        job.setdefault("company", record.get("company") or "")
        job.setdefault("title", record.get("title") or "")
        job.setdefault("discovered_url", record.get("url") or "")
        job.setdefault("source", "Already Applied")
        job["hidden_reason"] = str(record.get("reason") or "already_applied")
        job["applied_at"] = str(record.get("hidden_at") or "")
        jobs.append(job)
    return jobs


def _queue_jobs(queue: JobQueueService) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    try:
        items = queue.list_items(limit=200)
    except Exception:
        return []
    for item in items:
        job = item.job
        if job.company.upper().startswith("TEST DO NOT USE"):
            continue
        result = item.result or {}
        pipeline = result.get("pipeline_result") or {}
        export = result.get("export_result") or {}
        jobs.append(
            {
                "job_id": job.job_id or item.queue_id,
                "company": job.company,
                "title": job.title,
                "jd_text": job.jd_text,
                "discovered_url": job.discovered_url or pipeline.get("official_url") or "",
                "official_url": pipeline.get("official_url") or job.discovered_url or "",
                "source": job.source,
                "location": job.location or "",
                "posted_at": job.posted_at,
                "queue_id": item.queue_id,
                "queue_status": item.status,
                "updated_at": item.updated_at,
                "packet_folder_path": export.get("packet_folder_path") or "",
                "apply_plan_path": export.get("apply_plan_path") or "",
                "tailored_resume_docx_path": export.get("tailored_resume_docx_path") or "",
                "tailored_resume_pdf_path": export.get("tailored_resume_pdf_path") or "",
            }
        )
    return jobs


def _analyzed_rows(
    jobs: list[dict[str, Any]],
    *,
    feed_service: JobFeedService,
    match_service: LLMMatchService,
    visibility: JobVisibilityService,
    tracker_rows: list[Any],
    search: str,
    min_score: int,
    show_reviews: bool,
    show_hidden: bool,
    use_llm: bool,
    limit: int,
    include_skips: bool = False,
) -> tuple[list[DashboardJobRow], int, int]:
    rows: list[DashboardJobRow] = []
    hidden_count = 0
    skipped_count = 0
    needle = search.strip().lower()
    live_llm_budget = 8 if use_llm and not include_skips else 4
    live_llm_used = 0

    scan_limit = min(len(jobs), max(limit * 20, 120))
    for job in jobs[:scan_limit]:
        if _is_demo_or_smoke_job(job):
            continue
        hidden = visibility.is_hidden(job)
        hidden_reason = visibility.hidden_reason(job) if hidden else ""
        applied = hidden_reason == "already_applied" or visibility.is_applied_in_tracker(job, tracker_rows)
        if not hidden_reason and applied:
            hidden_reason = "already_applied"
        if (hidden or applied) and not show_hidden:
            hidden_count += 1
            continue

        if needle and needle not in f"{job.get('company', '')} {job.get('title', '')}".lower():
            continue

        prepared = feed_service.ensure_jd_text(job)
        if _quality_rejected(prepared):
            skipped_count += 1
            if not include_skips:
                continue
            analysis = match_service.analyze(prepared, use_llm=False)
        elif use_llm:
            cached = match_service.cached_analysis(prepared) if hasattr(match_service, "cached_analysis") else None
            if cached:
                analysis = cached
            elif live_llm_used < live_llm_budget:
                analysis = match_service.analyze(prepared, use_llm=True)
                live_llm_used += 1
            else:
                analysis = dict(match_service.analyze(prepared, use_llm=False))
                analysis["llm_pending"] = True
                analysis["scoring_mode"] = "fast_precheck_pending_llm"
                reason = str(analysis.get("one_line_reason") or "").strip()
                analysis["one_line_reason"] = (
                    f"{reason} LLM review deferred to keep the dashboard responsive."
                    if reason
                    else "LLM review deferred to keep the dashboard responsive."
                )
        else:
            analysis = match_service.analyze(prepared, use_llm=False)
        if not include_skips and int(analysis.get("score") or 0) < min_score:
            continue
        if not include_skips and analysis.get("verdict") == "skip":
            skipped_count += 1
            continue
        if not show_reviews and analysis.get("verdict") == "review":
            continue

        rows.append(
            DashboardJobRow(
                key=visibility.job_key(prepared),
                job=prepared,
                analysis=analysis,
                url=visibility.resolve_url(prepared),
                hidden=hidden,
                applied=applied,
                hidden_reason=hidden_reason,
            )
        )
        if len(rows) >= limit:
            break

    rows.sort(key=lambda row: int(row.analysis.get("score") or 0), reverse=True)
    return rows, hidden_count, skipped_count


def _quality_rejected(job: dict[str, Any]) -> bool:
    if str(job.get("quality_decision") or "").lower() == "reject":
        return True
    if job.get("quality_actionable") is False:
        return True
    blockers = job.get("quality_blockers")
    return isinstance(blockers, list) and bool(blockers)


def _tracker_rows(tracker: TrackerService) -> list[Any]:
    try:
        return tracker.list_rows()
    except Exception:
        return []


def _main_diagnostics(feed: JobFeedService) -> list[dict[str, Any]]:
    payload = _load_payload(getattr(feed, "cache_path", Path("data/cache/job_feed/latest_jobs.json")))
    return payload.get("targets", []) if isinstance(payload.get("targets"), list) else []


def _fresh_diagnostics(feed: JobFeedService) -> list[dict[str, Any]]:
    payload = feed.load_recent_payload() if hasattr(feed, "load_recent_payload") else {}
    return payload.get("targets", []) if isinstance(payload.get("targets"), list) else []


def _packet_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in _packet_roots():
        if not root.exists():
            continue
        for path in root.rglob("apply_plan.json"):
            data = _load_payload(path)
            job = data.get("job", {})
            decision = data.get("decision", {})
            rows.append(
                {
                    "path": str(path),
                    "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                    "company": job.get("company", "Unknown"),
                    "role": job.get("role", "Unknown"),
                    "score": decision.get("tailored_score") or decision.get("base_score"),
                    "official_url": job.get("official_url", ""),
                }
            )
    return sorted(rows, key=lambda row: str(row["updated_at"]), reverse=True)[:80]


def _packet_roots() -> list[Path]:
    roots = [*BASE_PACKET_ROOTS]
    profile = _load_payload(APPLICATION_PROFILE_PATH)
    resume_storage = profile.get("resume_storage") if isinstance(profile.get("resume_storage"), dict) else {}
    resume_root = str(resume_storage.get("root_directory") or "").strip()
    if resume_root:
        roots.append(Path(resume_root))

    unique_roots: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        unique_roots.append(root)
    return unique_roots


def _dedupe_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visibility = JobVisibilityService()
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for job in jobs:
        if _is_demo_or_smoke_job(job):
            continue
        key = visibility.job_key(job)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
    return deduped


def _is_demo_or_smoke_job(job: dict[str, Any]) -> bool:
    text = " ".join(str(job.get(key, "")) for key in ("company", "title", "source", "queue_id", "job_id")).lower()
    return any(marker in text for marker in ("smoke", "test do not use", "wf2 queue", "wf3 test", "wf6 worker", "packet artifact"))


def _load_payload(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
