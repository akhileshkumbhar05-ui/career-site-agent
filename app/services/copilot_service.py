from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.services.claude_tailoring_service import ClaudeTailoringService

from fastapi import HTTPException

from app.schemas.copilot import (
    APPLIED_USING_VALUES,
    STATUS_VALUES,
    ConfirmApplicationLogRequest,
    ConfirmApplicationLogResponse,
    ManualJDAnalyzeRequest,
    ManualJDAnalyzeResponse,
    PrepareApplicationLogRequest,
    PrepareApplicationLogResponse,
    SafeApplyPlan,
    SheetApplicationRow,
)
from app.schemas.job import JobQualityGateRequest
from app.schemas.resume import ResumeTailorRequest
from app.schemas.tracker import ApplicationRowCreateRequest, SheetsLogRequest
from app.services.job_quality_gate_service import JobQualityGateService
from app.services.llm_match_service import LLMMatchService
from app.services.tailoring_service import TailoringService
from app.services.tracker_service import TrackerService


class ManualJDCopilotService:
    def __init__(
        self,
        *,
        matcher: LLMMatchService,
        quality_gate: JobQualityGateService,
        tracker: TrackerService,
        tailorer: "TailoringService | ClaudeTailoringService | None" = None,
        data_dir: str = "data/manual_copilot",
    ) -> None:
        self.matcher = matcher
        self.quality_gate = quality_gate
        self.tracker = tracker
        self.tailorer = tailorer or TailoringService()
        self.data_dir = Path(data_dir)
        self.leads_path = self.data_dir / "leads.jsonl"
        self.audit_path = self.data_dir / "sheet_write_audit.jsonl"

    def analyze(self, payload: ManualJDAnalyzeRequest) -> ManualJDAnalyzeResponse:
        applied_using = self._resolve_applied_using(payload.applied_using, payload.source, payload.link)
        lead_id = self._lead_id(payload.company, payload.role, payload.link, payload.jd_text)
        job = {
            "job_id": lead_id,
            "company": payload.company.strip(),
            "title": payload.role.strip(),
            "jd_text": payload.jd_text.strip(),
            "discovered_url": payload.link.strip(),
            "source": payload.source.strip() or "Unknown",
            "location": payload.location.strip(),
            "salary_quoted": payload.salary_quoted.strip() or "N/A",
        }

        gate = self.quality_gate.evaluate(
            JobQualityGateRequest(
                company=job["company"],
                title=job["title"],
                jd_text=job["jd_text"],
                location=job["location"] or None,
                source=job["source"],
            )
        )
        match = self.matcher.analyze(job, use_llm=payload.use_llm)
        tailoring = self._tailoring_payload(match, job)
        apply_plan = self._apply_plan(job, gate.model_dump(), match)
        sheet_preview = self._sheet_row(
            company=job["company"],
            role=job["title"],
            salary_quoted=job["salary_quoted"],
            source=job["source"],
            applied_using=applied_using,
            status="",
            job_url=job["discovered_url"],
            date_applied="",
        ).as_legacy_sheet_row()

        response = ManualJDAnalyzeResponse(
            lead_id=lead_id,
            job=job,
            quality_gate=gate.model_dump(),
            match=match,
            tailoring=tailoring,
            apply_plan=apply_plan,
            sheet_preview=sheet_preview,
        )
        self._append_jsonl(
            self.leads_path,
            {
                "event": "manual_jd_analyzed",
                "created_at": self._now_iso(),
                "lead_id": lead_id,
                "company": job["company"],
                "role": job["title"],
                "link": job["discovered_url"],
                "recommendation": apply_plan.recommendation,
                "score": match.get("score"),
            },
        )
        return response

    def prepare_log(self, payload: PrepareApplicationLogRequest) -> PrepareApplicationLogResponse:
        applied_using = self._resolve_applied_using(payload.applied_using, payload.source, payload.link)
        if applied_using not in APPLIED_USING_VALUES:
            raise HTTPException(status_code=400, detail=f"Applied Using must be one of: {', '.join(APPLIED_USING_VALUES)}")

        row = self._sheet_row(
            company=payload.company,
            role=payload.role,
            salary_quoted=payload.salary_quoted,
            source=payload.source,
            applied_using=applied_using,
            status="Not Yet Applied Due to Technical Issue" if payload.technical_issue else "",
            job_url=payload.link,
            date_applied=self._today() if payload.technical_issue else "",
        )
        legacy_row = row.as_legacy_sheet_row()
        duplicate = self._find_duplicate(row)
        audit = {
            "event": "sheet_write_proposed",
            "created_at": self._now_iso(),
            "lead_id": payload.lead_id,
            "row": legacy_row,
            "technical_issue": payload.technical_issue,
            "duplicate": duplicate,
        }
        self._append_jsonl(self.audit_path, audit)

        if duplicate:
            return PrepareApplicationLogResponse(
                success=True,
                action="duplicate",
                message="An existing row matches this proposal; no write is needed.",
                row=legacy_row,
                duplicate_reason=duplicate["reason"],
                requires_human_confirmation=not payload.technical_issue,
                audit_path=str(self.audit_path),
            )

        return PrepareApplicationLogResponse(
            success=True,
            action="ready",
            message=(
                "Technical-issue row is ready to commit."
                if payload.technical_issue
                else "Row is ready; Date and Status remain blank until manual submission is confirmed."
            ),
            row=legacy_row,
            requires_human_confirmation=not payload.technical_issue,
            audit_path=str(self.audit_path),
        )

    def confirm_log(self, payload: ConfirmApplicationLogRequest) -> ConfirmApplicationLogResponse:
        status = "Not Yet Applied Due to Technical Issue" if payload.technical_issue else payload.status
        if status not in STATUS_VALUES:
            raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(STATUS_VALUES)}")
        if status == "Applied" and not payload.human_confirmed_submission:
            raise HTTPException(status_code=400, detail="Cannot log Status=Applied without manual submission confirmation.")

        applied_using = self._resolve_applied_using(payload.applied_using, payload.source, payload.link)
        if applied_using not in APPLIED_USING_VALUES:
            raise HTTPException(status_code=400, detail=f"Applied Using must be one of: {', '.join(APPLIED_USING_VALUES)}")

        row = self._sheet_row(
            company=payload.company,
            role=payload.role,
            salary_quoted=payload.salary_quoted,
            source=payload.source,
            applied_using=applied_using,
            status=status,
            job_url=payload.link,
            date_applied=payload.date_applied.strip() or self._today(),
        )
        legacy_row = row.as_legacy_sheet_row()
        duplicate = self._find_duplicate(row)
        audit_base = {
            "created_at": self._now_iso(),
            "lead_id": payload.lead_id,
            "row": legacy_row,
            "human_confirmed_submission": payload.human_confirmed_submission,
            "technical_issue": payload.technical_issue,
        }

        if duplicate:
            self._append_jsonl(self.audit_path, {**audit_base, "event": "sheet_write_duplicate_skipped", "duplicate": duplicate})
            return ConfirmApplicationLogResponse(
                success=True,
                action="duplicate_skipped",
                message="Duplicate row found; no new sheet-style row was written.",
                row=legacy_row,
                audit_path=str(self.audit_path),
                destination="none",
            )

        if self.tracker.sheets_configured:
            sheet_result = self.tracker.log_to_sheets(
                SheetsLogRequest(
                    date=row.date_applied,
                    company=row.company,
                    role=row.role,
                    salary=row.salary_quoted,
                    job_posted_on=row.source,
                    applied_using=row.applied_using,
                    status=row.status,
                    link=row.job_url,
                    human_confirmed_submission=payload.human_confirmed_submission,
                    technical_issue=payload.technical_issue,
                )
            )
            if not sheet_result.success:
                self._append_jsonl(
                    self.audit_path,
                    {**audit_base, "event": "sheet_write_failed", "message": sheet_result.message},
                )
                return ConfirmApplicationLogResponse(
                    success=False,
                    action="write_failed",
                    message=sheet_result.message,
                    row=legacy_row,
                    audit_path=str(self.audit_path),
                    destination="google_sheets",
                )

            duplicate_skipped = sheet_result.mode == "duplicate_skipped"
            event = "sheet_write_duplicate_skipped" if duplicate_skipped else "sheet_write_created"
            self._append_jsonl(
                self.audit_path,
                {**audit_base, "event": event, "target_row": sheet_result.target_row},
            )
            return ConfirmApplicationLogResponse(
                success=True,
                action="duplicate_skipped" if duplicate_skipped else "created",
                message=sheet_result.message,
                row=legacy_row,
                audit_path=str(self.audit_path),
                destination="google_sheets",
            )

        self.tracker.add_row(
            ApplicationRowCreateRequest(
                company_applied=row.company,
                role=row.role,
                salary_quoted_while_applying=row.salary_quoted,
                job_posted_on=row.source,
                applied_using=row.applied_using,
                status=row.status,
                link=row.job_url,
            )
        )
        self._append_jsonl(self.audit_path, {**audit_base, "event": "sheet_write_created"})
        return ConfirmApplicationLogResponse(
            success=True,
            action="created",
            message="Application row saved locally; Google Apps Script is not configured.",
            row=legacy_row,
            audit_path=str(self.audit_path),
            destination="local_tracker",
        )

    def _tailoring_payload(self, match: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
        parsed = match.get("parsed") or {}
        if not parsed:
            return {"status": "not_available", "changes_summary": ["JD parsing did not produce a tailoring payload."]}
        if match.get("verdict") == "skip" or int(match.get("score") or 0) < 65:
            return {
                "status": "not_worth_tailoring",
                "tailored_score": int(match.get("score") or 0),
                "changes_summary": ["Not worth tailoring until Akhilesh manually overrides the fit decision."],
            }
        response = self.tailorer.tailor(
            ResumeTailorRequest(
                job_id=str(match.get("job_id") or ""),
                parsed_jd=self._parsed_model(match, str(job.get("jd_text") or "")),
                current_score=int(match.get("base_score") or match.get("score") or 0),
            )
        )
        return {
            "status": "draft_ready",
            "engine": type(self.tailorer).__name__,
            "tailored_score": response.tailored_score,
            "selected_project_ids": response.selected_project_ids,
            "changes_summary": response.changes_summary,
            "summary_variant_key": response.summary_variant_key,
            "summary_text": getattr(response, "summary_text", "") or "",
            "rewritten_bullets": getattr(response, "rewritten_bullets", None) or [],
            "skill_gaps": getattr(response, "skill_gaps", None) or [],
            "connection_note": getattr(response, "connection_note", "") or "",
        }

    def _parsed_model(self, match: dict[str, Any], jd_text: str = ""):
        from app.schemas.job import ParsedJD

        parsed = match.get("parsed") or {}
        return ParsedJD(
            job_id=str(match.get("job_id") or ""),
            company=str(match.get("company") or ""),
            title=str(match.get("title") or ""),
            required_skills=list(parsed.get("required_skills") or []),
            preferred_skills=list(parsed.get("preferred_skills") or []),
            responsibilities=[],
            keywords=list(parsed.get("keywords") or []),
            constraints=list(parsed.get("constraints") or []),
            jd_text=jd_text or "",
        )

    def _apply_plan(self, job: dict[str, Any], gate: dict[str, Any], match: dict[str, Any]) -> SafeApplyPlan:
        verdict = str(match.get("verdict") or "review")
        if verdict in {"strong_match", "good_match"} and gate.get("decision") == "pass":
            recommendation = "apply"
        elif verdict == "skip" or gate.get("decision") == "reject":
            recommendation = "reject"
        else:
            recommendation = "manual_review"

        human_questions = [
            "Review tailored resume before upload.",
            "Answer EEO, salary, citizenship, security-clearance, and sponsorship questions manually.",
            "Resolve any low-confidence or ambiguous ATS fields manually.",
            "Click final submit manually, then confirm before logging Status=Applied.",
        ]
        if gate.get("authorization_risk") in {"medium", "high"}:
            human_questions.insert(0, "Review work authorization and sponsorship wording before continuing.")

        return SafeApplyPlan(
            recommendation=recommendation,
            safe_autofill={
                "company": str(job.get("company") or ""),
                "role": str(job.get("title") or ""),
                "job_url": str(job.get("discovered_url") or ""),
                "source": str(job.get("source") or "Unknown"),
            },
            human_review_required=human_questions,
            blocked_actions=[
                "Do not auto-submit the application.",
                "Do not fabricate resume experience, skills, salary, or authorization answers.",
                "Do not answer legal, EEO, citizenship, clearance, sponsorship, or salary fields automatically.",
            ],
            submission_boundary="The system may prepare data, but Akhilesh must review, submit, and confirm before Status=Applied is logged.",
        )

    def _find_duplicate(self, row: SheetApplicationRow) -> dict[str, str] | None:
        return self.tracker.find_duplicate(company=row.company, role=row.role, link=row.job_url)

    def _sheet_row(
        self,
        *,
        company: str,
        role: str,
        salary_quoted: str,
        source: str,
        applied_using: str,
        status: str,
        job_url: str,
        date_applied: str,
    ) -> SheetApplicationRow:
        return SheetApplicationRow(
            date_applied=date_applied.strip(),
            company=company.strip(),
            role=role.strip(),
            salary_quoted=salary_quoted.strip() or "N/A",
            source=source.strip() or "Unknown",
            applied_using=applied_using,
            status=status,
            job_url=job_url.strip(),
        )

    @staticmethod
    def _resolve_applied_using(value: str, source: str, link: str) -> str:
        explicit = value.strip()
        if explicit:
            return explicit

        link_lower = link.strip().lower()
        if "linkedin.com" in link_lower:
            return "LinkedIn"
        if "indeed.com" in link_lower:
            return "Indeed"
        if "ziprecruiter.com" in link_lower:
            return "ZipRecruiter"
        if "jobright.ai" in link_lower:
            return "Jobright.ai"
        if link_lower:
            return "Company Website"

        source_lower = source.strip().lower()
        if "linkedin" in source_lower:
            return "LinkedIn"
        if "indeed" in source_lower:
            return "Indeed"
        if "ziprecruiter" in source_lower:
            return "ZipRecruiter"
        if "jobright" in source_lower:
            return "Jobright.ai"
        return "Company Website"

    @staticmethod
    def _lead_id(company: str, role: str, link: str, jd_text: str) -> str:
        raw = "|".join([company.strip().lower(), role.strip().lower(), link.strip().lower(), jd_text[:1000]])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _today() -> str:
        return datetime.now(ZoneInfo("America/Chicago")).strftime("%m/%d/%Y")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(ZoneInfo("America/Chicago")).isoformat()

    @staticmethod
    def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
