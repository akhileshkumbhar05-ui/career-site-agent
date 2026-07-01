from __future__ import annotations

import html
import hashlib
import inspect
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.dependencies import (  # noqa: E402
    get_autofill_autopilot_service,
    get_autofill_context_service,
    get_job_feed_service,
    get_job_queue_service,
    get_llm_match_service,
    get_tracker_service,
)
from app.schemas.ats_autofill import AutofillAutopilotArmRequest, AutofillContextRequest  # noqa: E402
from app.services.job_visibility_service import JobVisibilityService  # noqa: E402


FASTAPI_HEALTH_URL = "http://127.0.0.1:8000/health"
OUTPUT_ROOT = "data/outputs/autofill_packets"
APPLICATION_PROFILE_PATH = PROJECT_ROOT / "data" / "application_profile.json"
EXTENSION_PATH = PROJECT_ROOT / "browser_assist" / "ats_autofill_extension"
BASE_PACKET_ROOTS = [
    PROJECT_ROOT / "data" / "outputs" / "autofill_packets",
    PROJECT_ROOT / "data" / "outputs" / "agent_packets",
    PROJECT_ROOT / "data" / "outputs" / "queue_packets",
    PROJECT_ROOT / "data" / "outputs" / "queue_packets_test",
]


st.set_page_config(page_title="CareerSite Agent", page_icon=None, layout="wide")


def apply_styles() -> None:
    st.markdown(
        """
<style>
    :root {
        --bg: #141414;
        --bg-2: #0b0b0b;
        --panel: #181818;
        --panel-2: #1f1f1f;
        --panel-hover: #2a2a2a;
        --field: #333333;
        --ink: #ffffff;
        --muted: #b3b3b3;
        --muted-2: #808080;
        --line: rgba(255, 255, 255, 0.10);
        --line-strong: rgba(255, 255, 255, 0.24);
        --red: #e50914;
        --red-2: #b20710;
        --red-soft: rgba(229, 9, 20, 0.16);
        --mint: #46d369;
        --mint-soft: rgba(70, 211, 105, 0.15);
        --amber: #f5c518;
        --amber-soft: rgba(245, 197, 24, 0.15);
        --blue: #5aa9ff;
        --blue-soft: rgba(90, 169, 255, 0.14);
    }
    .stApp, div[data-testid="stAppViewContainer"] {
        background:
            radial-gradient(120% 60% at 0% 0%, rgba(229, 9, 20, 0.18), transparent 55%),
            linear-gradient(180deg, #1a1a1a 0%, var(--bg) 32%, var(--bg-2) 100%);
        background-attachment: fixed;
        color: var(--ink);
    }
    header[data-testid="stHeader"] {
        background: transparent;
    }
    .main .block-container {
        max-width: 1500px;
        padding: 1.15rem 1.6rem 3rem;
    }
    h1, h2, h3, h4 {
        letter-spacing: -0.01em;
        color: var(--ink);
    }
    p { letter-spacing: 0; }
    div[data-testid="stMetric"] {
        background: var(--panel-2);
        border: 1px solid var(--line);
        border-radius: 10px;
        padding: 0.72rem 0.85rem;
    }
    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: var(--ink);
    }
    .topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0.95rem;
        padding: 0.2rem 0 0.35rem;
    }
    .brand {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        color: var(--ink);
        font-weight: 900;
        font-size: 1.6rem;
        letter-spacing: 0.01em;
    }
    .brand-mark {
        position: relative;
        width: 34px;
        height: 34px;
        border-radius: 8px;
        background: linear-gradient(160deg, var(--red), var(--red-2));
        box-shadow: 0 6px 18px rgba(229, 9, 20, 0.45);
    }
    .brand-mark::after {
        content: "C";
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #fff;
        font-size: 1.25rem;
        font-weight: 900;
    }
    .brand-subtitle {
        color: var(--muted);
        font-size: 0.9rem;
        margin-top: 0.1rem;
    }
    .summary-band {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 10px;
        padding: 0.9rem;
        margin-bottom: 1rem;
    }
    .filter-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
        margin: 0.55rem 0 0.75rem;
    }
    .filter-chip {
        display: inline-flex;
        align-items: center;
        border: 1px solid var(--line-strong);
        background: rgba(255, 255, 255, 0.06);
        color: #e5e5e5;
        border-radius: 999px;
        padding: 0.4rem 0.7rem;
        font-size: 0.82rem;
        font-weight: 700;
    }
    /* Bordered job cards (st.container(border=True)) */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--panel);
        border: 1px solid var(--line) !important;
        border-radius: 12px;
        transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease, background 160ms ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        background: var(--panel-hover);
        border-color: var(--line-strong) !important;
        transform: translateY(-3px);
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.55);
    }
    .score-ring {
        width: 78px;
        height: 78px;
        border-radius: 50%;
        border: 4px solid var(--mint);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.5rem;
        font-weight: 800;
        color: #fff;
        background: radial-gradient(circle at center, rgba(0, 0, 0, 0.35), transparent 70%);
        box-shadow: 0 0 18px rgba(70, 211, 105, 0.25);
    }
    .score-label {
        font-size: 0.82rem;
        font-weight: 800;
        text-transform: uppercase;
        text-align: center;
        color: var(--muted);
    }
    .score-mode {
        color: var(--muted-2);
        font-size: 0.72rem;
        text-align: center;
    }
    .job-title {
        color: var(--ink);
        font-size: 1.18rem;
        font-weight: 800;
        line-height: 1.22;
        margin-bottom: 0.18rem;
    }
    .job-company {
        color: var(--muted);
        font-size: 0.9rem;
        margin-bottom: 0.75rem;
    }
    .muted {
        color: var(--muted);
    }
    .reason {
        color: var(--ink);
        font-size: 0.9rem;
        margin: 0.5rem 0;
    }
    .source-note {
        color: var(--muted);
        font-size: 0.85rem;
        margin: 0.25rem 0 0.75rem;
    }
    .section-title-row {
        display: flex;
        justify-content: space-between;
        align-items: end;
        gap: 1rem;
        margin-top: 1rem;
    }
    .tag {
        display: inline-block;
        border-radius: 999px;
        padding: 0.26rem 0.6rem;
        font-size: 0.72rem;
        font-weight: 800;
        text-transform: uppercase;
        margin: 0.1rem 0.16rem 0.1rem 0;
        border: 1px solid transparent;
    }
    .tag-good { color: var(--mint); background: var(--mint-soft); border-color: rgba(70, 211, 105, 0.4); }
    .tag-review { color: var(--amber); background: var(--amber-soft); border-color: rgba(245, 197, 24, 0.4); }
    .tag-skip { color: #ff9ba1; background: var(--red-soft); border-color: rgba(229, 9, 20, 0.5); }
    .tag-blue { color: var(--blue); background: var(--blue-soft); border-color: rgba(90, 169, 255, 0.35); }
    .detail-panel {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 1rem;
        margin-top: 0.65rem;
    }
    .path-box {
        background: #000;
        border: 1px solid var(--line);
        border-radius: 6px;
        padding: 0.55rem 0.7rem;
        color: #6dd58c;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 0.78rem;
        word-break: break-all;
    }
    .stButton > button, .stDownloadButton > button {
        border-radius: 6px;
        font-weight: 700;
        min-height: 2.45rem;
    }
    .stButton > button[kind="primary"] {
        background: var(--red);
        border-color: var(--red);
        color: #fff;
        box-shadow: 0 4px 16px rgba(229, 9, 20, 0.35);
    }
    .stButton > button[kind="primary"]:hover {
        background: #f6121d;
        border-color: #f6121d;
    }
    .stButton > button[kind="secondary"] {
        background: rgba(255, 255, 255, 0.08);
        border-color: var(--line-strong);
        color: #fff;
    }
    .stButton > button[kind="secondary"]:hover {
        background: rgba(255, 255, 255, 0.18);
        border-color: var(--line-strong);
        color: #fff;
    }
    .job-title-link {
        color: var(--ink) !important;
        font-size: 1.25rem;
        line-height: 1.24;
        font-weight: 800;
        text-decoration: none !important;
    }
    .job-title-link:hover {
        color: var(--red) !important;
        text-decoration: underline !important;
    }
    .external-link-button {
        display: inline-flex;
        min-height: 2.45rem;
        width: 100%;
        align-items: center;
        justify-content: center;
        border-radius: 6px;
        border: 1px solid var(--line-strong);
        background: rgba(255, 255, 255, 0.10);
        color: #fff !important;
        font-weight: 700;
        text-decoration: none !important;
        padding: 0 0.8rem;
        white-space: nowrap;
    }
    .external-link-button:hover {
        border-color: var(--red);
        color: #fff !important;
        background: rgba(229, 9, 20, 0.18);
    }
    .detail-empty {
        background: var(--panel);
        border: 1px dashed var(--line-strong);
        border-radius: 12px;
        padding: 1rem;
        color: var(--muted);
    }
    div[data-testid="stExpander"] details {
        border: 1px solid var(--line);
        border-radius: 10px;
        background: var(--panel);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 1.1rem;
        border-bottom: 1px solid var(--line);
    }
    .stTabs [data-baseweb="tab-highlight"] {
        background: var(--red);
    }
    .stTabs [aria-selected="true"] {
        color: #fff;
    }
    @media (max-width: 900px) {
        .section-title-row { flex-direction: column; align-items: start; }
    }
</style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def services() -> dict[str, Any]:
    return {
        "queue": get_job_queue_service(),
        "feed": get_job_feed_service(),
        "match": get_llm_match_service(),
        "context": get_autofill_context_service(),
        "autopilot": get_autofill_autopilot_service(),
        "tracker": get_tracker_service(),
        "visibility": JobVisibilityService(),
    }


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def md_escape(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def clear_interaction_state() -> None:
    for key in (
        "selected_job",
        "selected_analysis",
        "prepared_context",
        "prepared_context_job_key",
        "autopilot_result",
    ):
        st.session_state.pop(key, None)
    st.session_state["home_mode"] = True


def external_link_html(label: object, url: str, *, class_name: str = "") -> str:
    classes = f' class="{class_name}"' if class_name else ""
    return f'<a{classes} href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)}</a>'


def render_external_button(column: Any, label: str, url: str) -> None:
    column.markdown(external_link_html(label, url, class_name="external-link-button"), unsafe_allow_html=True)


def existing_local_path(value: str) -> Path | None:
    if not value:
        return None
    try:
        path = Path(value)
    except (OSError, ValueError):
        return None
    return path if path.exists() else None


def render_file_artifact(label: str, path_value: str, *, mime: str) -> None:
    if not path_value:
        return
    st.markdown(f"**{esc(label)}**")
    st.markdown(f'<div class="path-box">{esc(path_value)}</div>', unsafe_allow_html=True)
    local_path = existing_local_path(path_value)
    if local_path:
        digest = hashlib.sha1(str(local_path).encode("utf-8")).hexdigest()[:12]
        st.download_button(
            f"Download {label}",
            data=local_path.read_bytes(),
            file_name=local_path.name,
            mime=mime,
            key=f"download_{label.lower().replace(' ', '_')}_{digest}",
        )
    else:
        st.caption("This file was not found on disk. Use the HTML resume path if PDF rendering failed.")


def health_check(url: str) -> bool:
    try:
        request = Request(url, headers={"User-Agent": "CareerSite-UI"})
        with urlopen(request, timeout=1.2) as response:
            return response.status == 200
    except Exception:
        return False


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def configured_resume_root() -> Path | None:
    profile = read_json(APPLICATION_PROFILE_PATH)
    resume_storage = profile.get("resume_storage") if isinstance(profile.get("resume_storage"), dict) else {}
    root = str(resume_storage.get("root_directory") or "").strip()
    return Path(root) if root else None


def packet_roots() -> list[Path]:
    roots = [*BASE_PACKET_ROOTS]
    resume_root = configured_resume_root()
    if resume_root:
        roots.append(resume_root)

    unique_roots: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        unique_roots.append(root)
    return unique_roots


def queue_jobs() -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    try:
        for item in services()["queue"].list_items(limit=200):
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
                    "tailored_resume_pdf_path": export.get("tailored_resume_pdf_path") or "",
                }
            )
    except Exception as exc:
        st.warning(f"Queue unavailable: {exc}")
    return jobs


def cached_feed_jobs() -> list[dict[str, Any]]:
    return services()["feed"].load_cached_jobs(limit=200)


def cached_scraped_jobs() -> list[dict[str, Any]]:
    return services()["feed"].load_cached_scraped_jobs(limit=300)


def cached_recent_jobs() -> list[dict[str, Any]]:
    loader = getattr(services()["feed"], "load_cached_recent_jobs", None)
    if not callable(loader):
        return []
    return loader(limit=200)


def cached_applied_jobs() -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for record in services()["visibility"].applied_jobs():
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


def cached_recent_payload() -> dict[str, Any]:
    feed = services()["feed"]
    loader = getattr(feed, "load_recent_payload", None)
    if callable(loader):
        return loader()

    cache_path = Path(getattr(feed, "recent_cache_path", PROJECT_ROOT / "data" / "cache" / "job_feed" / "recent_24h_jobs.json"))
    return read_json(cache_path)


def all_feed_jobs() -> list[dict[str, Any]]:
    jobs = [*cached_feed_jobs(), *cached_scraped_jobs(), *queue_jobs()]
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for job in jobs:
        if is_demo_or_smoke_job(job):
            continue
        key = (resolve_job_url(job) or job.get("job_id") or "").strip().lower()
        if not key:
            key = f"{job.get('company','')}|{job.get('title','')}|{job.get('location','')}".lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
    return deduped


def is_demo_or_smoke_job(job: dict[str, Any]) -> bool:
    text = " ".join(
        str(job.get(key, ""))
        for key in ("company", "title", "source", "queue_id", "job_id")
    ).lower()
    markers = (
        "smoke",
        "test do not use",
        "wf2 queue",
        "wf3 test",
        "wf6 worker",
        "packet artifact",
    )
    return any(marker in text for marker in markers)


def resolve_job_url(job: dict[str, Any]) -> str:
    return services()["visibility"].resolve_url(job)


def job_key(job: dict[str, Any]) -> str:
    return services()["visibility"].job_key(job)


def has_hard_blocker(job: dict[str, Any]) -> bool:
    blockers = [str(item).lower() for item in (job.get("quality_blockers") or [])]
    hard_markers = (
        "seniority blocker",
        "experience requirement appears above",
        "work authorization blocker",
        "security clearance",
        "clearance",
        "citizen",
        "sponsorship",
        "location blocker",
    )
    return any(any(marker in blocker for marker in hard_markers) for blocker in blockers)


def tracker_rows() -> list[Any]:
    try:
        return services()["tracker"].list_rows()
    except Exception as exc:
        st.caption(f"Applied tracker unavailable for duplicate filtering: {exc}")
        return []


def is_hidden_or_applied(job: dict[str, Any], rows: list[Any]) -> tuple[bool, str]:
    visibility = services()["visibility"]
    if visibility.is_hidden(job):
        return True, visibility.hidden_reason(job) or "hidden"
    if job.get("queue_status") in {"submitted", "manually_skipped", "rejected"}:
        return True, str(job.get("queue_status"))
    if visibility.is_applied_in_tracker(job, rows):
        return True, "already in tracker"
    return False, ""


def select_job(job: dict[str, Any], analysis: dict[str, Any]) -> None:
    st.session_state["selected_job"] = job
    st.session_state["selected_analysis"] = analysis
    st.session_state["home_mode"] = False
    selected_key = job_key(job)
    if st.session_state.get("prepared_context_job_key") != selected_key:
        st.session_state.pop("prepared_context", None)
        st.session_state.pop("autopilot_result", None)


def cached_semantic_analysis(job: dict[str, Any]) -> dict[str, Any] | None:
    if job.get("ai_score") is None:
        return None
    if job.get("quality_decision") == "reject" and str(job.get("ai_verdict") or "") != "skip":
        return None

    score = int(job.get("ai_score") or 0)
    verdict = str(job.get("ai_verdict") or "review")
    return {
        "job_id": job.get("job_id") or job_key(job),
        "company": job.get("company") or "",
        "title": job.get("title") or job.get("role") or "",
        "location": job.get("location") or "",
        "source": job.get("source") or "",
        "url": resolve_job_url(job),
        "score": score,
        "base_score": int(job.get("ai_base_score") or job.get("base_score") or score),
        "verdict": verdict,
        "worth_applying": bool(job.get("ai_worth_applying")),
        "label": job.get("ai_label") or ("Good Match" if verdict == "good_match" else "Strong Match" if verdict == "strong_match" else "Needs Review"),
        "one_line_reason": job.get("ai_reason") or "; ".join((job.get("quality_reasons") or [])[:2]),
        "strengths": job.get("ai_strengths") or job.get("quality_signals") or [],
        "gaps": job.get("ai_gaps") or [],
        "risks": job.get("ai_risks") or job.get("quality_blockers") or job.get("quality_reasons") or [],
        "suggested_actions": job.get("ai_suggested_actions")
        or [
            "Open the original job posting.",
            "Tailor the resume if the job still looks worth applying.",
            "Run automated autofill and review before submitting.",
        ],
        "sponsorship_note": job.get("ai_sponsorship_note") or "Review authorization wording before submitting.",
        "scoring_mode": job.get("ai_scoring_mode") or "llm_cached",
        "quality_gate_decision": job.get("quality_decision") or "",
        "target_role_key": job.get("quality_role_key") or "",
        "years_required": job.get("years_required"),
        "components": job.get("ai_components") or {},
        "parsed": job.get("ai_parsed") or {},
        "created_at": job.get("ai_reviewed_at") or "",
    }


def analyze_job(job: dict[str, Any], *, use_llm: bool) -> dict[str, Any]:
    job = services()["feed"].ensure_jd_text(job)
    cached = cached_semantic_analysis(job)
    if cached:
        return cached
    return services()["match"].analyze(job, use_llm=use_llm)


def analyze_jobs(jobs: list[dict[str, Any]], *, use_llm: bool, limit: int) -> list[dict[str, Any]]:
    rows = []
    for job in jobs[:limit]:
        prepared = services()["feed"].ensure_jd_text(job)
        analysis = analyze_job(prepared, use_llm=use_llm)
        rows.append({"job": prepared, "analysis": analysis})
    rows.sort(key=lambda row: row["analysis"]["score"], reverse=True)
    return rows


def semantic_review_jobs(jobs: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    reviewed: list[dict[str, Any]] = []
    progress = st.progress(0, text="AI reviewing scraped jobs...")
    total = max(1, min(limit, len(jobs)))
    for index, job in enumerate(jobs):
        if index < limit:
            prepared = services()["feed"].ensure_jd_text(job)
            analysis = services()["match"].analyze(prepared, use_llm=True)
            reviewed.append(with_semantic_fields(prepared, analysis))
            progress.progress(min(index + 1, total) / total, text=f"AI reviewed {min(index + 1, total)} of {total} jobs")
        else:
            reviewed.append(job)
    progress.empty()
    return reviewed


def with_semantic_fields(job: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    updated = dict(job)
    updated.update(
        {
            "ai_score": int(analysis.get("score") or 0),
            "ai_base_score": int(analysis.get("base_score") or analysis.get("score") or 0),
            "ai_verdict": analysis.get("verdict") or "review",
            "ai_worth_applying": bool(analysis.get("worth_applying")),
            "ai_label": analysis.get("label") or "",
            "ai_reason": analysis.get("one_line_reason") or "",
            "ai_strengths": analysis.get("strengths") or [],
            "ai_gaps": analysis.get("gaps") or [],
            "ai_risks": analysis.get("risks") or [],
            "ai_suggested_actions": analysis.get("suggested_actions") or [],
            "ai_sponsorship_note": analysis.get("sponsorship_note") or "",
            "ai_scoring_mode": analysis.get("scoring_mode") or "llm",
            "ai_provider": analysis.get("llm_provider") or "",
            "ai_model": analysis.get("llm_model") or "",
            "ai_components": analysis.get("components") or {},
            "ai_parsed": analysis.get("parsed") or {},
            "ai_reviewed_at": datetime.now(UTC).isoformat(),
        }
    )
    return updated


def recommendation_jobs_from_reviewed(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recommended: list[dict[str, Any]] = []
    for job in jobs:
        hard_blocked = has_hard_blocker(job)
        ai_reviewed = job.get("ai_score") is not None
        ai_verdict = str(job.get("ai_verdict") or "")
        if ai_reviewed:
            score = int(job.get("ai_score") or 0)
            if not hard_blocked and ai_verdict != "skip" and score >= 55:
                recommended.append(job)
            continue
        if (job.get("quality_actionable") or int(job.get("discovery_score") or 0) >= 65) and not hard_blocked:
            recommended.append(job)
    return recommended


def persist_feed_payload(payload: dict[str, Any]) -> dict[str, Any]:
    feed = services()["feed"]
    persist = getattr(feed, "persist_payload", None)
    if callable(persist):
        return persist(payload)

    cache_path = Path(getattr(feed, "cache_path", PROJECT_ROOT / "data" / "cache" / "job_feed" / "latest_jobs.json"))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def persist_recent_payload(payload: dict[str, Any]) -> dict[str, Any]:
    feed = services()["feed"]
    persist = getattr(feed, "persist_recent_payload", None)
    if callable(persist):
        return persist(payload)

    cache_path = Path(getattr(feed, "recent_cache_path", PROJECT_ROOT / "data" / "cache" / "job_feed" / "recent_24h_jobs.json"))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def refresh_feed_payload(
    *,
    max_companies: int,
    max_jobs: int,
    include_rejected: bool,
    include_web: bool,
    web_max_results: int,
) -> dict[str, Any]:
    feed = services()["feed"]
    kwargs: dict[str, Any] = {
        "max_companies": int(max_companies),
        "max_jobs_per_company": int(max_jobs),
        "include_rejected": include_rejected,
    }

    try:
        params = inspect.signature(feed.refresh_live_jobs).parameters
    except (TypeError, ValueError):
        params = {}

    if "include_web" in params:
        kwargs["include_web"] = include_web
        kwargs["web_max_results"] = web_max_results
    elif include_web:
        st.warning(
            "This Streamlit process still has an older job-feed service in memory. "
            "Restart/open the fresh app URL to enable web sources."
        )

    return feed.refresh_live_jobs(**kwargs)


def refresh_recent_payload(
    *,
    hours: int,
    max_results: int,
    include_rejected: bool,
    max_target_companies: int,
) -> dict[str, Any]:
    feed = services()["feed"]
    refresh = getattr(feed, "refresh_recent_jobs", None)
    if not callable(refresh):
        st.warning(
            "This Streamlit process still has an older job-feed service in memory. "
            "Restart/open the fresh app URL to enable the Fresh 24h tab."
        )
        return {"targets": [], "jobs": [], "all_jobs": []}
    return refresh(
        hours=hours,
        max_results=max_results,
        include_rejected=include_rejected,
        max_target_companies=max_target_companies,
        include_targets=True,
    )


def prepare_packet(job: dict[str, Any], *, render_pdf: bool = True) -> Any:
    prepared = services()["feed"].ensure_jd_text(job)
    url = resolve_job_url(prepared) or resolve_job_url(job)
    return services()["context"].load_or_prepare(
        AutofillContextRequest(
            url=url,
            page_title=f"{prepared.get('title', '')} | {prepared.get('company', '')}",
            page_text=prepared.get("jd_text", ""),
            company=prepared.get("company", ""),
            role=prepared.get("title", ""),
            source=prepared.get("source", "website_feed"),
            output_root_override="",
            force_prepare=True,
            render_pdf=render_pdf,
        )
    )


def arm_automated_autofill(context: dict[str, Any] | None, job: dict[str, Any]) -> dict[str, Any]:
    context = context or {}
    apply_plan_path = context.get("prepared_apply_plan_path") or context.get("matched_apply_plan_path") or ""
    apply_plan = context.get("apply_plan") or services()["autopilot"].autofill.build_profile_apply_plan(
        resolve_job_url(job),
        job,
    )
    response = services()["autopilot"].arm(
        AutofillAutopilotArmRequest(
            url=resolve_job_url(job),
            apply_plan=apply_plan,
            apply_plan_path=apply_plan_path,
            overwrite=False,
            open_browser=True,
            expires_minutes=45,
        )
    )
    return response.model_dump()


def packet_paths() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in packet_roots():
        if not root.exists():
            continue
        for path in root.rglob("apply_plan.json"):
            data = read_json(path)
            job = data.get("job", {})
            decision = data.get("decision", {})
            rows.append(
                {
                    "path": path,
                    "data": data,
                    "mtime": path.stat().st_mtime,
                    "company": job.get("company", "Unknown"),
                    "role": job.get("role", "Unknown"),
                    "score": decision.get("tailored_score") or decision.get("base_score"),
                }
            )
    return sorted(rows, key=lambda row: row["mtime"], reverse=True)


def tag_class(verdict: str) -> str:
    if verdict in {"strong_match", "good_match"}:
        return "tag-good"
    if verdict == "skip":
        return "tag-skip"
    return "tag-review"


def score_ring_color(score: int, verdict: str) -> str:
    if verdict == "skip" or score < 65:
        return "#ff7a80"
    if score < 80:
        return "#f5c518"
    return "#46d369"


def run_main_job_refresh() -> dict[str, Any]:
    payload = refresh_feed_payload(
        max_companies=10,
        max_jobs=10,
        include_rejected=False,
        include_web=True,
        web_max_results=45,
    )
    st.session_state["last_refresh_summary"] = payload.get("targets", [])
    st.session_state["last_refresh_jobs"] = payload.get("all_jobs") or payload.get("jobs", [])
    scraped_count = sum(int(row.get("scraped") or 0) for row in payload.get("targets", []))
    kept_count = sum(int(row.get("kept") or 0) for row in payload.get("targets", []))
    st.session_state["refresh_status_message"] = (
        f"Refresh complete: {scraped_count} scraped, {kept_count} kept, "
        f"{payload.get('preserved_job_count', 0)} existing jobs preserved."
    )
    st.cache_data.clear()
    return payload


def render_topbar() -> None:
    title_col, action_col = st.columns([5, 1.55], vertical_alignment="center")
    with title_col:
        st.markdown(
            """
<div class="topbar">
  <div>
    <div class="brand"><div class="brand-mark"></div><span>CareerSite Jobs</span></div>
    <div class="brand-subtitle">AI-ranked entry-level Data, ML, AI, and Python roles with resume tailoring and autofill handoff.</div>
  </div>
  <div class="muted">ATS feeds | New-grad lists | Web search agent</div>
</div>
            """,
            unsafe_allow_html=True,
        )
    with action_col:
        home_col, refresh_col = st.columns([0.85, 1.15])
        if home_col.button("Home", key="home_top", width="stretch"):
            clear_interaction_state()
            st.rerun()
        if refresh_col.button("Refresh Jobs", key="refresh_jobs_top", type="primary", width="stretch"):
            with st.spinner("Refreshing job sources..."):
                run_main_job_refresh()
            st.rerun()


def render_filters(*, key_prefix: str = "main", freshness_chip: str | None = None) -> dict[str, Any]:
    chips = [
        "AI job-search agent",
        "United States",
        "Data / ML / AI",
        "Entry / New Grad",
        "0-1.4 Years",
        "Relocation OK",
        "No Clearance Roles",
    ]
    if freshness_chip:
        chips.insert(1, freshness_chip)
    chip_html = "".join(f'<span class="filter-chip">{esc(chip)}</span>' for chip in chips)
    st.markdown(
        f"""
<div class="filter-row">
  {chip_html}
</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="source-note">Autofill opens the ATS page and fills safe text/select/radio fields automatically. You still review uploads and final submit.</div>',
        unsafe_allow_html=True,
    )
    col1, col2, col3, col4, col5 = st.columns([2.2, 1.0, 1.1, 1.15, 1.1])
    search = col1.text_input(
        "Search by title or company",
        label_visibility="collapsed",
        placeholder="Search by title or company",
        key=f"{key_prefix}_search",
    )
    min_score = col2.slider("Minimum score", min_value=0, max_value=100, value=60, step=5, key=f"{key_prefix}_min_score")
    show_reviews = col3.checkbox("Include review jobs", value=True, key=f"{key_prefix}_show_reviews")
    show_hidden = col4.checkbox("Show hidden/applied", value=False, key=f"{key_prefix}_show_hidden")
    use_llm = col5.toggle("LLM deep score", value=True, key=f"{key_prefix}_use_llm")
    return {
        "search": search.strip().lower(),
        "min_score": min_score,
        "show_reviews": show_reviews,
        "show_hidden": show_hidden,
        "use_llm": use_llm,
    }


def render_scraped_jobs_table(jobs: list[dict[str, Any]]) -> None:
    if not jobs:
        st.caption("No scraped job rows are available yet. Run Scrape Real Jobs to load them.")
        return

    ordered_jobs = sorted(
        jobs,
        key=lambda job: (
            job.get("ai_score") is not None,
            int(job.get("ai_score") or 0),
            bool(job.get("quality_actionable")),
        ),
        reverse=True,
    )
    rows = []
    for job in ordered_jobs[:150]:
        ai_score = job.get("ai_score")
        ai_verdict = job.get("ai_verdict") or ""
        ai_actionable = bool(job.get("ai_worth_applying")) or ai_verdict in {"strong_match", "good_match"}
        rows.append(
            {
                "Company": job.get("company") or "",
                "Role": job.get("title") or job.get("role") or "",
                "AI Score": f"{int(ai_score)}%" if ai_score is not None else "",
                "AI Verdict": ai_verdict,
                "Decision": job.get("quality_decision") or "unknown",
                "Actionable": "Yes" if ai_actionable or job.get("quality_actionable") else "No",
                "Years": str(job.get("years_required")) if job.get("years_required") is not None else "",
                "Location": job.get("location") or "",
                "Reason": job.get("ai_reason") or "; ".join((job.get("quality_blockers") or job.get("quality_reasons") or [])[:2]),
                "Open": resolve_job_url(job),
            }
        )

    st.markdown("**Scraped job rows**")
    st.caption("These are the raw jobs from the scrape run. AI-reviewed rows can override soft title rejects, but hard blockers stay blocked.")
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "Open": st.column_config.LinkColumn("Open", display_text="Open"),
            "Reason": st.column_config.TextColumn("Reason", width="large"),
        },
    )
    st.markdown("**Quick open links**")
    for job in ordered_jobs[:40]:
        url = resolve_job_url(job)
        label = f"{job.get('company') or 'Unknown'} - {job.get('title') or job.get('role') or 'Untitled role'}"
        decision = (
            f"{int(job['ai_score'])}% {job.get('ai_verdict') or 'review'}"
            if job.get("ai_score") is not None
            else job.get("quality_decision") or "unknown"
        )
        if url:
            st.markdown(f"- {external_link_html(label, url)} | `{decision}`", unsafe_allow_html=True)
        else:
            st.markdown(f"- {md_escape(label)} | `{decision}` | no URL found")


def render_refresh_controls(*, expanded: bool = False) -> None:
    with st.expander("Refresh discovery sources", expanded=expanded):
        st.caption("Pulls configured ATS boards plus public new-grad feeds and broad web search. The local AI scorer ranks jobs into the main feed; it does not submit applications or touch n8n credentials.")
        col1, col2, col3, col4, col5, col6, col7 = st.columns([0.85, 0.85, 0.9, 1.05, 0.95, 0.95, 1.25])
        max_companies = col1.number_input("ATS companies", min_value=1, max_value=16, value=8, step=1)
        max_jobs = col2.number_input("Jobs/company", min_value=1, max_value=25, value=8, step=1)
        include_rejected = col3.checkbox("Include skips", value=False)
        semantic_review = col4.checkbox("LLM semantic review", value=True)
        include_web = col5.checkbox("Web sources", value=True)
        review_limit = col6.number_input("AI review limit", min_value=1, max_value=80, value=40, step=5)
        if col7.button("Scrape Real Jobs", type="primary"):
            with st.spinner("Scraping configured ATS targets without sending anything to n8n..."):
                payload = refresh_feed_payload(
                    max_companies=int(max_companies),
                    max_jobs=int(max_jobs),
                    include_rejected=include_rejected or semantic_review,
                    include_web=include_web,
                    web_max_results=max(8, min(40, int(max_companies) * int(max_jobs))),
                )
                if semantic_review:
                    scraped_jobs = payload.get("all_jobs") or payload.get("jobs", [])
                    with st.spinner("Running local LLM semantic fit review over scraped jobs..."):
                        reviewed_jobs = semantic_review_jobs(scraped_jobs, limit=int(review_limit))
                    payload["all_jobs"] = reviewed_jobs
                    payload["jobs"] = recommendation_jobs_from_reviewed(reviewed_jobs)
                    persist_feed_payload(payload)
                st.session_state["last_refresh_summary"] = payload.get("targets", [])
                st.session_state["last_refresh_jobs"] = payload.get("all_jobs") or payload.get("jobs", [])
                st.cache_data.clear()
                st.rerun()

    if st.session_state.get("last_refresh_summary"):
        with st.expander("Source diagnostics", expanded=False):
            st.dataframe(st.session_state["last_refresh_summary"], width="stretch", hide_index=True)
            refresh_jobs = st.session_state.get("last_refresh_jobs") or cached_scraped_jobs()
            render_scraped_jobs_table(refresh_jobs)


def render_recent_refresh_controls(*, expanded: bool = False) -> None:
    with st.expander("Refresh last-24-hour jobs", expanded=expanded):
        st.caption("Searches public feeds plus configured ATS boards, keeps only relevant profile jobs posted in the last 24 hours, and stores them in a separate cache.")
        col1, col2, col3, col4, col5 = st.columns([0.85, 0.85, 1.0, 1.05, 1.25])
        max_results = col1.number_input("Fresh results", min_value=5, max_value=80, value=30, step=5, key="fresh_max_results")
        max_targets = col2.number_input("ATS companies", min_value=0, max_value=16, value=8, step=1, key="fresh_ats_companies")
        include_rejected = col3.checkbox("Include skips", value=False, key="fresh_include_skips")
        semantic_review = col4.checkbox("LLM semantic review", value=False, key="fresh_semantic_review")
        review_limit = col5.number_input("AI review limit", min_value=1, max_value=80, value=30, step=5, key="fresh_review_limit")
        if st.button("Scrape Fresh 24h Jobs", type="primary", key="fresh_scrape_jobs"):
            with st.spinner("Searching recent public feeds for relevant profile jobs..."):
                payload = refresh_recent_payload(
                    hours=24,
                    max_results=int(max_results),
                    include_rejected=include_rejected or semantic_review,
                    max_target_companies=int(max_targets),
                )
                if semantic_review:
                    scraped_jobs = payload.get("all_jobs") or payload.get("jobs", [])
                    with st.spinner("Running local LLM semantic fit review over fresh jobs..."):
                        reviewed_jobs = semantic_review_jobs(scraped_jobs, limit=int(review_limit))
                    payload["all_jobs"] = reviewed_jobs
                    payload["jobs"] = recommendation_jobs_from_reviewed(reviewed_jobs)
                    persist_recent_payload(payload)
                st.session_state["last_recent_summary"] = payload.get("targets", [])
                st.session_state["last_recent_jobs"] = payload.get("all_jobs") or payload.get("jobs", [])
                if payload.get("jobs"):
                    st.session_state["last_recent_message"] = f"Found {len(payload.get('jobs') or [])} fresh recommended jobs."
                else:
                    scraped_count = sum(int(row.get("scraped") or 0) for row in payload.get("targets", []))
                    st.session_state["last_recent_message"] = (
                        f"Refresh completed: {scraped_count} relevant jobs with posted-time signals were found in the last 24 hours."
                    )
                st.cache_data.clear()
                st.rerun()

    recent_payload = cached_recent_payload()
    recent_summary = st.session_state.get("last_recent_summary") or recent_payload.get("targets") or []
    recent_jobs = st.session_state.get("last_recent_jobs") or recent_payload.get("all_jobs") or recent_payload.get("jobs") or []
    recent_message = st.session_state.get("last_recent_message")
    if not recent_message and recent_payload.get("created_at"):
        scraped_count = sum(int(row.get("scraped") or 0) for row in recent_summary)
        created = str(recent_payload.get("created_at") or "").split(".")[0].replace("T", " ")
        recent_message = f"Last refresh {created}: {scraped_count} relevant jobs with posted-time signals were found in the last 24 hours."
    if recent_message:
        if recent_jobs:
            st.success(recent_message)
        else:
            st.warning(recent_message)

    if recent_summary:
        with st.expander("Fresh source diagnostics", expanded=False):
            st.dataframe(recent_summary, width="stretch", hide_index=True)
            render_scraped_jobs_table(recent_jobs)


def render_job_card(row: dict[str, Any], index: int, *, key_prefix: str = "main") -> None:
    job = row["job"]
    analysis = row["analysis"]
    url = resolve_job_url(job)
    hidden_reason = row.get("hidden_reason") or job.get("hidden_reason") or ""
    already_applied = hidden_reason == "already_applied"
    score = int(analysis["score"])
    verdict = analysis["verdict"]
    color = score_ring_color(score, verdict)
    posted_value = (
        job.get("freshness_label")
        or job.get("posted_at")
        or job.get("publication_date")
        or job.get("created_at")
        or "Not listed"
    )
    details = [
        ("Location", job.get("location") or "Not listed"),
        ("Posted", posted_value),
        ("Source", job.get("source") or "Unknown"),
        ("Experience", f"{analysis.get('years_required')} years" if analysis.get("years_required") else "Not explicit"),
        ("Work Auth", analysis.get("sponsorship_note") or "Review"),
    ]
    tags = [
        analysis.get("label", "Match"),
        analysis.get("target_role_key", "") or "role inferred",
        analysis.get("scoring_mode", "score").replace("_", " "),
        job.get("source_scope", "").replace("_", " "),
    ]
    title = esc(job.get("title", "Untitled Role"))
    hidden_tag = f'<span class="tag tag-review">{esc(hidden_reason)}</span>' if hidden_reason else ""

    with st.container(border=True):
        main, match = st.columns([5.4, 1.25], vertical_alignment="top")
        with main:
            if url:
                st.markdown(external_link_html(title, url, class_name="job-title-link"), unsafe_allow_html=True)
            else:
                st.markdown(f"### {title}")
            st.caption(f"{job.get('company', 'Unknown Company')} | {job.get('source', 'Unknown')}")
            dcols = st.columns(len(details))
            for col, (key, value) in zip(dcols, details, strict=False):
                col.markdown(f"**{key}**  \n{value}")
            st.write(analysis.get("one_line_reason", ""))
            tag_html = "".join(
                f'<span class="tag {tag_class(verdict) if i == 0 else "tag-blue"}">{esc(tag)}</span>'
                for i, tag in enumerate(tags)
                if tag
            )
            st.markdown(f"{tag_html}{hidden_tag}", unsafe_allow_html=True)
        with match:
            st.markdown(
                f'<div class="score-ring" style="border-color:{color};margin-left:auto;margin-right:auto;">{score}%</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="score-label" style="text-align:center;">{esc(analysis.get("label", "Match"))}</div>',
                unsafe_allow_html=True,
            )
            st.caption(analysis.get("scoring_mode", "score").replace("_", " "))

        c1, c2, c3, c4, c5 = st.columns([1.0, 1.1, 0.95, 1.0, 1.45])
        if c1.button("Details", key=f"{key_prefix}_details_{index}"):
            select_job(job, analysis)
        if c2.button("Tailor Resume", key=f"{key_prefix}_tailor_{index}", type="primary", disabled=verdict == "skip"):
            with st.spinner("Preparing tailored packet..."):
                context = prepare_packet(job, render_pdf=True)
                st.session_state["prepared_context"] = context.model_dump()
                st.session_state["prepared_context_job_key"] = job_key(job)
                select_job(job, analysis)
                if context.prepared_resume_path:
                    st.success(f"Tailored resume saved: {context.prepared_resume_path}")
                    st.toast("Tailored resume saved.")
                else:
                    st.error(context.message or "Tailor Resume did not create a resume file.")
        if c3.button("Autofill", key=f"{key_prefix}_autofill_{index}", disabled=verdict == "skip" or not url):
            with st.spinner("Opening ATS page and filling saved profile answers..."):
                st.session_state["autopilot_result"] = arm_automated_autofill(
                    st.session_state.get("prepared_context"),
                    job,
                )
                select_job(job, analysis)
                st.toast("Profile autofill armed.")
        if url:
            render_external_button(c4, "Open Job", url)
        if c5.button(
            "Applied" if already_applied else "Already Applied",
            key=f"{key_prefix}_applied_{index}",
            disabled=already_applied,
            width="stretch",
        ):
            services()["visibility"].mark_applied(job)
            if st.session_state.get("selected_job") and job_key(st.session_state["selected_job"]) == job_key(job):
                st.session_state.pop("selected_job", None)
                st.session_state.pop("selected_analysis", None)
                st.session_state.pop("prepared_context", None)
                st.session_state.pop("autopilot_result", None)
                st.session_state.pop("prepared_context_job_key", None)
            st.toast("Moved to Already Applied.")
            st.rerun()


def render_detail_panel(*, key_prefix: str = "main") -> None:
    job = st.session_state.get("selected_job")
    analysis = st.session_state.get("selected_analysis")
    if not job or not analysis:
        return

    st.markdown('<div class="detail-panel">', unsafe_allow_html=True)
    top_left, top_right = st.columns([4, 1])
    top_left.subheader(f"{job.get('title', 'Role')} at {job.get('company', 'Company')}")
    if top_right.button("Back", key=f"{key_prefix}_detail_back", width="stretch"):
        clear_interaction_state()
        st.rerun()
    cols = st.columns([1, 1, 1, 1])
    cols[0].metric("Match", f"{analysis.get('score', 0)}%")
    cols[1].metric("Verdict", analysis.get("label", "Review"))
    cols[2].metric("Base", f"{analysis.get('base_score', 0)}%")
    cols[3].metric("Mode", analysis.get("scoring_mode", "score").replace("_", " "))

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Strengths**")
        for item in analysis.get("strengths", []):
            st.write(f"- {item}")
    with c2:
        st.markdown("**Gaps**")
        gaps = analysis.get("gaps", [])
        if gaps:
            for item in gaps:
                st.write(f"- {item}")
        else:
            st.caption("No major gaps listed.")
    with c3:
        st.markdown("**Risks**")
        risks = analysis.get("risks", [])
        if risks:
            for item in risks:
                st.write(f"- {item}")
        else:
            st.caption("No major risks listed.")

    st.markdown("**Actions**")
    url = resolve_job_url(job)
    if url:
        st.markdown(external_link_html("Open original job posting", url, class_name="external-link-button"), unsafe_allow_html=True)
    for item in analysis.get("suggested_actions", []):
        st.write(f"- {item}")
    st.markdown("</div>", unsafe_allow_html=True)


def render_prepared_packet() -> None:
    context = st.session_state.get("prepared_context")
    autopilot = st.session_state.get("autopilot_result")
    if not context and not autopilot:
        return
    selected = st.session_state.get("selected_job")
    if context and selected and st.session_state.get("prepared_context_job_key") != job_key(selected):
        return

    st.markdown('<div class="detail-panel">', unsafe_allow_html=True)
    if context:
        st.subheader("Prepared Packet")
        st.write(context.get("message", "Packet ready."))
        if context.get("pdf_error"):
            st.warning(f"PDF was not created. HTML resume is ready. Details: {context.get('pdf_error')}")
    else:
        st.subheader("Autofill")
        st.write("Using saved application profile answers. Tailored packet generation is optional.")
    if context:
        pdf_path = context.get("prepared_resume_pdf_path") or ""
        docx_path = context.get("prepared_resume_docx_path") or ""
        html_path = context.get("prepared_resume_html_path") or ""
        resume_path = context.get("prepared_resume_path") or ""
        render_file_artifact(
            "Tailored resume DOCX",
            docx_path or (resume_path if resume_path.lower().endswith(".docx") else ""),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        render_file_artifact(
            "Tailored resume PDF",
            pdf_path,
            mime="application/pdf",
        )
        if html_path:
            render_file_artifact("Tailored resume HTML", html_path, mime="text/html")
        elif resume_path and resume_path != pdf_path:
            render_file_artifact("Tailored resume", resume_path, mime="text/html")
        if context.get("intended_resume_pdf_path") and not pdf_path:
            st.markdown("**PDF target path**")
            st.markdown(f'<div class="path-box">{esc(context["intended_resume_pdf_path"])}</div>', unsafe_allow_html=True)
    path = (context or {}).get("prepared_apply_plan_path") or (context or {}).get("matched_apply_plan_path")
    if path:
        st.markdown("**Apply plan**")
        st.markdown(f'<div class="path-box">{esc(path)}</div>', unsafe_allow_html=True)
    target_url = (((context or {}).get("apply_plan") or {}).get("job") or {}).get("official_url") or ""
    if target_url:
        st.markdown("**Target job URL**")
        st.markdown(external_link_html(target_url, target_url), unsafe_allow_html=True)
    if autopilot:
        st.markdown("**Automated autofill**")
        if autopilot.get("armed"):
            st.success(autopilot.get("message", "Automated autofill armed."))
        else:
            st.warning(autopilot.get("message", "Automated autofill could not be armed."))
        if autopilot.get("target_url"):
            st.markdown(external_link_html("Open target ATS page", autopilot["target_url"], class_name="external-link-button"), unsafe_allow_html=True)
        st.caption("Safe text, select, and radio fields fill automatically on the matching ATS page. Resume upload and final submit remain review points.")
    st.markdown("**Autofill extension folder**")
    st.markdown(f'<div class="path-box">{esc(EXTENSION_PATH)}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_feed() -> None:
    jobs = all_feed_jobs()
    render_topbar()
    if st.session_state.get("refresh_status_message"):
        st.success(st.session_state["refresh_status_message"])
    filters = render_filters(key_prefix="main")

    if not jobs:
        st.info("No real jobs are cached yet. Click Refresh Jobs to pull current sources.")
        return

    applied_rows = tracker_rows()
    visible_jobs: list[dict[str, Any]] = []
    hidden_count = 0
    for job in jobs:
        hidden, reason = is_hidden_or_applied(job, applied_rows)
        if hidden:
            hidden_count += 1
            if not filters["show_hidden"]:
                continue
            job = {**job, "hidden_reason": reason}
        visible_jobs.append(job)
    if hidden_count and not filters["show_hidden"]:
        st.caption(f"Hidden {hidden_count} already-applied or dismissed jobs. Turn on Show hidden/applied to inspect them.")

    analyzed = analyze_jobs(visible_jobs, use_llm=filters["use_llm"], limit=75)
    filtered = []
    for row in analyzed:
        job = row["job"]
        analysis = row["analysis"]
        if job.get("hidden_reason"):
            row["hidden_reason"] = job["hidden_reason"]
        haystack = f"{job.get('company','')} {job.get('title','')}".lower()
        if filters["search"] and filters["search"] not in haystack:
            continue
        if analysis["score"] < filters["min_score"]:
            continue
        if analysis["verdict"] == "skip":
            continue
        if not filters["show_reviews"] and analysis["verdict"] == "review":
            continue
        filtered.append(row)

    st.markdown(
        f"""
<div class="section-title-row">
  <div><h3>Recommended Jobs ({len(filtered)})</h3></div>
  <div class="muted">{len(visible_jobs)} visible leads after duplicate filtering</div>
</div>
        """,
        unsafe_allow_html=True,
    )
    if not filtered:
        st.info("No jobs match the current filters. Lower the minimum score, keep Include review jobs on, or show hidden/applied jobs to inspect what was filtered out.")
        return

    current = st.session_state.get("selected_job")
    filtered_keys = {job_key(row["job"]) for row in filtered}
    if not st.session_state.get("home_mode") and not current:
        select_job(filtered[0]["job"], filtered[0]["analysis"])
        current = st.session_state.get("selected_job")

    list_col, detail_col = st.columns([1.55, 0.95], gap="large")
    with list_col:
        for index, row in enumerate(filtered[:40]):
            render_job_card(row, index, key_prefix="main")

    with detail_col:
        if st.session_state.get("home_mode"):
            st.markdown(
                """
<div class="detail-empty">
  <strong>Home</strong><br>
  Choose Details on a job to pin its fit analysis here. Job links open in a new tab so this feed stays put.
</div>
                """,
                unsafe_allow_html=True,
            )
        elif not current or job_key(current) not in filtered_keys:
            st.markdown(
                """
<div class="detail-empty">
  <strong>Choose a job</strong><br>
  Pick Details on a recommendation to pin its fit analysis here.
</div>
                """,
                unsafe_allow_html=True,
            )
        else:
            render_detail_panel(key_prefix="main")
            render_prepared_packet()


def render_fresh_24h() -> None:
    jobs = []
    seen: set[str] = set()
    for job in cached_recent_jobs():
        if is_demo_or_smoke_job(job):
            continue
        key = (resolve_job_url(job) or job.get("job_id") or "").strip().lower()
        if not key:
            key = f"{job.get('company','')}|{job.get('title','')}|{job.get('location','')}".lower()
        if key in seen:
            continue
        seen.add(key)
        jobs.append(job)

    st.markdown(
        """
<div class="section-title-row">
  <div><h3>Fresh 24h Jobs</h3></div>
  <div class="muted">Relevant profile jobs with verified posted-time signals</div>
</div>
        """,
        unsafe_allow_html=True,
    )
    render_recent_refresh_controls(expanded=not bool(jobs))
    filters = render_filters(key_prefix="fresh", freshness_chip="Posted <24h")

    if not jobs:
        payload = cached_recent_payload()
        if payload.get("created_at"):
            st.info("No last-24-hour recommended jobs are cached from the latest refresh. Check Fresh source diagnostics above for source-by-source counts.")
        else:
            st.info("No last-24-hour jobs are cached yet. Open Refresh last-24-hour jobs and run a scrape.")
        return

    applied_rows = tracker_rows()
    visible_jobs: list[dict[str, Any]] = []
    hidden_count = 0
    for job in jobs:
        hidden, reason = is_hidden_or_applied(job, applied_rows)
        if hidden:
            hidden_count += 1
            if not filters["show_hidden"]:
                continue
            job = {**job, "hidden_reason": reason}
        visible_jobs.append(job)
    if hidden_count and not filters["show_hidden"]:
        st.caption(f"Hidden {hidden_count} already-applied or dismissed fresh jobs. Turn on Show hidden/applied to inspect them.")

    analyzed = analyze_jobs(visible_jobs, use_llm=filters["use_llm"], limit=75)
    filtered = []
    for row in analyzed:
        job = row["job"]
        analysis = row["analysis"]
        if job.get("hidden_reason"):
            row["hidden_reason"] = job["hidden_reason"]
        haystack = f"{job.get('company','')} {job.get('title','')}".lower()
        if filters["search"] and filters["search"] not in haystack:
            continue
        if analysis["score"] < filters["min_score"]:
            continue
        if analysis["verdict"] == "skip":
            continue
        if not filters["show_reviews"] and analysis["verdict"] == "review":
            continue
        filtered.append(row)

    st.markdown(
        f"""
<div class="section-title-row">
  <div><h3>Last-24-Hour Matches ({len(filtered)})</h3></div>
  <div class="muted">{len(visible_jobs)} fresh leads after duplicate filtering</div>
</div>
        """,
        unsafe_allow_html=True,
    )
    if not filtered:
        st.info("No fresh jobs match the current filters. Lower the minimum score or keep Include review jobs on.")
        return

    current = st.session_state.get("selected_job")
    filtered_keys = {job_key(row["job"]) for row in filtered}
    list_col, detail_col = st.columns([1.55, 0.95], gap="large")
    with list_col:
        for index, row in enumerate(filtered[:40]):
            render_job_card(row, index, key_prefix="fresh")

    with detail_col:
        if st.session_state.get("home_mode") or not current or job_key(current) not in filtered_keys:
            st.markdown(
                """
<div class="detail-empty">
  <strong>Fresh 24h</strong><br>
  Choose Details on a fresh job to pin its fit analysis here.
</div>
                """,
                unsafe_allow_html=True,
            )
        else:
            render_detail_panel(key_prefix="fresh")
            render_prepared_packet()


def render_already_applied() -> None:
    jobs = cached_applied_jobs()
    st.markdown(
        f"""
<div class="section-title-row">
  <div><h3>Already Applied ({len(jobs)})</h3></div>
  <div class="muted">Jobs you moved out of recommendations</div>
</div>
        """,
        unsafe_allow_html=True,
    )
    search = st.text_input(
        "Search applied jobs",
        label_visibility="collapsed",
        placeholder="Search applied jobs by title or company",
        key="applied_search",
    ).strip().lower()

    if not jobs:
        st.info("No already-applied jobs yet. Use Already Applied on a job card to move it here.")
        return

    filtered_jobs = [
        job
        for job in jobs
        if not search or search in f"{job.get('company','')} {job.get('title','')}".lower()
    ]
    if not filtered_jobs:
        st.info("No already-applied jobs match the current search.")
        return

    analyzed = analyze_jobs(filtered_jobs, use_llm=False, limit=100)
    for row in analyzed:
        row["hidden_reason"] = "already_applied"

    current = st.session_state.get("selected_job")
    filtered_keys = {job_key(row["job"]) for row in analyzed}
    list_col, detail_col = st.columns([1.55, 0.95], gap="large")
    with list_col:
        for index, row in enumerate(analyzed[:60]):
            render_job_card(row, index, key_prefix="applied")

    with detail_col:
        if st.session_state.get("home_mode") or not current or job_key(current) not in filtered_keys:
            st.markdown(
                """
<div class="detail-empty">
  <strong>Already Applied</strong><br>
  Choose Details on an applied job to pin its fit analysis here.
</div>
                """,
                unsafe_allow_html=True,
            )
        else:
            render_detail_panel(key_prefix="applied")
            render_prepared_packet()


def render_packets() -> None:
    packets = packet_paths()
    st.subheader("Tailored Packets")
    if not packets:
        st.info("No packets found yet.")
        return
    rows = [
        {
            "Company": item["company"],
            "Role": item["role"],
            "Score": item["score"],
            "Updated": datetime.fromtimestamp(item["mtime"]).strftime("%m/%d %H:%M"),
            "Path": str(item["path"]),
        }
        for item in packets[:80]
    ]
    st.dataframe(rows, width="stretch", hide_index=True)


def render_autofill() -> None:
    st.subheader("Autofill")
    api_ok = health_check(FASTAPI_HEALTH_URL)
    col1, col2 = st.columns(2)
    col1.metric("FastAPI", "Online" if api_ok else "Offline")
    col2.metric("Extension", "Installed" if EXTENSION_PATH.exists() else "Missing")
    st.markdown("**Extension folder**")
    st.markdown(f'<div class="path-box">{esc(EXTENSION_PATH)}</div>', unsafe_allow_html=True)
    st.markdown("**Packet output folder**")
    st.markdown(f'<div class="path-box">{esc((PROJECT_ROOT / OUTPUT_ROOT).resolve())}</div>', unsafe_allow_html=True)
    resume_root = configured_resume_root()
    if resume_root:
        st.markdown("**Tailored resume target folder**")
        st.markdown(f'<div class="path-box">{esc(resume_root)}</div>', unsafe_allow_html=True)
    st.caption("Click Autofill on a recommended job. CareerSite arms an autofill task, opens the ATS page, and the extension fills safe fields automatically. Final submit remains manual.")
    render_prepared_packet()


def main() -> None:
    apply_styles()
    feed, fresh, applied, packets, autofill = st.tabs(["Recommended", "Fresh 24h", "Already Applied", "Tailored Packets", "Autofill"])
    with feed:
        render_feed()
    with fresh:
        render_fresh_24h()
    with applied:
        render_already_applied()
    with packets:
        render_packets()
    with autofill:
        render_autofill()


if __name__ == "__main__":
    main()
