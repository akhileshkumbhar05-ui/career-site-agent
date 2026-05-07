from app.schemas.job import ParsedJD
from app.schemas.resume import ResumeTailorRequest
from app.services.tailoring_service import TailoringService


def test_tailoring_increases_score():
    service = TailoringService()
    payload = ResumeTailorRequest(
        job_id='job2',
        parsed_jd=ParsedJD(
            job_id='job2',
            company='Example',
            title='Machine Learning Engineer',
            required_skills=['python', 'aws', 'deployment'],
            preferred_skills=['fastapi'],
            years_required='1+ years',
            education="master's",
            responsibilities=['Deploy ML systems'],
            keywords=['deployment', 'evaluation'],
            constraints=[]
        ),
        current_score=74
    )
    result = service.tailor(payload)
    assert result.tailored_score > payload.current_score
