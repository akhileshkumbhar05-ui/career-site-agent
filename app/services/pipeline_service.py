from app.schemas.job import JDParseRequest, OfficialJobResolutionRequest
from app.schemas.job import JobQualityGateRequest
from app.schemas.pipeline import JobProcessRequest, JobProcessResponse
from app.schemas.resume import (
    ResumeDecisionRequest,
    ResumeScoreRequest,
    ResumeTailorRequest,
)
from app.schemas.tracker import ApplicationRowCreateRequest
from app.services.canonicalization_service import CanonicalizationService
from app.services.decision_service import DecisionService
from app.services.application_packet_service import ApplicationPacketService
from app.services.jd_parser_service import JDParserService
from app.services.job_quality_gate_service import JobQualityGateService
from app.services.scoring_service import ScoringService
from app.services.tailoring_service import TailoringService
from app.services.tracker_service import TrackerService


class PipelineService:
    def __init__(
        self,
        parser: JDParserService,
        scorer: ScoringService,
        tailorer: TailoringService,
        decider: DecisionService,
        canonicalizer: CanonicalizationService,
        tracker: TrackerService,
        quality_gate: JobQualityGateService,
        packet_builder: ApplicationPacketService,
    ) -> None:
        self.parser = parser
        self.scorer = scorer
        self.tailorer = tailorer
        self.decider = decider
        self.canonicalizer = canonicalizer
        self.tracker = tracker
        self.quality_gate = quality_gate
        self.packet_builder = packet_builder

    def process_job(self, payload: JobProcessRequest) -> JobProcessResponse:
        resume_version = "base_resume_v1"

        gate = self.quality_gate.evaluate(
            JobQualityGateRequest(
                company=payload.company,
                title=payload.title,
                jd_text=payload.jd_text,
                location=payload.location,
                source=payload.source,
            )
        )

        if gate.decision == "reject":
            gate_reason = "; ".join(gate.blockers or gate.reasons)
            return JobProcessResponse(
                job_id=payload.job_id,
                company=payload.company,
                title=payload.title,
                canonical_job_id=payload.job_id,
                official_url=payload.discovered_url,
                ats_type="unknown",
                resolution_status="skipped_by_quality_gate",
                resolution_confidence=0.0,
                base_score=0,
                tailored_score=None,
                decision="reject",
                decision_reason=f"Quality gate rejected this lead: {gate_reason}",
                recommended_resume_version=resume_version,
                tracker_status="Not Applied",
                quality_gate_decision=gate.decision,
                quality_gate_reasons=gate.reasons,
                quality_gate_blockers=gate.blockers,
                target_role_key=gate.role_key,
                selected_project_ids=[],
                changes_summary=[],
                summary_text=None,
                rewritten_bullets=[],
                connection_note=None,
            )

        resolution = self.canonicalizer.resolve(
            OfficialJobResolutionRequest(
                company=payload.company,
                title=payload.title,
                discovered_url=payload.discovered_url,
                source=payload.source,
            )
        )

        parsed = self.parser.parse(
            JDParseRequest(
                job_id=payload.job_id,
                company=payload.company,
                title=payload.title,
                official_url=resolution.official_url or None,
                jd_text=payload.jd_text,
            )
        )

        score = self.scorer.score(
            ResumeScoreRequest(
                job_id=payload.job_id,
                resume_version=resume_version,
                parsed_jd=parsed,
            )
        )

        tailored = None
        if 65 <= score.overall_score < 85:
            tailored = self.tailorer.tailor(
                ResumeTailorRequest(
                    job_id=payload.job_id,
                    resume_version=resume_version,
                    parsed_jd=parsed,
                    current_score=score.overall_score,
                )
            )

        decision = self.decider.decide(
            ResumeDecisionRequest(
                job_id=payload.job_id,
                base_score=score.overall_score,
                tailored_score=tailored.tailored_score if tailored else None,
            )
        )

        tracker_status = "Not Applied"

        self.tracker.add_row(
            ApplicationRowCreateRequest(
                company_applied=payload.company,
                role=payload.title,
                salary_quoted_while_applying="N/A",
                job_posted_on=payload.source or "Unknown",
                applied_using="Company Website",
                status=tracker_status,
                link=resolution.official_url or payload.discovered_url,
                job_id=payload.job_id,
                base_match_percent=int(score.overall_score),
                tailored_match_percent=int(tailored.tailored_score) if tailored else None,
                resume_version_used=resume_version,
                notes=decision.reason,
            )
        )

        application_packet = None
        if decision.decision != "reject":
            application_packet = self.packet_builder.build(
                job_id=payload.job_id,
                company=payload.company,
                role=payload.title,
                official_url=resolution.official_url or payload.discovered_url,
                base_score=int(score.overall_score),
                tailored_score=int(tailored.tailored_score) if tailored else None,
                decision=decision.decision,
                decision_reason=decision.reason,
                target_role_key=gate.role_key,
                source=payload.source,
                posted_at=payload.posted_at,
                location=payload.location,
            )

        selected_project_ids = tailored.selected_project_ids if tailored else []
        changes_summary = tailored.changes_summary if tailored else []
        summary_text = tailored.summary_text if tailored else None
        rewritten_bullets = tailored.rewritten_bullets if tailored and tailored.rewritten_bullets else []
        connection_note = tailored.connection_note if tailored else None

        return JobProcessResponse(
            job_id=payload.job_id,
            company=payload.company,
            title=payload.title,
            canonical_job_id=resolution.canonical_job_id,
            official_url=resolution.official_url,
            ats_type=resolution.ats_type,
            resolution_status=resolution.status,
            resolution_confidence=resolution.confidence,
            base_score=int(score.overall_score),
            tailored_score=int(tailored.tailored_score) if tailored else None,
            decision=decision.decision,
            decision_reason=decision.reason,
            recommended_resume_version=resume_version,
            tracker_status=tracker_status,
            quality_gate_decision=gate.decision,
            quality_gate_reasons=gate.reasons,
            quality_gate_blockers=gate.blockers,
            target_role_key=gate.role_key,
            selected_project_ids=selected_project_ids,
            changes_summary=changes_summary,
            summary_text=summary_text,
            rewritten_bullets=rewritten_bullets,
            connection_note=connection_note,
            application_packet=application_packet,
        )
