from fastapi.testclient import TestClient

from app.dependencies import (
    get_autofill_context_service,
    get_job_feed_service,
    get_job_queue_service,
    get_llm_match_service,
    get_tracker_service,
)
from app.api import webapp as webapp_api
from app.main import app
from app.schemas.ats_autofill import AutofillContextResponse
from app.services.job_visibility_service import JobVisibilityService


class FakeFeed:
    def __init__(self) -> None:
        self.refreshed = False
        self.recent_refreshed = False

    def load_cached_jobs(self, limit: int = 100) -> list[dict]:
        return [
            {
                "job_id": "good",
                "company": "GoodCo",
                "title": "Junior Data Scientist",
                "jd_text": "Python SQL machine learning. 1 year experience.",
                "discovered_url": "https://example.com/good",
                "source": "pytest",
                "location": "Remote, United States",
            },
            {
                "job_id": "skip",
                "company": "SkipCo",
                "title": "Data Engineer I",
                "jd_text": "The company does not sponsor/support H-1B petitions, TN, or Forms I-983/STEM OPT.",
                "discovered_url": "https://example.com/skip",
                "source": "pytest",
                "location": "United States",
            },
        ][:limit]

    def load_cached_scraped_jobs(self, limit: int = 200) -> list[dict]:
        return []

    def load_cached_recent_jobs(self, limit: int = 100) -> list[dict]:
        return self.load_cached_jobs(limit=limit)

    def load_recent_payload(self) -> dict:
        return {"targets": [{"company": "Recent", "status": "ok", "scraped": 2, "kept": 1}]}

    def ensure_jd_text(self, job: dict) -> dict:
        return job

    def refresh_live_jobs(self, **_kwargs) -> dict:
        self.refreshed = True
        return {"targets": [{"company": "Main", "status": "ok", "scraped": 1, "kept": 1}], "jobs": []}

    def refresh_recent_jobs(self, **_kwargs) -> dict:
        self.recent_refreshed = True
        return {"targets": [{"company": "Recent", "status": "ok", "scraped": 1, "kept": 1}], "jobs": []}


class FakeMatch:
    def __init__(self) -> None:
        self.use_llm_calls: list[bool] = []

    def analyze(self, job: dict, *, use_llm: bool = False) -> dict:
        self.use_llm_calls.append(use_llm)
        if "does not sponsor" in job.get("jd_text", ""):
            return {
                "score": 59,
                "base_score": 59,
                "verdict": "skip",
                "label": "Skip",
                "one_line_reason": "Work authorization blocker.",
                "strengths": [],
                "gaps": [],
                "risks": ["Work authorization blocker."],
                "sponsorship_note": "Work authorization language looks risky; review before applying.",
                "scoring_mode": "deterministic_fallback",
                "target_role_key": "data_engineer",
                "years_required": None,
            }
        return {
            "score": 86,
            "base_score": 86,
            "verdict": "good_match",
            "label": "Good Match",
            "one_line_reason": "Good profile fit.",
            "strengths": ["Matched skill: Python"],
            "gaps": [],
            "risks": [],
            "sponsorship_note": "No obvious sponsorship blocker found.",
            "scoring_mode": "deterministic_fallback",
            "target_role_key": "data_scientist",
            "years_required": 1,
        }


class FakeRejectFeed(FakeFeed):
    def load_cached_jobs(self, limit: int = 100) -> list[dict]:
        return [
            {
                "job_id": "eu",
                "company": "Databricks",
                "title": "AI Engineer - FDE (Forward Deployed Engineer)",
                "jd_text": "Build GenAI applications with LLMs.",
                "discovered_url": "https://example.com/eu",
                "source": "Greenhouse Live Feed",
                "location": "Remote - Spain",
            },
            {
                "job_id": "good",
                "company": "GoodCo",
                "title": "Junior Data Scientist",
                "jd_text": "Python SQL machine learning. 1 year experience.",
                "discovered_url": "https://example.com/good",
                "source": "pytest",
                "location": "Remote, United States",
            },
        ][:limit]

    def ensure_jd_text(self, job: dict) -> dict:
        if job.get("job_id") == "eu":
            updated = dict(job)
            updated["quality_decision"] = "reject"
            updated["quality_actionable"] = False
            updated["quality_blockers"] = ["Location blocker: role is outside the configured United States search scope."]
            return updated
        return job


class FakeCachedHighMatch(FakeMatch):
    def cached_analysis(self, job: dict) -> dict:
        return {
            "score": 90,
            "base_score": 90,
            "verdict": "good_match",
            "label": "Good Match",
            "one_line_reason": "Old cached high score.",
            "strengths": ["llm"],
            "gaps": [],
            "risks": [],
            "sponsorship_note": "No obvious sponsorship blocker found.",
            "scoring_mode": "llm",
            "target_role_key": "ai_engineer",
            "years_required": None,
        }


class FakeQueue:
    def list_items(self, limit: int = 100) -> list:
        return []


class FakeTracker:
    def list_rows(self) -> list:
        return []


class FakeContext:
    def __init__(self) -> None:
        self.last_payload = None

    def load_or_prepare(self, payload):
        self.last_payload = payload
        return AutofillContextResponse(
            source="prepared_tailored_resume",
            confidence=0.9,
            apply_plan={"job": {"company": payload.company, "role": payload.role}},
            prepared_apply_plan_path="D:\\Educational Documents\\Resumes\\GoodCo\\application_packets\\apply_plan.json",
            prepared_packet_folder_path="D:\\Educational Documents\\Resumes\\GoodCo\\application_packets",
            prepared_resume_path="D:\\Educational Documents\\Resumes\\GoodCo\\resume.docx",
            prepared_resume_docx_path="D:\\Educational Documents\\Resumes\\GoodCo\\resume.docx",
            prepared_resume_html_path="D:\\Educational Documents\\Resumes\\GoodCo\\resume.html",
            message="prepared",
        )


def test_webapp_dashboard_returns_ranked_non_skip_jobs() -> None:
    fake_feed = FakeFeed()
    fake_match = FakeMatch()
    app.dependency_overrides[get_job_feed_service] = lambda: fake_feed
    app.dependency_overrides[get_llm_match_service] = lambda: fake_match
    app.dependency_overrides[get_job_queue_service] = lambda: FakeQueue()
    app.dependency_overrides[get_tracker_service] = lambda: FakeTracker()

    try:
        response = TestClient(app).get("/webapp/dashboard")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"]["raw_count"] == 2
    assert payload["stats"]["returned_count"] == 1
    assert payload["jobs"][0]["job"]["company"] == "GoodCo"
    assert payload["jobs"][0]["analysis"]["score"] == 86
    assert fake_match.use_llm_calls
    assert all(fake_match.use_llm_calls)


def test_webapp_dashboard_hard_filters_quality_rejects_before_cached_llm_scores() -> None:
    fake_feed = FakeRejectFeed()
    app.dependency_overrides[get_job_feed_service] = lambda: fake_feed
    app.dependency_overrides[get_llm_match_service] = lambda: FakeCachedHighMatch()
    app.dependency_overrides[get_job_queue_service] = lambda: FakeQueue()
    app.dependency_overrides[get_tracker_service] = lambda: FakeTracker()

    try:
        response = TestClient(app).get("/webapp/dashboard?min_score=0&use_llm=true")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    companies = [row["job"]["company"] for row in payload["jobs"]]
    assert "Databricks" not in companies
    assert "GoodCo" in companies
    assert payload["stats"]["skipped_count"] >= 1


def test_webapp_refresh_recent_endpoint() -> None:
    fake_feed = FakeFeed()
    app.dependency_overrides[get_job_feed_service] = lambda: fake_feed

    try:
        response = TestClient(app).post("/webapp/refresh-fresh24", json={"hours": 24, "max_results": 10})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_feed.recent_refreshed is True
    assert response.json()["targets"][0]["company"] == "Recent"


def test_webapp_prepare_packet_forces_configured_resume_folder() -> None:
    fake_feed = FakeFeed()
    fake_context = FakeContext()
    app.dependency_overrides[get_job_feed_service] = lambda: fake_feed
    app.dependency_overrides[get_autofill_context_service] = lambda: fake_context

    try:
        response = TestClient(app).post(
            "/webapp/prepare-packet",
            json={"job": fake_feed.load_cached_jobs()[0], "render_pdf": False},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_context.last_payload is not None
    assert fake_context.last_payload.output_root_override == ""
    assert fake_context.last_payload.force_prepare is True
    assert response.json()["prepared_resume_path"].startswith("D:\\Educational Documents\\Resumes")


def test_webapp_prepare_tailored_resume_endpoint_uses_same_context_flow() -> None:
    fake_feed = FakeFeed()
    fake_context = FakeContext()
    app.dependency_overrides[get_job_feed_service] = lambda: fake_feed
    app.dependency_overrides[get_autofill_context_service] = lambda: fake_context

    try:
        response = TestClient(app).post(
            "/webapp/prepare-tailored-resume",
            json={"job": fake_feed.load_cached_jobs()[0], "render_pdf": False},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_context.last_payload is not None
    assert fake_context.last_payload.force_prepare is True
    assert response.json()["prepared_resume_docx_path"].endswith("resume.docx")


def test_webapp_already_applied_endpoint_moves_job_to_applied_feed(tmp_path, monkeypatch) -> None:
    fake_feed = FakeFeed()
    visibility = JobVisibilityService(state_path=str(tmp_path / "job_visibility.json"))
    monkeypatch.setattr(webapp_api, "JobVisibilityService", lambda: visibility)
    app.dependency_overrides[get_job_feed_service] = lambda: fake_feed
    app.dependency_overrides[get_llm_match_service] = lambda: FakeMatch()
    app.dependency_overrides[get_job_queue_service] = lambda: FakeQueue()
    app.dependency_overrides[get_tracker_service] = lambda: FakeTracker()

    try:
        client = TestClient(app)
        dashboard = client.get("/webapp/dashboard?min_score=0").json()
        job = dashboard["jobs"][0]["job"]

        response = client.post("/webapp/already-applied", json={"job": job})
        after_move = client.get("/webapp/dashboard?min_score=0").json()
        applied = client.get("/webapp/dashboard?feed=applied&min_score=100&show_reviews=false").json()
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert all(row["job"]["company"] != "GoodCo" for row in after_move["jobs"])
    assert applied["feed"] == "applied"
    assert applied["stats"]["returned_count"] == 1
    assert applied["jobs"][0]["job"]["company"] == "GoodCo"
    assert applied["jobs"][0]["applied"] is True


def test_webapp_has_no_arm_autofill_endpoint() -> None:
    # Autofill is now handled entirely by the browser watcher; the arm-autofill path is gone.
    response = TestClient(app).post("/webapp/arm-autofill", json={"job": {}})
    assert response.status_code == 404
