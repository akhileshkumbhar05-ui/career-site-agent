from functools import lru_cache

from app.agents.fit_scoring_agent import FitScoringAgent
from app.agents.job_discovery_agent import JobDiscoveryAgent
from app.agents.page_watcher_agent import PageWatcherAgent
from app.agents.recruiter_outreach_agent import RecruiterOutreachAgent
from app.agents.resume_tailoring_agent import ResumeTailoringAgent
from app.agents.tracker_email_agent import TrackerEmailAgent
from app.config import settings
from app.services.application_packet_export_service import ApplicationPacketExportService
from app.services.application_packet_service import ApplicationPacketService
from app.services.application_orchestrator_service import ApplicationOrchestratorService
from app.services.ats_autofill_service import ATSAutofillService
from app.services.autofill_autopilot_service import AutofillAutopilotService
from app.services.autofill_context_service import AutofillContextService
from app.services.canonicalization_service import CanonicalizationService
from app.services.career_agent_orchestrator_service import CareerAgentOrchestratorService
from app.services.claude_tailoring_service import ClaudeTailoringService
from app.services.decision_service import DecisionService
from app.services.jd_parser_service import JDParserService
from app.services.job_feed_service import JobFeedService
from app.services.job_queue_service import JobQueueService
from app.services.job_quality_gate_service import JobQualityGateService
from app.services.llm_match_service import LLMMatchService
from app.services.copilot_service import ManualJDCopilotService
from app.services.page_watcher_service import PageWatcherService
from app.services.recruiter_service import RecruiterService
from app.services.scoring_service import ScoringService
from app.services.tailoring_service import TailoringService
from app.services.tailoring_review_service import TailoringReviewService
from app.services.tracker_service import TrackerService
from app.services.pipeline_service import PipelineService


@lru_cache
def get_jd_parser_service() -> JDParserService:
    return JDParserService()


@lru_cache
def get_scoring_service() -> ScoringService:
    return ScoringService()


@lru_cache
def get_tailoring_service() -> TailoringService | ClaudeTailoringService:
    if settings.anthropic_api_key:
        try:
            return ClaudeTailoringService(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
        except RuntimeError:
            pass
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
def get_job_quality_gate_service() -> JobQualityGateService:
    return JobQualityGateService()


@lru_cache
def get_tracker_service() -> TrackerService:
    return TrackerService()


@lru_cache
def get_application_packet_service() -> ApplicationPacketService:
    return ApplicationPacketService()


@lru_cache
def get_application_packet_export_service() -> ApplicationPacketExportService:
    return ApplicationPacketExportService()


@lru_cache
def get_ats_autofill_service() -> ATSAutofillService:
    return ATSAutofillService()


@lru_cache
def get_autofill_context_service() -> AutofillContextService:
    return AutofillContextService(
        autofill=get_ats_autofill_service(),
        parser=get_jd_parser_service(),
        scorer=get_scoring_service(),
        tailorer=get_tailoring_service(),
        decider=get_decision_service(),
        quality_gate=get_job_quality_gate_service(),
        packet_builder=get_application_packet_service(),
        packet_exporter=get_application_packet_export_service(),
    )


@lru_cache
def get_tailoring_review_service() -> TailoringReviewService:
    return TailoringReviewService(context=get_autofill_context_service())


@lru_cache
def get_autofill_autopilot_service() -> AutofillAutopilotService:
    return AutofillAutopilotService(autofill=get_ats_autofill_service())


@lru_cache
def get_page_watcher_service() -> PageWatcherService:
    return PageWatcherService(
        autofill=get_ats_autofill_service(),
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
    )


@lru_cache
def get_job_queue_service() -> JobQueueService:
    return JobQueueService()


@lru_cache
def get_job_feed_service() -> JobFeedService:
    return JobFeedService(quality_gate=get_job_quality_gate_service())


@lru_cache
def get_llm_match_service() -> LLMMatchService:
    return LLMMatchService(
        parser=get_jd_parser_service(),
        scorer=get_scoring_service(),
        quality_gate=get_job_quality_gate_service(),
    )


@lru_cache
def get_manual_jd_copilot_service() -> ManualJDCopilotService:
    return ManualJDCopilotService(
        matcher=get_llm_match_service(),
        quality_gate=get_job_quality_gate_service(),
        tracker=get_tracker_service(),
        tailorer=get_tailoring_service(),
    )


@lru_cache
def get_pipeline_service() -> PipelineService:
    return PipelineService(
        parser=get_jd_parser_service(),
        scorer=get_scoring_service(),
        tailorer=get_tailoring_service(),
        decider=get_decision_service(),
        canonicalizer=get_canonicalization_service(),
        tracker=get_tracker_service(),
        quality_gate=get_job_quality_gate_service(),
        packet_builder=get_application_packet_service(),
    )


@lru_cache
def get_application_orchestrator_service() -> ApplicationOrchestratorService:
    return ApplicationOrchestratorService(
        queue=get_job_queue_service(),
        pipeline=get_pipeline_service(),
        packet_exporter=get_application_packet_export_service(),
    )


@lru_cache
def get_job_discovery_agent() -> JobDiscoveryAgent:
    return JobDiscoveryAgent(
        feed=get_job_feed_service(),
        matcher=get_llm_match_service(),
        queue=get_job_queue_service(),
    )


@lru_cache
def get_fit_scoring_agent() -> FitScoringAgent:
    return FitScoringAgent(
        feed=get_job_feed_service(),
        matcher=get_llm_match_service(),
    )


@lru_cache
def get_resume_tailoring_agent() -> ResumeTailoringAgent:
    return ResumeTailoringAgent(
        queue=get_job_queue_service(),
        pipeline=get_pipeline_service(),
        packet_exporter=get_application_packet_export_service(),
    )


@lru_cache
def get_page_watcher_agent() -> PageWatcherAgent:
    return PageWatcherAgent(watcher=get_page_watcher_service())


@lru_cache
def get_recruiter_outreach_agent() -> RecruiterOutreachAgent:
    return RecruiterOutreachAgent(recruiter=get_recruiter_service())


@lru_cache
def get_tracker_email_agent() -> TrackerEmailAgent:
    return TrackerEmailAgent(tracker=get_tracker_service())


@lru_cache
def get_career_agent_orchestrator_service() -> CareerAgentOrchestratorService:
    return CareerAgentOrchestratorService(
        discovery_agent=get_job_discovery_agent(),
        scoring_agent=get_fit_scoring_agent(),
        tailoring_agent=get_resume_tailoring_agent(),
        watcher_agent=get_page_watcher_agent(),
        recruiter_agent=get_recruiter_outreach_agent(),
        tracker_email_agent=get_tracker_email_agent(),
        queue_orchestrator=get_application_orchestrator_service(),
    )
