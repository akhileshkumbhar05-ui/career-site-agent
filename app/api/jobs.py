from fastapi import APIRouter, Depends

from app.dependencies import get_canonicalization_service, get_jd_parser_service
from app.schemas.job import JobLead, OfficialJobResolutionRequest, OfficialJobResolutionResponse, JDParseRequest, ParsedJD
from app.services.canonicalization_service import CanonicalizationService
from app.services.jd_parser_service import JDParserService

router = APIRouter()


@router.post("/normalize", response_model=JobLead)
def normalize_job(job: JobLead) -> JobLead:
    job.company = job.company.strip()
    job.title = job.title.strip()
    return job


@router.post("/resolve-official", response_model=OfficialJobResolutionResponse)
def resolve_official(
    payload: OfficialJobResolutionRequest,
    service: CanonicalizationService = Depends(get_canonicalization_service),
) -> OfficialJobResolutionResponse:
    return service.resolve(payload)


@router.post("/parse-jd", response_model=ParsedJD)
def parse_jd(
    payload: JDParseRequest,
    service: JDParserService = Depends(get_jd_parser_service),
) -> ParsedJD:
    return service.parse(payload)
