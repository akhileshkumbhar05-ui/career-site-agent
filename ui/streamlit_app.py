import json
import sys
from pathlib import Path

import requests
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.schemas.job import JDParseRequest, OfficialJobResolutionRequest
from app.schemas.resume import (
    ResumeDecisionRequest,
    ResumeScoreRequest,
    ResumeTailorRequest,
)
from app.schemas.tracker import ApplicationRowCreateRequest
from app.services.canonicalization_service import CanonicalizationService
from app.services.decision_service import DecisionService
from app.services.jd_parser_service import JDParserService
from app.services.scoring_service import ScoringService
from app.services.tailoring_service import TailoringService
from ui.components.job_review_panel import render_job_review_panel
from ui.components.recruiter_panel import render_recruiter_panel
from ui.components.score_card import render_score_card

API_BASE_URL = "http://127.0.0.1:8000"
RESUME_VERSION = "base_resume_v1"

APPLIED_USING_OPTIONS = ["Company Website", "LinkedIn"]
APPLICATION_STATUS_OPTIONS = ["Applied", "Rejection", "Not Applied"]

st.set_page_config(page_title="CareerSite Agent", layout="wide")
st.title("CareerSite Agent Demo")
st.caption("Career-site-grounded resume fit scoring, tailoring, and decision support.")

parser = JDParserService()
scoring = ScoringService()
tailoring = TailoringService()
decision_service = DecisionService()
canonicalization_service = CanonicalizationService()

for key in [
    "job_payload",
    "resolution_result",
    "parsed",
    "score",
    "tailored",
    "decision",
    "last_selected_sample",
    "tracker_rows",
]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "tracker_rows" else []

st.sidebar.header("Input Mode")
input_mode = st.sidebar.radio(
    "Choose JD input type",
    ["Sample JD", "Paste JD Text"],
)

with st.sidebar:
    st.subheader("API Status")
    if st.button("Check API Health"):
        try:
            resp = requests.get(f"{API_BASE_URL}/health", timeout=5)
            resp.raise_for_status()
            payload = resp.json()
            st.success(payload.get("status", "ok"))
            st.caption(payload.get("service", "CareerSite Agent"))
        except Exception as e:
            st.error(f"API unavailable: {e}")


def analyze_job(job_payload: dict):
    resolution_payload = OfficialJobResolutionRequest(
        company=job_payload.get("company", "").strip(),
        title=job_payload.get("title", "").strip(),
        discovered_url=job_payload.get("discovered_url", "").strip(),
        source=job_payload.get("source", "manual").strip(),
    )
    resolution_result = canonicalization_service.resolve(resolution_payload)

    parsed = parser.parse(JDParseRequest(**job_payload))

    score = scoring.score(
        ResumeScoreRequest(
            job_id=job_payload["job_id"],
            resume_version=RESUME_VERSION,
            parsed_jd=parsed,
        )
    )

    tailored = None
    if 65 <= score.overall_score < 85:
        tailored = tailoring.tailor(
            ResumeTailorRequest(
                job_id=job_payload["job_id"],
                resume_version=RESUME_VERSION,
                parsed_jd=parsed,
                current_score=score.overall_score,
            )
        )

    decision = decision_service.decide(
        ResumeDecisionRequest(
            job_id=job_payload["job_id"],
            base_score=score.overall_score,
            tailored_score=tailored.tailored_score if tailored else None,
        )
    )

    st.session_state.job_payload = job_payload
    st.session_state.resolution_result = resolution_result
    st.session_state.parsed = parsed
    st.session_state.score = score
    st.session_state.tailored = tailored
    st.session_state.decision = decision


def fetch_tracker_rows() -> list[dict]:
    resp = requests.get(f"{API_BASE_URL}/tracker/rows", timeout=10)
    resp.raise_for_status()
    return resp.json()


if input_mode == "Sample JD":
    sample_jobs = sorted(Path("data/sample_jobs").glob("sample_jd_*.json"))
    selected_path = st.selectbox(
        "Choose a sample JD",
        sample_jobs,
        format_func=lambda p: p.name,
    )

    if selected_path:
        selected_key = str(selected_path)
        if st.session_state.last_selected_sample != selected_key:
            job_payload = json.loads(Path(selected_path).read_text(encoding="utf-8"))
            job_payload.setdefault("job_id", selected_path.stem)
            analyze_job(job_payload)
            st.session_state.last_selected_sample = selected_key

else:
    st.subheader("Paste Job Description")

    company = st.text_input("Company", value="Example Company")
    title = st.text_input("Role Title", value="AI Engineer")
    job_id = st.text_input("Job ID", value="manual_job_001")
    discovered_url = st.text_input("Discovered Job URL", value="")
    source = st.text_input("Found Via", value="manual")

    jd_text = st.text_area(
        "Paste the full job description here",
        height=300,
        placeholder="Paste the full JD text here...",
    )

    if st.button("Analyze Pasted JD"):
        if not jd_text.strip():
            st.warning("Please paste a job description first.")
            st.stop()

        job_payload = {
            "job_id": job_id.strip() or "manual_job_001",
            "company": company.strip() or "Example Company",
            "title": title.strip() or "Untitled Role",
            "jd_text": jd_text.strip(),
            "discovered_url": discovered_url.strip(),
            "source": source.strip() or "manual",
        }
        analyze_job(job_payload)

job_payload = st.session_state.job_payload
resolution_result = st.session_state.resolution_result
parsed = st.session_state.parsed
score = st.session_state.score
tailored = st.session_state.tailored
decision = st.session_state.decision

if job_payload and parsed and score and decision:
    top_left, top_right = st.columns([1.1, 1])

    with top_left:
        render_job_review_panel(job_payload, parsed)

        st.subheader("Posting Resolution")
        if resolution_result:
            st.write(f"**Canonical Job ID:** {resolution_result.canonical_job_id}")
            st.write(f"**Official URL:** {resolution_result.official_url or 'Not provided'}")
            st.write(f"**ATS Type:** {resolution_result.ats_type}")
            st.write(f"**Status:** {resolution_result.status}")
            st.write(f"**Confidence:** {resolution_result.confidence}")

    with top_right:
        render_score_card(score)

        st.subheader("Decision Recommendation")

        decision_label_map = {
            "apply_now": "Apply Now",
            "manual_review": "Manual Review",
            "reject": "Reject",
        }
        decision_value = decision_label_map.get(decision.decision, decision.decision)

        if decision.decision == "apply_now":
            st.success(f"Recommendation: {decision_value}")
        elif decision.decision == "manual_review":
            st.warning(f"Recommendation: {decision_value}")
        else:
            st.error(f"Recommendation: {decision_value}")

        st.write(decision.reason)

        if tailored:
            st.subheader("Tailoring Impact")

            metric_col1, metric_col2, metric_col3 = st.columns(3)
            with metric_col1:
                st.metric("Base Score", f"{score.overall_score}%")
            with metric_col2:
                st.metric(
                    "Tailored Score",
                    f"{tailored.tailored_score}%",
                    delta=tailored.tailored_score - score.overall_score,
                )
            with metric_col3:
                score_gap = max(0, 85 - score.overall_score)
                st.metric("Gap to Apply Threshold", f"{score_gap}")

            st.markdown("**Selected Projects**")
            if tailored.selected_project_ids:
                for project_id in tailored.selected_project_ids:
                    st.write(f"- {project_id}")
            else:
                st.write("No project selection available.")

            st.markdown("**Tailoring Changes Planned**")
            for change in tailored.changes_summary:
                st.write(f"- {change}")

        st.divider()
        st.subheader("Applications Tracker")

        default_link = resolution_result.official_url if resolution_result else job_payload.get("discovered_url", "")
        default_job_posted_on = job_payload.get("source", "Unknown")

        salary_input = st.text_input(
            "Salary Quoted while Applying",
            value="N/A",
            key="tracker_salary",
        )
        job_posted_on_input = st.text_input(
            "Job Posted On",
            value=default_job_posted_on,
            key="tracker_job_posted_on",
        )
        applied_using_input = st.selectbox(
            "Applied Using",
            APPLIED_USING_OPTIONS,
            index=0,
            key="tracker_applied_using",
        )
        status_input = st.selectbox(
            "Status",
            APPLICATION_STATUS_OPTIONS,
            index=0,
            key="tracker_status",
        )
        link_input = st.text_input(
            "Link",
            value=default_link,
            key="tracker_link",
        )
        tracker_notes = st.text_area(
            "Notes",
            value=decision.reason,
            height=100,
            key="tracker_notes",
        )

        if st.button("Save Application Row"):
            try:
                tracker_payload = ApplicationRowCreateRequest(
                    company_applied=job_payload["company"],
                    role=job_payload["title"],
                    salary_quoted_while_applying=salary_input.strip() or "N/A",
                    job_posted_on=job_posted_on_input.strip() or "Unknown",
                    applied_using=applied_using_input,
                    status=status_input,
                    link=link_input.strip(),
                    job_id=job_payload.get("job_id"),
                    base_match_percent=int(score.overall_score),
                    tailored_match_percent=int(tailored.tailored_score) if tailored else None,
                    resume_version_used=RESUME_VERSION,
                    notes=tracker_notes.strip() or None,
                )

                resp = requests.post(
                    f"{API_BASE_URL}/tracker/add-row",
                    json=tracker_payload.model_dump(),
                    timeout=10,
                )
                resp.raise_for_status()
                tracker_response = resp.json()

                st.success(tracker_response["message"])
                st.write(
                    f"Saved: **{tracker_response['company_applied']} - {tracker_response['role']}**"
                )
                st.write(f"Application Status: **{tracker_response['status']}**")

                st.session_state.tracker_rows = fetch_tracker_rows()
            except Exception as e:
                st.error(f"Failed to save application row: {e}")

    st.divider()

    bottom_left, bottom_right = st.columns(2)

    with bottom_left:
        st.subheader("Tailoring Preview")
        if tailored:
            st.json(tailored.model_dump(), expanded=False)
        else:
            st.info(
                "Tailoring was not triggered because the base score is already high enough or too low for automatic tailoring."
            )

    with bottom_right:
        render_recruiter_panel(job_payload["company"], job_payload["title"])

st.divider()
st.subheader("Saved Application Rows")

col_a, col_b = st.columns([1, 3])

with col_a:
    if st.button("Refresh Application Rows"):
        try:
            st.session_state.tracker_rows = fetch_tracker_rows()
        except Exception as e:
            st.error(f"Failed to load application rows: {e}")

with col_b:
    if st.session_state.tracker_rows:
        st.dataframe(st.session_state.tracker_rows, use_container_width=True)
    else:
        st.info("No application rows loaded yet.")