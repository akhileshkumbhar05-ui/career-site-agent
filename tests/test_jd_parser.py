from app.schemas.job import JDParseRequest
from app.services.jd_parser_service import JDParserService


def test_jd_parser_extracts_required_skills():
    service = JDParserService()
    payload = JDParseRequest(
        job_id='test_job',
        title='Data Scientist',
        company='Example',
        jd_text='Need Python, SQL, machine learning, and AWS experience. Bachelor degree required.'
    )
    parsed = service.parse(payload)
    assert 'python' in parsed.required_skills
    assert parsed.education is not None
