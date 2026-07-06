from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.schemas.application_packet import ApplicationPacketExportRequest
from app.schemas.job import JDParseRequest, JobQualityGateRequest
from app.schemas.resume import ResumeDecisionRequest, ResumeScoreRequest, ResumeTailorRequest
from app.schemas.tailoring_review import (
    TailoringDraftBullet,
    TailoringDraftPublication,
    TailoringDraftProject,
    TailoringDraftRequest,
    TailoringDraftResponse,
    TailoringFinalizeRequest,
    TailoringFinalizeResponse,
    TailoringPreviewRenderResponse,
)
from app.services.autofill_context_service import AutofillContextService
from app.services.profile_evidence_service import ProfileEvidenceService
from app.services.resume_quality_service import ResumeQualityService


class TailoringReviewService:
    def __init__(
        self,
        *,
        context: AutofillContextService,
        draft_dir: str = "data/tailoring_drafts",
        audit_path: str = "data/tailoring_review_audit.jsonl",
        master_resume_path: str = "data/master_resume/master_resume.json",
    ) -> None:
        self.context = context
        self.draft_dir = Path(draft_dir)
        self.audit_path = Path(audit_path)
        self.master_resume_path = Path(master_resume_path)

    def create_draft(self, payload: TailoringDraftRequest) -> TailoringDraftResponse:
        page_text = self.context._clean_page_text(payload.page_text)[: payload.max_page_text_chars]
        if len(page_text) < 800 or not self.context._has_job_description_signal(page_text):
            fetched = self.context._fetch_page_text(payload.url)
            if len(fetched) > len(page_text):
                page_text = fetched[: payload.max_page_text_chars]
        identity = self.context._infer_page_identity(payload.page_title, payload.url, page_text)
        company = payload.company.strip() or identity["company"]
        role = payload.role.strip() or identity["role"]
        location = identity["location"]

        if not page_text or not role or not self.context._has_job_description_signal(page_text):
            raise HTTPException(status_code=422, detail="Open a full job description page before creating a tailoring draft.")

        gate = self.context.quality_gate.evaluate(
            JobQualityGateRequest(
                company=company,
                title=role,
                jd_text=page_text,
                location=location,
                source=payload.source,
            )
        )
        hard_blockers = self.context._manual_tailor_blockers(gate.blockers)
        if gate.decision == "reject" and hard_blockers:
            raise HTTPException(status_code=422, detail="Tailoring blocked: " + "; ".join(hard_blockers))

        target_role_key = gate.role_key or self.context._infer_target_role_key(role, page_text) or ""
        job_id = self.context._job_id_from_url(payload.url) or f"third_eye_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        parsed = self.context.parser.parse(
            JDParseRequest(
                job_id=job_id,
                company=company,
                title=role,
                official_url=payload.url or None,
                jd_text=page_text,
            )
        )
        score = self.context.scorer.score(
            ResumeScoreRequest(job_id=job_id, resume_version="base_resume_v1", parsed_jd=parsed)
        )
        tailored = self.context.tailorer.tailor(
            ResumeTailorRequest(
                job_id=job_id,
                resume_version="base_resume_v1",
                parsed_jd=parsed,
                current_score=score.overall_score,
                preferences=payload.tailoring_preferences,
            )
        )
        if not tailored.selected_project_ids and not tailored.summary_text and not tailored.rewritten_bullets:
            reason = "; ".join(tailored.changes_summary or ["This role was not worth tailoring."])
            raise HTTPException(status_code=422, detail=reason)

        master = self._master_resume()
        bullets = self._draft_bullets(tailored.rewritten_bullets or [], master)
        emphasis = set(payload.tailoring_preferences.emphasis)
        projects = self._draft_projects(tailored.selected_project_ids, master) if "projects" in emphasis else []
        publications = self._draft_publications(master) if "research_papers" in emphasis else []
        draft_id = uuid4().hex
        record = {
            "draft_id": draft_id,
            "created_at": datetime.now(UTC).isoformat(),
            "job": {
                "job_id": job_id,
                "company": company,
                "role": role,
                "url": payload.url,
                "source": payload.source,
                "location": location,
                "target_role_key": target_role_key,
                "page_text": page_text,
            },
            "base_score": int(score.overall_score),
            "tailored_score": int(tailored.tailored_score),
            "preferences": payload.tailoring_preferences.model_dump(),
            "summary_original": str(master.get("candidate", {}).get("base_summary") or ""),
            "summary_proposed": str(tailored.summary_text or ""),
            "bullets": [item.model_dump() for item in bullets],
            "projects": [item.model_dump() for item in projects],
            "publications": [item.model_dump() for item in publications],
            "skill_gaps": tailored.skill_gaps,
            "connection_note": tailored.connection_note or "",
            "cover_letter_text": tailored.cover_letter_text or "",
            "changes_summary": tailored.changes_summary,
            "finalized": {},
        }
        self._write_draft(record)
        self._audit(
            "draft_created",
            {
                "draft_id": draft_id,
                "company": company,
                "role": role,
                "url": payload.url,
                "target_role_key": target_role_key,
                "preferences": payload.tailoring_preferences.model_dump(),
                "base_score": score.overall_score,
                "tailored_score": tailored.tailored_score,
            },
        )
        return self._draft_response(record)

    def finalize(self, payload: TailoringFinalizeRequest) -> TailoringFinalizeResponse:
        record = self._read_draft(payload.draft_id)
        summary, rewritten = self._review_payload_parts(record, payload)

        job = record["job"]
        decision = self.context.decider.decide(
            ResumeDecisionRequest(
                job_id=job["job_id"],
                base_score=record["base_score"],
                tailored_score=record["tailored_score"],
            )
        )
        packet = self.context.packet_builder.build(
            job_id=job["job_id"],
            company=job["company"],
            role=job["role"],
            official_url=job["url"],
            base_score=record["base_score"],
            tailored_score=record["tailored_score"],
            decision=decision.decision,
            decision_reason=decision.reason,
            target_role_key=job["target_role_key"] or None,
            source=job["source"],
            location=job["location"],
        )
        export = self.context.packet_exporter.export(
            ApplicationPacketExportRequest(
                application_packet=packet,
                output_root_override=payload.output_root_override or None,
                selected_project_ids=payload.project_ids,
                # The reviewer's selection is explicit — an empty list means "no projects section".
                auto_select_projects=False,
                selected_publication_ids=payload.publication_ids,
                include_publications=bool(payload.publication_ids),
                bullet_counts=payload.bullet_counts,
                changes_summary=record.get("changes_summary", []),
                summary_text=summary,
                rewritten_bullets=rewritten,
                connection_note=payload.connection_note.strip() or record.get("connection_note", ""),
                cover_letter_text=self._cover_letter_for_finalize(record, payload),
                jd_text=job["page_text"],
                render_pdf=payload.render_pdf,
            )
        )
        finalized = {
            "created_at": datetime.now(UTC).isoformat(),
            "docx_path": export.tailored_resume_docx_path,
            "pdf_path": export.tailored_resume_pdf_path or "",
            "apply_plan_path": export.apply_plan_path,
            "cover_letter_path": export.cover_letter_path,
            "quality_passed": export.quality_passed,
            "quality_checks": export.quality_checks,
            "project_ids": payload.project_ids,
            "publication_ids": payload.publication_ids,
            "accepted_bullet_count": len(rewritten),
        }
        record["finalized"] = finalized
        self._write_draft(record)
        self._audit(
            "draft_finalized",
            {
                "draft_id": payload.draft_id,
                "company": job["company"],
                "role": job["role"],
                "project_ids": payload.project_ids,
                "publication_ids": payload.publication_ids,
                "accepted_bullet_count": len(rewritten),
                "quality_passed": export.quality_passed,
                "docx_ready": bool(export.tailored_resume_docx_path),
                "pdf_ready": bool(export.tailored_resume_pdf_path),
            },
        )
        return TailoringFinalizeResponse(
            draft_id=payload.draft_id,
            quality_passed=export.quality_passed,
            quality_checks=export.quality_checks,
            docx_ready=Path(export.tailored_resume_docx_path).exists(),
            pdf_ready=bool(export.tailored_resume_pdf_path and Path(export.tailored_resume_pdf_path).exists()),
            docx_download_path=f"/autofill/tailoring/download/{payload.draft_id}/docx",
            pdf_download_path=(
                f"/autofill/tailoring/download/{payload.draft_id}/pdf"
                if export.tailored_resume_pdf_path
                else ""
            ),
            prepared_resume_docx_path=export.tailored_resume_docx_path,
            prepared_resume_pdf_path=export.tailored_resume_pdf_path or "",
            prepared_apply_plan_path=export.apply_plan_path,
            apply_url=job["url"],
            cover_letter_path=export.cover_letter_path,
            message="Final resume rendered locally. Use Download DOCX or Download PDF to choose a save location.",
        )

    def render_preview(self, payload: TailoringFinalizeRequest) -> TailoringPreviewRenderResponse:
        record = self._read_draft(payload.draft_id)
        summary, rewritten = self._review_payload_parts(record, payload)
        return TailoringPreviewRenderResponse(
            draft_id=payload.draft_id,
            resume_preview_html=self._build_resume_preview_html(
                record,
                summary=summary,
                rewritten=rewritten,
                project_ids=payload.project_ids,
                publication_ids=payload.publication_ids,
                bullet_counts=payload.bullet_counts,
            ),
        )

    def download_path(self, draft_id: str, file_format: str) -> Path:
        record = self._read_draft(draft_id)
        finalized = record.get("finalized") or {}
        key = "docx_path" if file_format == "docx" else "pdf_path"
        path = Path(str(finalized.get(key) or ""))
        if file_format not in {"docx", "pdf"} or not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail=f"{file_format.upper()} file is not available.")
        return path

    def _draft_response(self, record: dict[str, Any]) -> TailoringDraftResponse:
        job = record["job"]
        return TailoringDraftResponse(
            draft_id=record["draft_id"],
            company=job["company"],
            role=job["role"],
            target_role_key=job["target_role_key"],
            base_score=record["base_score"],
            tailored_score=record["tailored_score"],
            preferences=record["preferences"],
            summary_original=record["summary_original"],
            summary_proposed=record["summary_proposed"],
            bullets=record["bullets"],
            projects=record["projects"],
            publications=record.get("publications", []),
            skill_gaps=record.get("skill_gaps", []),
            connection_note=record.get("connection_note", ""),
            cover_letter_text=record.get("cover_letter_text", ""),
            changes_summary=record.get("changes_summary", []),
            resume_preview_html=self._build_resume_preview_html(record),
            message="Claude draft is ready for review. No resume file has been generated yet.",
        )

    def _draft_bullets(self, bullets: list[dict], master: dict) -> list[TailoringDraftBullet]:
        result: list[TailoringDraftBullet] = []
        for index, bullet in enumerate(bullets[:50]):
            if not isinstance(bullet, dict) or not bullet.get("rewritten"):
                continue
            section = str(bullet.get("section") or "project").lower()
            item_id = str(
                bullet.get("project_id")
                or bullet.get("experience_id")
                or bullet.get("publication_id")
                or bullet.get("item_id")
                or ""
            )
            original = str(bullet.get("original") or self._lookup_original(master, section, item_id) or "")
            proposed = str(bullet.get("rewritten") or "")
            if not self._acceptable_rewrite(original, proposed):
                continue
            digest = hashlib.sha256(f"{section}|{item_id}|{index}|{original}|{proposed}".encode()).hexdigest()[:16]
            result.append(
                TailoringDraftBullet(
                    bullet_id=digest,
                    section=section,
                    item_id=item_id,
                    item_label=self._item_label(master, section, item_id),
                    original=original,
                    proposed=proposed,
                )
            )
        return result

    @staticmethod
    def _draft_projects(selected_ids: list[str], master: dict) -> list[TailoringDraftProject]:
        by_id = {str(item.get("id") or ""): item for item in master.get("projects", [])}
        effective_ids = selected_ids[:3]
        return [
            TailoringDraftProject(
                project_id=project_id,
                name=str(by_id.get(project_id, {}).get("name") or project_id),
            )
            for project_id in effective_ids
            if project_id in by_id
        ]

    @staticmethod
    def _draft_publications(master: dict) -> list[TailoringDraftPublication]:
        result: list[TailoringDraftPublication] = []
        for item in master.get("publications", [])[:2]:
            title = str(item.get("title") or "")
            venue = str(item.get("venue") or "")
            year = str(item.get("year") or "")
            publication_id = TailoringReviewService._publication_id(item)
            if title and publication_id:
                result.append(
                    TailoringDraftPublication(
                        publication_id=publication_id,
                        title=title,
                        venue=venue,
                        year=year,
                    )
                )
        return result

    @staticmethod
    def _publication_id(item: dict) -> str:
        if item.get("id"):
            return str(item.get("id"))
        raw = f"{item.get('title', '')}_{item.get('venue', '')}_{item.get('year', '')}".lower()
        return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")[:96]

    def _review_payload_parts(
        self,
        record: dict[str, Any],
        payload: TailoringFinalizeRequest,
    ) -> tuple[str, list[dict[str, str]]]:
        known_bullets = {item["bullet_id"]: item for item in record.get("bullets", [])}
        decisions = {item.bullet_id: item for item in payload.bullets}
        rewritten: list[dict[str, str]] = []
        for bullet_id, source in known_bullets.items():
            decision = decisions.get(bullet_id)
            if decision is None or not decision.accepted:
                continue
            text = decision.text.strip() or source["proposed"]
            self._validate_edit(text, source["original"])
            if not self._acceptable_rewrite(source["original"], text):
                continue
            rewritten.append(
                {
                    "section": source["section"],
                    "item_id": source["item_id"],
                    "project_id": source["item_id"] if source["section"] == "project" else "",
                    "experience_id": source["item_id"] if source["section"] == "experience" else "",
                    "publication_id": source["item_id"] if source["section"] in {"publication", "research", "research_paper"} else "",
                    "original": source["original"],
                    "rewritten": text,
                }
            )

        allowed_projects = {item["project_id"] for item in record.get("projects", [])}
        if any(project_id not in allowed_projects for project_id in payload.project_ids):
            raise HTTPException(status_code=400, detail="Project selection contains an unknown project.")
        allowed_publications = {item["publication_id"] for item in record.get("publications", [])}
        if any(publication_id not in allowed_publications for publication_id in payload.publication_ids):
            raise HTTPException(status_code=400, detail="Research paper selection contains an unknown publication.")

        summary = record["summary_proposed"] if payload.summary_accepted else record["summary_original"]
        if payload.summary_accepted and payload.summary_text.strip():
            summary = payload.summary_text.strip()
        self._validate_edit(summary, record["summary_original"], max_length=1400)
        return summary, rewritten

    def _cover_letter_for_finalize(self, record: dict[str, Any], payload: TailoringFinalizeRequest) -> str:
        if not payload.cover_letter_accepted:
            return ""
        text = (payload.cover_letter_text.strip() or str(record.get("cover_letter_text") or "").strip())
        if not text:
            return ""
        if len(text) > 4000:
            raise HTTPException(status_code=400, detail="Cover letter is too long.")
        profile_context = ProfileEvidenceService().build_prompt_context(max_chars=60000)
        master_text = self.master_resume_path.read_text(encoding="utf-8") + "\n" + str(profile_context)
        supported_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", master_text))
        unsupported = sorted(set(re.findall(r"\d+(?:\.\d+)?%?", text)) - supported_numbers)
        if unsupported:
            raise HTTPException(
                status_code=400,
                detail="Cover letter contains unsupported metrics: " + ", ".join(unsupported),
            )
        if ProfileEvidenceService._sanitize(text) != text:
            raise HTTPException(status_code=400, detail="Cover letter contains credential-like or secret content.")
        return text

    def _build_resume_preview_html(
        self,
        record: dict[str, Any],
        *,
        summary: str | None = None,
        rewritten: list[dict[str, str]] | None = None,
        project_ids: list[str] | None = None,
        publication_ids: list[str] | None = None,
        bullet_counts: Any | None = None,
    ) -> str:
        master = self._master_resume()
        counts = self._coerce_bullet_counts(bullet_counts or self._record_bullet_counts(record))
        selected_project_ids = (
            project_ids
            if project_ids is not None
            else [item["project_id"] for item in record.get("projects", []) if item.get("selected", True)]
        )
        selected_publication_ids = (
            publication_ids
            if publication_ids is not None
            else [item["publication_id"] for item in record.get("publications", []) if item.get("selected", True)]
        )
        selected_projects = self.context.packet_exporter._select_projects(master, selected_project_ids)
        proposed_rewrites = rewritten if rewritten is not None else self._default_rewritten_bullets(record)
        selected_projects = self.context.packet_exporter._apply_rewritten_bullets(selected_projects, proposed_rewrites)
        experience = self.context.packet_exporter._apply_rewritten_experience_bullets(
            master.get("experience", []),
            proposed_rewrites,
        )
        publications = self.context.packet_exporter._select_publications(
            master,
            jd_text=record["job"].get("page_text", ""),
            selected_projects=selected_projects,
            selected_publication_ids=selected_publication_ids,
            include_publications=bool(selected_publication_ids),
        )
        publications = self.context.packet_exporter._apply_rewritten_publication_bullets(
            publications,
            proposed_rewrites,
        )
        selected_projects = self.context.packet_exporter._limit_bullets(
            selected_projects,
            counts["projects_per_project"],
        )
        experience = self.context.packet_exporter._limit_bullets(
            experience,
            counts["experience_per_role"],
        )
        publications = self.context.packet_exporter._limit_bullets(
            publications,
            counts["research_per_paper"],
        )
        return self.context.packet_exporter.renderer.render_html_string(
            master.get("candidate", {}),
            selected_projects,
            summary_text=summary if summary is not None else (record.get("summary_proposed") or record.get("summary_original")),
            skills=master.get("skills", {}),
            experience=experience,
            education=master.get("education", []),
            publications=publications,
        )

    @staticmethod
    def _record_bullet_counts(record: dict[str, Any]) -> dict[str, int]:
        preferences = record.get("preferences") or {}
        counts = preferences.get("bullet_counts") if isinstance(preferences, dict) else {}
        return TailoringReviewService._coerce_bullet_counts(counts)

    @staticmethod
    def _coerce_bullet_counts(value: Any) -> dict[str, int]:
        data = value.model_dump() if hasattr(value, "model_dump") else value
        if not isinstance(data, dict):
            data = {}
        return {
            "experience_per_role": TailoringReviewService._clamp_int(data.get("experience_per_role", 3), 0, 50),
            "projects_per_project": TailoringReviewService._clamp_int(data.get("projects_per_project", 2), 0, 50),
            "research_per_paper": TailoringReviewService._clamp_int(data.get("research_per_paper", 2), 0, 50),
        }

    @staticmethod
    def _clamp_int(value: Any, low: int, high: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = low
        return max(low, min(high, parsed))

    @staticmethod
    def _default_rewritten_bullets(record: dict[str, Any]) -> list[dict[str, str]]:
        rewritten: list[dict[str, str]] = []
        for source in record.get("bullets", []):
            proposed = str(source.get("proposed") or "").strip()
            original = str(source.get("original") or "")
            if not proposed or not TailoringReviewService._acceptable_rewrite(original, proposed):
                continue
            section = str(source.get("section") or "")
            item_id = str(source.get("item_id") or "")
            rewritten.append(
                {
                    "section": section,
                    "item_id": item_id,
                    "project_id": item_id if section == "project" else "",
                    "experience_id": item_id if section == "experience" else "",
                    "publication_id": item_id if section in {"publication", "research", "research_paper"} else "",
                    "original": str(source.get("original") or ""),
                    "rewritten": proposed,
                }
            )
        return rewritten

    @staticmethod
    def _acceptable_rewrite(original: str, proposed: str) -> bool:
        if not ResumeQualityService._looks_like_xyz_bullet(proposed):
            return False
        if original.lower().startswith(("source evidence", "profile evidence")):
            return True
        original_numbers = ResumeQualityService._numbers_in_text(original)
        if not original_numbers:
            return True
        proposed_numbers = ResumeQualityService._numbers_in_text(proposed)
        return original_numbers.issubset(proposed_numbers)

    @staticmethod
    def _lookup_original(master: dict, section: str, item_id: str) -> str:
        if section in {"publication", "research", "research_paper"}:
            items = master.get("publications", [])
        else:
            items = master.get("projects", []) if section == "project" else master.get("experience", [])
        for item in items:
            candidate_id = str(
                item.get("id")
                or (
                    TailoringReviewService._publication_id(item)
                    if section in {"publication", "research", "research_paper"}
                    else TailoringReviewService._experience_id(item)
                )
            )
            if candidate_id == item_id:
                return str((item.get("bullets") or [""])[0])
        return ""

    @staticmethod
    def _item_label(master: dict, section: str, item_id: str) -> str:
        if section in {"publication", "research", "research_paper"}:
            items = master.get("publications", [])
        else:
            items = master.get("projects", []) if section == "project" else master.get("experience", [])
        for item in items:
            candidate_id = str(
                item.get("id")
                or (
                    TailoringReviewService._publication_id(item)
                    if section in {"publication", "research", "research_paper"}
                    else TailoringReviewService._experience_id(item)
                )
            )
            if candidate_id == item_id:
                return str(item.get("name") or item.get("title") or item_id)
        return item_id.replace("_", " ").title()

    @staticmethod
    def _experience_id(item: dict) -> str:
        raw = f"{item.get('title', '')}_{item.get('company', '')}".lower()
        return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")

    def _validate_edit(self, text: str, original: str, *, max_length: int = 700) -> None:
        if not text or len(text) > max_length:
            raise HTTPException(status_code=400, detail="Edited resume text is empty or too long.")
        profile_context = ProfileEvidenceService().build_prompt_context(max_chars=60000)
        master_text = self.master_resume_path.read_text(encoding="utf-8") + "\n" + str(profile_context)
        supported_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", master_text))
        unsupported = sorted(set(re.findall(r"\d+(?:\.\d+)?%?", text)) - supported_numbers)
        if unsupported:
            raise HTTPException(
                status_code=400,
                detail="Edited text contains unsupported metrics: " + ", ".join(unsupported),
            )
        if ProfileEvidenceService._sanitize(text) != text:
            raise HTTPException(status_code=400, detail="Edited text contains credential-like or secret content.")
        if not original and len(text.split()) > 80:
            raise HTTPException(status_code=400, detail="Edited text is too broad to verify against resume evidence.")

    def _master_resume(self) -> dict:
        return json.loads(self.master_resume_path.read_text(encoding="utf-8"))

    def _draft_path(self, draft_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", draft_id):
            raise HTTPException(status_code=400, detail="Invalid tailoring draft ID.")
        return self.draft_dir / f"{draft_id}.json"

    def _write_draft(self, record: dict[str, Any]) -> None:
        path = self._draft_path(record["draft_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, ensure_ascii=True), encoding="utf-8")

    def _read_draft(self, draft_id: str) -> dict[str, Any]:
        path = self._draft_path(draft_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Tailoring draft was not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def _audit(self, event: str, data: dict[str, Any]) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"event": event, "created_at": datetime.now(UTC).isoformat(), **data}
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
