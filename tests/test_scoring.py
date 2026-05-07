from app.schemas.job import ParsedJD
from app.schemas.resume import ResumeScoreRequest
from app.services.scoring_service import ScoringService


def test_scoring_returns_valid_score():
    service = ScoringService()
    payload = ResumeScoreRequest(
        job_id='job1',
        parsed_jd=ParsedJD(
            job_id='job1',
            company='Example',
            title='AI Engineer',
            required_skills=['python', 'rag'],
            preferred_skills=['fastapi'],
            years_required='1+ years',
            education="master's",
            responsibilities=['Build AI workflows'],
            keywords=['rag', 'deployment'],
            constraints=[]
        )
    )
    result = service.score(payload)
    assert 0 <= result.overall_score <= 100
