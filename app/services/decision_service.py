from app.schemas.resume import ResumeDecisionRequest, ResumeDecisionResponse


class DecisionService:
    def decide(self, payload: ResumeDecisionRequest) -> ResumeDecisionResponse:
        base_score = payload.base_score
        tailored_score = payload.tailored_score
        final_score = tailored_score if tailored_score is not None else base_score

        improvement = 0
        if tailored_score is not None:
            improvement = tailored_score - base_score

        if final_score >= 90:
            return ResumeDecisionResponse(
                job_id=payload.job_id,
                decision="apply_now",
                reason="Fit score is very strong after evaluation and is suitable for immediate application."
            )

        if final_score >= 85:
            if tailored_score is not None and improvement > 0:
                return ResumeDecisionResponse(
                    job_id=payload.job_id,
                    decision="apply_now",
                    reason="Tailoring improved the resume enough to cross the application threshold."
                )
            return ResumeDecisionResponse(
                job_id=payload.job_id,
                decision="apply_now",
                reason="Fit score meets the application threshold."
            )

        if 75 <= final_score < 85:
            if tailored_score is not None and improvement >= 5:
                return ResumeDecisionResponse(
                    job_id=payload.job_id,
                    decision="manual_review",
                    reason="Resume tailoring improved alignment, but the role still needs manual review before applying."
                )
            return ResumeDecisionResponse(
                job_id=payload.job_id,
                decision="manual_review",
                reason="Role shows partial alignment, but the score remains below the apply threshold."
            )

        if 65 <= final_score < 75:
            return ResumeDecisionResponse(
                job_id=payload.job_id,
                decision="manual_review",
                reason="Role may be salvageable, but alignment is still too weak for automatic apply."
            )

        return ResumeDecisionResponse(
            job_id=payload.job_id,
            decision="reject",
            reason="Fit score is too low for a targeted application."
        )