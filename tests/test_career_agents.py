from fastapi.testclient import TestClient

from app.agents.fit_scoring_agent import FitScoringAgent
from app.agents.job_discovery_agent import JobDiscoveryAgent
from app.main import app
from app.schemas.agent import FitScoringAgentRequest, JobDiscoveryAgentRequest
from app.schemas.pipeline import JobProcessRequest
from app.schemas.queue import QueueEnqueueResponse


class FakeJobFeed:
    def __init__(self) -> None:
        self.refresh_kwargs = {}
        self.jobs = [
            {
                "job_id": "agent_good_fit",
                "company": "Good Fit AI",
                "title": "Junior Data Scientist",
                "jd_text": "Python SQL machine learning dashboards. 1 year experience.",
                "discovered_url": "https://example.com/good-fit",
                "source": "pytest",
                "location": "Remote, United States",
            },
            {
                "job_id": "agent_weak_fit",
                "company": "Weak Fit Systems",
                "title": "Senior Security Engineer",
                "jd_text": "Requires active clearance and 8 years of experience.",
                "discovered_url": "https://example.com/weak-fit",
                "source": "pytest",
                "location": "United States",
            },
        ]

    def refresh_live_jobs(self, **_: object) -> dict:
        self.refresh_kwargs = dict(_)
        return {"targets": [{"company": "Good Fit AI", "status": "ok"}], "jobs": self.jobs}

    def load_cached_jobs(self, **_: object) -> list[dict]:
        return self.jobs

    def ensure_jd_text(self, job: dict) -> dict:
        enriched = dict(job)
        enriched.setdefault("jd_text", "Python SQL machine learning.")
        return enriched


class FakeMatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def analyze(self, job: dict, *, use_llm: bool = True) -> dict:
        self.calls.append((job["job_id"], use_llm))
        if job["job_id"] == "agent_good_fit":
            return {
                "score": 91,
                "verdict": "strong_match",
                "worth_applying": True,
                "risks": [],
                "scoring_mode": "test",
            }
        return {
            "score": 35,
            "verdict": "skip",
            "worth_applying": False,
            "risks": ["Clearance and seniority mismatch."],
            "scoring_mode": "test",
        }


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[JobProcessRequest] = []

    def enqueue(self, payload) -> QueueEnqueueResponse:
        self.enqueued.append(payload.job)
        return QueueEnqueueResponse(
            queue_id=f"queue_{payload.job.job_id}",
            status="discovered",
            duplicate=False,
            message="queued",
        )


def test_job_discovery_agent_scores_and_enqueues_high_fit_jobs() -> None:
    feed = FakeJobFeed()
    matcher = FakeMatcher()
    queue = FakeQueue()
    agent = JobDiscoveryAgent(feed=feed, matcher=matcher, queue=queue)

    response = agent.run(
        JobDiscoveryAgentRequest(
            refresh_live=True,
            enqueue=True,
            min_match_score=80,
            max_enqueue=5,
            use_llm=False,
        )
    )

    assert response.discovered_count == 2
    assert response.analyzed_count == 2
    assert response.enqueued_count == 1
    assert [job.job_id for job in queue.enqueued] == ["agent_good_fit"]
    assert response.jobs[0].queue_id == "queue_agent_good_fit"
    assert response.jobs[1].queue_id == ""
    assert matcher.calls == [("agent_good_fit", False), ("agent_weak_fit", False)]
    assert feed.refresh_kwargs["include_web"] is True
    assert feed.refresh_kwargs["web_max_results"] == 35


def test_fit_scoring_agent_returns_analysis_without_live_llm() -> None:
    feed = FakeJobFeed()
    matcher = FakeMatcher()
    agent = FitScoringAgent(feed=feed, matcher=matcher)
    job = JobProcessRequest(
        job_id="agent_good_fit",
        company="Good Fit AI",
        title="Junior Data Scientist",
        jd_text="Python SQL machine learning dashboards.",
        discovered_url="https://example.com/good-fit",
        source="pytest",
    )

    response = agent.run(FitScoringAgentRequest(job=job, use_llm=False))

    assert response.score == 91
    assert response.verdict == "strong_match"
    assert response.worth_applying is True
    assert response.steps[0].agent == "fit_scoring"
    assert matcher.calls == [("agent_good_fit", False)]


def test_agents_capabilities_endpoint_is_registered() -> None:
    client = TestClient(app)

    response = client.get("/agents/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["orchestration"]["primary_entrypoint"] == "POST /agents/run-pipeline"
    assert {agent["name"] for agent in body["agents"]} >= {
        "job_discovery",
        "resume_tailoring",
        "page_watcher",
        "tracker_email",
    }


def test_page_watcher_agent_is_orchestrated_and_classifies_offline() -> None:
    from app.agents.page_watcher_agent import PageWatcherAgent
    from app.schemas.agent import PageWatcherAgentRequest
    from app.services.ats_autofill_service import ATSAutofillService
    from app.services.page_watcher_service import PageWatcherService

    agent = PageWatcherAgent(watcher=PageWatcherService(autofill=ATSAutofillService(), api_key=""))
    response = agent.run(
        PageWatcherAgentRequest(
            url="https://boards.greenhouse.io/acme/jobs/1",
            page_title="Data Scientist at Acme",
            page_text=(
                "About the role: responsibilities include Python, SQL, and machine learning. "
                "Minimum qualifications: 1 year of experience. Preferred qualifications: analytics."
            ),
            use_llm=False,
            fetch_if_empty=False,
        )
    )

    assert response.observation.page_type == "job_description"
    assert response.steps[0].agent == "page_watcher"
