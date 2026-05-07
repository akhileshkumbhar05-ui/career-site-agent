from app.schemas.resume import ResumeDecisionRequest
from app.services.decision_service import DecisionService


def test_decision_apply_now():
    service = DecisionService()
    result = service.decide(ResumeDecisionRequest(job_id='job3', base_score=88))
    assert result.decision == 'apply_now'
