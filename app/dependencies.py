from functools import lru_cache

from app.services.canonicalization_service import CanonicalizationService
from app.services.decision_service import DecisionService
from app.services.jd_parser_service import JDParserService
from app.services.recruiter_service import RecruiterService
from app.services.scoring_service import ScoringService
from app.services.tailoring_service import TailoringService
from app.services.tracker_service import TrackerService
from app.services.pipeline_service import PipelineService


@lru_cache
def get_jd_parser_service() -> JDParserService:
    return JDParserService()


@lru_cache
def get_scoring_service() -> ScoringService:
    return ScoringService()


@lru_cache
def get_tailoring_service() -> TailoringService:
    return TailoringService()


@lru_cache
def get_decision_service() -> DecisionService:
    return DecisionService()


@lru_cache
def get_canonicalization_service() -> CanonicalizationService:
    return CanonicalizationService()


@lru_cache
def get_recruiter_service() -> RecruiterService:
    return RecruiterService()


@lru_cache
def get_tracker_service() -> TrackerService:
    return TrackerService()

@lru_cache
def get_pipeline_service() -> PipelineService:
    return PipelineService(
        parser=get_jd_parser_service(),
        scorer=get_scoring_service(),
        tailorer=get_tailoring_service(),
        decider=get_decision_service(),
        canonicalizer=get_canonicalization_service(),
        tracker=get_tracker_service(),
    )