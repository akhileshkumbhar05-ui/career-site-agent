from app.services.jd_parser_service import JDParserService
from app.services.job_quality_gate_service import JobQualityGateService
from app.services import llm_match_service
from app.services.llm_match_service import LLMMatchService
from app.services.scoring_service import ScoringService


def make_service(tmp_path):
    return LLMMatchService(
        parser=JDParserService(),
        scorer=ScoringService(),
        quality_gate=JobQualityGateService(),
        cache_dir=str(tmp_path / "llm_match_cache"),
    )


def test_llm_can_override_soft_title_reject(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)

    monkeypatch.setattr(
        service,
        "_call_llm",
        lambda *_args, **_kwargs: {
            "match_score": 86,
            "verdict": "good_match",
            "worth_applying": True,
            "one_line_reason": "The JD is a junior ML/data role despite the nonstandard title.",
            "strengths": ["ML systems work", "Python and model evaluation"],
            "gaps": [],
            "risks": ["Title wording is nonstandard."],
            "suggested_actions": ["Review JD.", "Tailor resume."],
            "sponsorship_note": "No obvious blocker.",
            "confidence": 0.82,
        },
    )

    result = service.analyze(
        {
            "job_id": "soft_title_override",
            "company": "Scale AI",
            "title": "ML Systems Engineer, Robotics",
            "jd_text": "Build Python data pipelines, evaluate machine learning models, and analyze production ML behavior. 1 year experience.",
            "location": "San Francisco, CA",
            "discovered_url": "https://example.com/ml-systems",
            "source": "pytest",
        },
        use_llm=True,
    )

    assert result["score"] == 86
    assert result["verdict"] == "good_match"
    assert result["worth_applying"] is True


def test_llm_cannot_override_hard_seniority_blocker(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)
    llm_called = False

    def fake_llm(*_args, **_kwargs):
        nonlocal llm_called
        llm_called = True
        return {}

    monkeypatch.setattr(service, "_call_llm", fake_llm)

    result = service.analyze(
        {
            "job_id": "hard_senior_blocker",
            "company": "Scale AI",
            "title": "Senior Machine Learning Engineer",
            "jd_text": "Build Python ML systems. 1 year experience.",
            "location": "San Francisco, CA",
            "discovered_url": "https://example.com/senior-ml",
            "source": "pytest",
        },
        use_llm=True,
    )

    assert result["score"] <= 59
    assert result["verdict"] == "skip"
    assert result["worth_applying"] is False
    assert any("Seniority blocker" in risk for risk in result["risks"])
    assert llm_called is False


def test_llm_match_sanitizes_false_blocker_language(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)

    monkeypatch.setattr(
        service,
        "_call_llm",
        lambda *_args, **_kwargs: {
            "match_score": 82,
            "verdict": "good_match",
            "worth_applying": True,
            "one_line_reason": "Security clearance and US citizenship are blocked.",
            "strengths": ["Python", "SQL"],
            "gaps": ["None"],
            "risks": ["None"],
            "suggested_actions": ["Tailor resume."],
            "sponsorship_note": "No obvious blocker.",
            "confidence": 0.8,
        },
    )

    result = service.analyze(
        {
            "job_id": "false_blocker_reason",
            "company": "GoodCo",
            "title": "Data Scientist",
            "jd_text": "Build Python SQL analytics and machine learning models. 1 year experience.",
            "location": "United States",
            "discovered_url": "https://example.com/data-scientist",
            "source": "pytest",
        },
        use_llm=True,
    )

    assert "blocked" not in result["one_line_reason"].lower()
    assert result["gaps"] == []
    assert result["risks"] == []


def test_cached_llm_match_normalizes_contradictory_zero_score(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)

    job = {
        "job_id": "contradictory_cache",
        "company": "GoodCo",
        "title": "Junior Data Scientist",
        "jd_text": "Build Python SQL machine learning models. 1 year experience.",
        "location": "United States",
        "discovered_url": "https://example.com/data-scientist",
        "source": "pytest",
    }
    monkeypatch.setattr(
        service,
        "_call_llm",
        lambda *_args, **_kwargs: {
            "match_score": 0,
            "verdict": "strong_match",
            "worth_applying": True,
            "one_line_reason": "Good alignment.",
            "strengths": ["Python"],
            "gaps": [],
            "risks": [],
            "suggested_actions": ["Tailor resume."],
            "sponsorship_note": "No obvious blocker.",
            "confidence": 0.8,
        },
    )

    result = service.analyze(job, use_llm=True)

    assert result["score"] > 0
    assert result["verdict"] != "strong_match"


def test_llm_match_keeps_quality_review_roles_as_review(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)

    monkeypatch.setattr(
        service,
        "_call_llm",
        lambda *_args, **_kwargs: {
            "match_score": 88,
            "verdict": "strong_match",
            "worth_applying": True,
            "one_line_reason": "Strong ML fit.",
            "strengths": ["Python", "ML"],
            "gaps": [],
            "risks": [],
            "suggested_actions": ["Review JD."],
            "sponsorship_note": "No obvious blocker.",
            "confidence": 0.8,
        },
    )

    result = service.analyze(
        {
            "job_id": "two_year_review",
            "company": "ReviewCo",
            "title": "Machine Learning Engineer",
            "jd_text": "Build Python machine learning systems. 2 years experience.",
            "location": "United States",
            "discovered_url": "https://example.com/two-year-review",
            "source": "pytest",
        },
        use_llm=True,
    )

    assert result["verdict"] == "review"
    assert result["score"] <= 77
    assert result["worth_applying"] is False


def test_match_scoring_prefers_ollama_when_configured(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)
    anthropic_called = False

    monkeypatch.setattr("app.services.llm_match_service.settings.llm_provider", "ollama")
    monkeypatch.setattr("app.services.llm_match_service.settings.ollama_model", "llama3.2:1b")
    monkeypatch.setattr("app.services.llm_match_service.settings.anthropic_api_key", "test-key")
    class FakeAnthropicModule:
        pass

    monkeypatch.setattr(llm_match_service, "anthropic", FakeAnthropicModule)
    monkeypatch.setattr(service.ollama, "is_available", lambda: True)
    monkeypatch.setattr(
        service.ollama,
        "generate_json",
        lambda *_args, **_kwargs: {
            "match_score": 82,
            "verdict": "good_match",
            "worth_applying": True,
            "one_line_reason": "Ollama scored this role.",
            "strengths": ["Python"],
            "gaps": [],
            "risks": [],
            "suggested_actions": ["Apply."],
            "sponsorship_note": "No obvious blocker.",
            "confidence": 0.8,
        },
    )

    class FakeAnthropic:
        def __init__(self, *_args, **_kwargs) -> None:
            nonlocal anthropic_called
            anthropic_called = True

    monkeypatch.setattr(FakeAnthropicModule, "Anthropic", FakeAnthropic, raising=False)

    result = service.analyze(
        {
            "job_id": "ollama_priority",
            "company": "GoodCo",
            "title": "Junior Data Scientist",
            "jd_text": "Build Python SQL machine learning models. 1 year experience.",
            "location": "United States",
            "discovered_url": "https://example.com/ollama-priority",
            "source": "pytest",
        },
        use_llm=True,
    )

    assert result["scoring_mode"] == "llm"
    assert result["llm_provider"] == "ollama"
    assert result["llm_model"] == "llama3.2:1b"
    assert anthropic_called is False


def test_sonnet_5_request_uses_supported_token_bounded_options(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            content = type(
                "Content",
                (),
                {
                    "text": (
                        '{"match_score": 84, "verdict": "good_match", '
                        '"worth_applying": true, "one_line_reason": "Grounded fit.", '
                        '"strengths": ["Python"], "gaps": [], "risks": [], '
                        '"suggested_actions": ["Review."], '
                        '"sponsorship_note": "No obvious blocker.", "confidence": 0.8}'
                    )
                },
            )()
            return type("Message", (), {"content": [content]})()

    class FakeAnthropicClient:
        def __init__(self, **_kwargs) -> None:
            self.messages = FakeMessages()

    class FakeAnthropicModule:
        Anthropic = FakeAnthropicClient

    monkeypatch.setattr(llm_match_service, "anthropic", FakeAnthropicModule)
    monkeypatch.setattr("app.services.llm_match_service.settings.llm_provider", "mock")
    monkeypatch.setattr("app.services.llm_match_service.settings.anthropic_api_key", "test-key")
    monkeypatch.setattr("app.services.llm_match_service.settings.anthropic_model", "claude-sonnet-5")
    monkeypatch.setattr(service.ollama, "is_available", lambda: False)

    result = service.analyze(
        {
            "job_id": "sonnet_5_options",
            "company": "GoodCo",
            "title": "Junior Data Scientist",
            "jd_text": "Build Python and SQL machine learning models with one year of experience.",
            "location": "United States",
            "discovered_url": "https://example.com/sonnet-5-options",
            "source": "pytest",
        },
        use_llm=True,
    )

    assert result["llm_model"] == "claude-sonnet-5"
    assert captured["model"] == "claude-sonnet-5"
    assert captured["thinking"] == {"type": "disabled"}
    assert "temperature" not in captured
