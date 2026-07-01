import json
import re
import subprocess
import time
from datetime import date, datetime, UTC
from pathlib import Path

from app.schemas.application_packet import (
    ApplicationPacketExportRequest,
    ApplicationPacketExportResponse,
)
from app.services.resume_quality_service import ResumeQualityService
from app.services.resume_render_service import ResumeRenderService


class ApplicationPacketExportService:
    def __init__(
        self,
        master_resume_path: str = "data/master_resume/master_resume.json",
        renderer: ResumeRenderService | None = None,
        quality_service: ResumeQualityService | None = None,
    ) -> None:
        self.master_resume_path = Path(master_resume_path)
        self.renderer = renderer or ResumeRenderService()
        self.quality_service = quality_service or ResumeQualityService()

    def export(self, payload: ApplicationPacketExportRequest) -> ApplicationPacketExportResponse:
        packet = payload.application_packet
        master_resume = self._load_master_resume()

        company_folder, tailored_resume_path = self._resolve_output_paths(payload)
        packet_folder = company_folder / "application_packets" / f"{date.today().strftime('%Y%m%d')}_{packet.role_slug}"
        packet_folder.mkdir(parents=True, exist_ok=True)

        resume_docx_path = tailored_resume_path.with_suffix(".docx")
        resume_html_path = tailored_resume_path.with_suffix(".html")
        metadata_path = packet_folder / "application_packet.json"
        checklist_path = packet_folder / "form_fill_checklist.md"
        outreach_path = packet_folder / "recruiter_outreach.txt"
        jd_path = packet_folder / "job_description.txt"
        summary_path = packet_folder / "application_packet.md"
        apply_plan_path = packet_folder / "apply_plan.json"
        ats_answers_path = packet_folder / "ats_answer_bank.md"

        selected_projects = self._select_projects(
            master_resume,
            payload.selected_project_ids,
            fallback_to_top=payload.auto_select_projects,
        )
        selected_projects = self._apply_rewritten_bullets(selected_projects, payload.rewritten_bullets)
        experience = self._apply_rewritten_experience_bullets(
            master_resume.get("experience", []),
            payload.rewritten_bullets,
        )
        publications = self._select_publications(
            master_resume,
            jd_text=payload.jd_text,
            selected_projects=selected_projects,
            selected_publication_ids=payload.selected_publication_ids,
            include_publications=payload.include_publications,
        )
        publications = self._apply_rewritten_publication_bullets(publications, payload.rewritten_bullets)
        experience = self._limit_bullets(experience, payload.bullet_counts.experience_per_role)
        selected_projects = self._limit_bullets(selected_projects, payload.bullet_counts.projects_per_project)
        publications = self._limit_bullets(publications, payload.bullet_counts.research_per_paper)
        resume_skills = self._select_resume_skills(
            master_resume,
            payload=payload,
            selected_projects=selected_projects,
            experience=experience,
        )

        self.renderer.render_docx(
            str(resume_docx_path),
            master_resume.get("candidate", {}),
            selected_projects,
            summary_text=payload.summary_text,
            skills=resume_skills,
            experience=experience,
            education=master_resume.get("education", []),
            publications=publications,
        )

        self.renderer.render_html(
            str(resume_html_path),
            master_resume.get("candidate", {}),
            selected_projects,
            summary_text=payload.summary_text,
            skills=resume_skills,
            experience=experience,
            education=master_resume.get("education", []),
            publications=publications,
        )

        pdf_rendered = False
        pdf_error = ""
        pdf_path: str | None = None
        if payload.render_pdf:
            try:
                self._render_pdf_with_edge(resume_html_path, tailored_resume_path)
                pdf_rendered = True
                pdf_path = str(tailored_resume_path)
            except Exception as exc:
                pdf_error = str(exc)

        quality_passed, quality_checks = self.quality_service.validate(
            html_path=resume_html_path,
            pdf_path=Path(pdf_path) if pdf_path else None,
            master_resume=master_resume,
            rewritten_bullets=payload.rewritten_bullets,
        )

        metadata = {
            "created_at": datetime.now(UTC).isoformat(),
            "application_packet": packet.model_dump(),
            "effective_company_folder_path": str(company_folder),
            "effective_tailored_resume_path": str(tailored_resume_path),
            "effective_tailored_resume_docx_path": str(resume_docx_path),
            "output_root_override": payload.output_root_override,
            "selected_project_ids": payload.selected_project_ids,
            "selected_publication_ids": payload.selected_publication_ids,
            "bullet_counts": payload.bullet_counts.model_dump(),
            "selected_publications": publications,
            "selected_skills": resume_skills,
            "changes_summary": payload.changes_summary,
            "summary_text": payload.summary_text,
            "rewritten_bullets": payload.rewritten_bullets,
            "quality_passed": quality_passed,
            "quality_checks": quality_checks,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        apply_plan = self._build_apply_plan(payload)
        apply_plan["resume"]["tailored_resume_path"] = str(resume_docx_path)
        apply_plan["resume"]["tailored_resume_docx_path"] = str(resume_docx_path)
        apply_plan["resume"]["tailored_resume_html_path"] = str(resume_html_path)
        apply_plan["resume"]["intended_tailored_resume_pdf_path"] = str(tailored_resume_path)
        apply_plan["resume"]["tailored_resume_pdf_path"] = pdf_path or ""
        apply_plan_path.write_text(json.dumps(apply_plan, indent=2), encoding="utf-8")
        ats_answers_path.write_text(self._build_ats_answers(payload), encoding="utf-8")
        checklist_path.write_text(self._build_checklist(payload), encoding="utf-8")
        outreach_path.write_text(self._build_outreach(payload), encoding="utf-8")
        jd_path.write_text(payload.jd_text or "No job description text was provided.", encoding="utf-8")
        summary_path.write_text(self._build_summary(payload, selected_projects), encoding="utf-8")

        files = [
            str(resume_docx_path),
            str(resume_html_path),
            str(metadata_path),
            str(apply_plan_path),
            str(ats_answers_path),
            str(checklist_path),
            str(outreach_path),
            str(jd_path),
            str(summary_path),
        ]
        if pdf_path:
            files.insert(1, pdf_path)

        return ApplicationPacketExportResponse(
            company_folder_path=str(company_folder),
            packet_folder_path=str(packet_folder),
            tailored_resume_docx_path=str(resume_docx_path),
            tailored_resume_html_path=str(resume_html_path),
            intended_tailored_resume_pdf_path=str(tailored_resume_path),
            tailored_resume_pdf_path=pdf_path,
            pdf_rendered=pdf_rendered,
            pdf_error=pdf_error,
            quality_passed=quality_passed,
            quality_checks=quality_checks,
            metadata_path=str(metadata_path),
            checklist_path=str(checklist_path),
            outreach_path=str(outreach_path),
            jd_path=str(jd_path),
            apply_plan_path=str(apply_plan_path),
            ats_answers_path=str(ats_answers_path),
            files_written=files,
        )

    def _select_projects(
        self,
        master_resume: dict,
        selected_ids: list[str],
        *,
        fallback_to_top: bool = False,
    ) -> list[dict]:
        projects = master_resume.get("projects", [])
        if not selected_ids:
            # Automated paths auto-pick the top projects; the review flow passes
            # fallback_to_top=False so an explicit deselect-all renders no projects section.
            return projects[:3] if fallback_to_top else []

        by_id = {project.get("id"): project for project in projects}
        selected = [by_id[item] for item in selected_ids if item in by_id]
        return selected or projects[:3]

    def _resolve_output_paths(self, payload: ApplicationPacketExportRequest) -> tuple[Path, Path]:
        packet = payload.application_packet
        if not payload.output_root_override:
            return Path(packet.company_folder_path), Path(packet.tailored_resume_path)

        output_root = Path(payload.output_root_override)
        company_folder = output_root / self._sanitize_folder_name(packet.company)
        original_resume_name = Path(packet.tailored_resume_path).name
        if not original_resume_name or original_resume_name == ".":
            original_resume_name = f"Akhilesh_Kumbhar_{packet.company}_{packet.role_slug}.pdf"
        return company_folder, company_folder / original_resume_name

    @staticmethod
    def _apply_rewritten_bullets(projects: list[dict], rewritten_bullets: list[dict]) -> list[dict]:
        if not rewritten_bullets:
            return projects

        rewritten_by_project: dict[str, list[str]] = {}
        for item in rewritten_bullets:
            if str(item.get("section") or "").lower() == "experience":
                continue
            project_id = item.get("project_id") or item.get("item_id")
            rewritten = item.get("rewritten")
            if project_id and rewritten:
                rewritten_by_project.setdefault(project_id, []).append(rewritten)

        updated_projects = []
        for project in projects:
            copy = dict(project)
            rewritten = rewritten_by_project.get(project.get("id"))
            if rewritten:
                copy["bullets"] = ApplicationPacketExportService._merge_bullets(
                    rewritten,
                    project.get("bullets", []),
                )
            updated_projects.append(copy)

        return updated_projects

    @staticmethod
    def _apply_rewritten_experience_bullets(experience: list[dict], rewritten_bullets: list[dict]) -> list[dict]:
        if not rewritten_bullets:
            return experience

        rewritten_by_item: dict[str, list[str]] = {}
        for item in rewritten_bullets:
            section = str(item.get("section") or "").lower()
            item_id = str(item.get("experience_id") or item.get("item_id") or "")
            rewritten = item.get("rewritten")
            if section == "experience" and item_id and rewritten:
                rewritten_by_item.setdefault(item_id, []).append(rewritten)

        updated_experience = []
        for item in experience:
            copy = dict(item)
            candidates = {
                ApplicationPacketExportService._item_key(item.get("title", ""), item.get("company", "")),
                ApplicationPacketExportService._item_key(item.get("company", ""), item.get("title", "")),
                str(item.get("company", "")),
                str(item.get("title", "")),
            }
            rewritten = []
            for key in candidates:
                rewritten.extend(rewritten_by_item.get(key, []))
            if rewritten:
                copy["bullets"] = ApplicationPacketExportService._merge_bullets(
                    rewritten,
                    item.get("bullets", []),
                )
            updated_experience.append(copy)

        return updated_experience

    @staticmethod
    def _apply_rewritten_publication_bullets(publications: list[dict], rewritten_bullets: list[dict]) -> list[dict]:
        if not rewritten_bullets:
            return publications

        rewritten_by_item: dict[str, list[str]] = {}
        for item in rewritten_bullets:
            section = str(item.get("section") or "").lower()
            if section not in {"publication", "research", "research_paper"}:
                continue
            item_id = str(item.get("publication_id") or item.get("item_id") or "")
            rewritten = item.get("rewritten")
            if item_id and rewritten:
                rewritten_by_item.setdefault(item_id, []).append(rewritten)

        updated_publications = []
        for item in publications:
            copy = dict(item)
            candidates = {
                ApplicationPacketExportService._publication_id(item),
                ApplicationPacketExportService._item_key(item.get("title", "")),
                ApplicationPacketExportService._item_key(item.get("title", ""), item.get("venue", "")),
                str(item.get("title", "")),
                str(item.get("venue", "")),
            }
            rewritten = []
            for key in candidates:
                rewritten.extend(rewritten_by_item.get(key, []))
            if rewritten:
                copy["bullets"] = ApplicationPacketExportService._merge_bullets(
                    rewritten,
                    item.get("bullets", []),
                )
            updated_publications.append(copy)

        return updated_publications

    @staticmethod
    def _merge_bullets(preferred: list[str], originals: list[str], *, limit: int | None = None) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for bullet in [*preferred, *originals]:
            text = str(bullet or "").strip()
            if not text:
                continue
            key = ApplicationPacketExportService._normalize_match_text(text)
            if key in seen:
                continue
            seen.add(key)
            merged.append(text)
            if limit is not None and len(merged) >= limit:
                break
        return merged

    @staticmethod
    def _limit_bullets(items: list[dict], limit: int) -> list[dict]:
        limited = []
        for item in items:
            copy = dict(item)
            copy["bullets"] = list(copy.get("bullets") or [])[: max(0, int(limit))]
            limited.append(copy)
        return limited

    @staticmethod
    def _select_resume_skills(
        master_resume: dict,
        *,
        payload: ApplicationPacketExportRequest,
        selected_projects: list[dict],
        experience: list[dict],
    ) -> dict:
        skills = master_resume.get("skills", {})
        if not isinstance(skills, dict):
            return {}

        packet = payload.application_packet
        jd_text = " ".join(
            [
                payload.jd_text or "",
                payload.summary_text or "",
                packet.role or "",
                packet.target_role_key or "",
                " ".join(payload.changes_summary or []),
                " ".join(str(item.get("rewritten") or "") for item in payload.rewritten_bullets or []),
            ]
        )
        evidence_text = ApplicationPacketExportService._normalize_match_text(jd_text)
        role_key = str(packet.target_role_key or packet.role or "").lower()
        role_defaults = ApplicationPacketExportService._role_default_skills(role_key)
        hard_limits = {
            "programming_languages": 3,
            "machine_learning_and_ai": 5,
            "generative_ai_and_llms": 4,
            "data_and_analytics": 7,
            "cloud_and_deployment": 4,
            "automation_and_tools": 4,
        }

        selected: dict[str, list[str]] = {}
        for group, values in skills.items():
            if not isinstance(values, list):
                continue
            group_values = []
            for skill in values:
                skill_text = str(skill or "").strip()
                if not skill_text:
                    continue
                normalized_skill = ApplicationPacketExportService._normalize_match_text(skill_text)
                if normalized_skill in role_defaults or ApplicationPacketExportService._skill_in_text(
                    normalized_skill,
                    evidence_text,
                ):
                    group_values.append(skill_text)
            if group_values:
                selected[group] = group_values[: hard_limits.get(group, 5)]

        selected = ApplicationPacketExportService._ensure_core_resume_skills(selected, skills, role_defaults)
        selected = ApplicationPacketExportService._include_project_anchor_skills(
            selected,
            skills,
            selected_projects=selected_projects,
            evidence_text=evidence_text,
        )
        selected = ApplicationPacketExportService._include_experience_anchor_skills(
            selected,
            skills,
            experience=experience,
            evidence_text=evidence_text,
        )

        return {
            group: values
            for group, values in selected.items()
            if values
        }

    @staticmethod
    def _role_default_skills(role_key: str) -> set[str]:
        defaults = {"python", "sql"}
        if any(token in role_key for token in ["business_analyst", "business analyst", "data_analyst", "data analyst", "analytics"]):
            defaults.update(
                {
                    "pandas",
                    "numpy",
                    "power bi",
                    "streamlit",
                    "ms excel",
                    "excel",
                    "google sheets",
                    "matplotlib",
                    "seaborn",
                }
            )
        if any(token in role_key for token in ["data_scientist", "data scientist", "machine learning", "ml_engineer", "ml engineer"]):
            defaults.update({"machine learning", "scikit learn", "scikit-learn", "feature engineering", "model evaluation"})
        if any(token in role_key for token in ["ai_engineer", "ai engineer", "ai_software", "software engineer ai"]):
            defaults.update({"fastapi", "rag pipelines", "langchain", "agentic workflows"})
        if any(token in role_key for token in ["computer_vision", "computer vision", "cv engineer"]):
            defaults.update({"computer vision", "opencv", "yolov8", "pytorch", "tensorflow"})
        return defaults

    @staticmethod
    def _ensure_core_resume_skills(selected: dict, all_skills: dict, role_defaults: set[str]) -> dict:
        for group, values in all_skills.items():
            if not isinstance(values, list):
                continue
            for skill in values:
                normalized = ApplicationPacketExportService._normalize_match_text(skill)
                if normalized in role_defaults:
                    selected.setdefault(group, [])
                    if skill not in selected[group]:
                        selected[group].append(skill)
        return selected

    @staticmethod
    def _include_project_anchor_skills(
        selected: dict,
        all_skills: dict,
        *,
        selected_projects: list[dict],
        evidence_text: str,
    ) -> dict:
        project_text = ApplicationPacketExportService._normalize_match_text(
            " ".join(
                " ".join(str(bullet) for bullet in project.get("bullets", []))
                for project in selected_projects
            )
        )
        if not project_text:
            return selected
        for group, values in all_skills.items():
            if not isinstance(values, list):
                continue
            for skill in values:
                normalized = ApplicationPacketExportService._normalize_match_text(skill)
                if (
                    ApplicationPacketExportService._skill_in_text(normalized, evidence_text)
                    and ApplicationPacketExportService._skill_in_text(normalized, project_text)
                ):
                    selected.setdefault(group, [])
                    if skill not in selected[group]:
                        selected[group].append(skill)
        return selected

    @staticmethod
    def _include_experience_anchor_skills(
        selected: dict,
        all_skills: dict,
        *,
        experience: list[dict],
        evidence_text: str,
    ) -> dict:
        experience_skills = {
            ApplicationPacketExportService._normalize_match_text(skill)
            for item in experience
            for skill in item.get("skills_used", [])
        }
        for group, values in all_skills.items():
            if not isinstance(values, list):
                continue
            for skill in values:
                normalized = ApplicationPacketExportService._normalize_match_text(skill)
                if normalized in experience_skills and ApplicationPacketExportService._skill_in_text(normalized, evidence_text):
                    selected.setdefault(group, [])
                    if skill not in selected[group]:
                        selected[group].append(skill)
        return selected

    @staticmethod
    def _skill_in_text(normalized_skill: str, normalized_text: str) -> bool:
        if not normalized_skill or not normalized_text:
            return False
        aliases = {
            "ms excel": ["excel", "microsoft excel"],
            "power bi": ["powerbi", "power bi"],
            "scikit learn": ["scikit learn", "scikit-learn", "sklearn"],
            "scikit-learn": ["scikit learn", "scikit-learn", "sklearn"],
            "rag pipelines": ["rag", "retrieval augmented generation"],
            "aws ec2": ["aws", "ec2", "aws ec2"],
        }.get(normalized_skill, [normalized_skill])
        return any(re.search(rf"\b{re.escape(alias)}\b", normalized_text) for alias in aliases)

    @staticmethod
    def _normalize_match_text(value: object) -> str:
        text = str(value or "").lower()
        text = text.replace("&", " and ")
        text = re.sub(r"[^a-z0-9+#.]+", " ", text)
        return " ".join(text.split())

    @staticmethod
    def _select_publications(
        master_resume: dict,
        *,
        jd_text: str,
        selected_projects: list[dict],
        selected_publication_ids: list[str] | None = None,
        include_publications: bool = False,
    ) -> list[dict]:
        publications = master_resume.get("publications", [])
        if selected_publication_ids:
            by_id = {
                ApplicationPacketExportService._publication_id(item): item
                for item in publications
            }
            return [by_id[item] for item in selected_publication_ids[:2] if item in by_id]
        if include_publications:
            return publications[:2]

        text = jd_text.lower()
        energy_match = any(
            re.search(pattern, text)
            for pattern in [
                r"\belectric vehicle(s)?\b",
                r"\bev\b",
                r"\berev\b",
                r"\benergy\b",
                r"\bsustainability\b",
                r"\bemissions\b",
                r"\btransportation\b",
            ]
        )
        health_match = any(
            re.search(pattern, text)
            for pattern in [
                r"\bhealthcare\b",
                r"\bhealth care\b",
                r"\bbioinformatics\b",
                r"\bbiotech\b",
                r"\bmedical\b",
                r"\bclinical\b",
                r"\bdisease\b",
            ]
        )
        research_match = any(
            re.search(pattern, text)
            for pattern in [
                r"\bresearch scientist\b",
                r"\bresearch engineer\b",
                r"\bpublished\b",
                r"\bpublication\b",
                r"\bpeer reviewed\b",
            ]
        )
        selected = []
        for item in publications:
            title = str(item.get("title") or "").lower()
            venue = str(item.get("venue") or "").lower()
            if energy_match:
                if "electric vehicles" in title or "energies" in venue:
                    selected.append(item)
            if health_match:
                if "healthcare" in title or "ictcs" in venue:
                    selected.append(item)
            if research_match and item not in selected:
                selected.append(item)
        return selected[:2]

    @staticmethod
    def _publication_id(item: dict) -> str:
        if item.get("id"):
            return str(item.get("id"))
        raw = f"{item.get('title', '')}_{item.get('venue', '')}_{item.get('year', '')}".lower()
        return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")[:96]

    @staticmethod
    def _item_key(*parts: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", "_".join(parts).lower()).strip("_")

    @staticmethod
    def _sanitize_folder_name(value: str) -> str:
        cleaned = "".join(" " if char in '<>:"/\\|?*' else char for char in value).strip()
        return " ".join(cleaned.split()) or "Unknown Company"

    @staticmethod
    def _build_checklist(payload: ApplicationPacketExportRequest) -> str:
        packet = payload.application_packet
        candidate = packet.prefill_profile.get("candidate", {})
        work_auth = packet.prefill_profile.get("work_authorization", {})
        preferences = packet.prefill_profile.get("preferences", {})
        ats = packet.ats_answer_bank
        ats_work_auth = ats.get("work_authorization", {})

        lines = [
            f"# Form Fill Checklist - {packet.company}",
            "",
            f"- Role: {packet.role}",
            f"- Official URL: {packet.official_url}",
            f"- Base resume PDF: {packet.base_resume_pdf}",
            f"- Tailored resume DOCX: {Path(packet.tailored_resume_path).with_suffix('.docx')}",
            f"- Tailored resume PDF preview: {packet.tailored_resume_path}",
            "",
            "## Candidate",
            f"- Full name: {candidate.get('full_name', '')}",
            f"- Email: {candidate.get('email', '')}",
            f"- Phone: {candidate.get('phone', '')}",
            f"- Location: {candidate.get('city', '')}, {candidate.get('state', '')}, {candidate.get('country', '')}",
            f"- LinkedIn: {ApplicationPacketExportService._profile_link(candidate, 'linkedin')}",
            f"- GitHub: {ApplicationPacketExportService._profile_link(candidate, 'github')}",
            "",
            "## Work Authorization",
            f"- Authorized to work in the United States now: {work_auth.get('authorized_to_work_in_united_states')}",
            f"- Current status: {work_auth.get('current_status', '')}",
            f"- Requires current sponsorship: {work_auth.get('requires_current_sponsorship')}",
            f"- Requires future sponsorship: {work_auth.get('requires_future_sponsorship')}",
            f"- Standard explanation: {work_auth.get('standard_explanation', '')}",
            "",
            "## Preferences",
            f"- Willing to relocate: {preferences.get('willing_to_relocate')}",
            f"- Salary filter enabled: {preferences.get('salary_filter_enabled')}",
            f"- Target level: {preferences.get('target_level', '')}",
            "",
            "## Common ATS Answers",
            f"- Authorized to work in the United States now: {ats_work_auth.get('authorized_to_work_us_now', '')}",
            f"- Requires sponsorship now: {ats_work_auth.get('requires_sponsorship_now', '')}",
            f"- Requires sponsorship in the future: {ats_work_auth.get('requires_sponsorship_future', '')}",
            f"- Visa/status explanation: {ats_work_auth.get('standard_explanation', '')}",
            "",
            "## Application Steps",
        ]
        for step in packet.application_steps:
            lines.append(f"- {step.get('step', '')}: {step.get('description', '')}")

        lines.extend([
            "",
            "## Recruiter Search Targets",
        ])
        for search in packet.recruiter_searches:
            lines.append(f"- {search.get('label', '')}: {search.get('url', '')}")

        lines.extend([
            "",
            "## Human Review",
            f"- {packet.human_control_note}",
        ])
        return "\n".join(lines) + "\n"

    @staticmethod
    def _profile_link(candidate: dict, key: str) -> str:
        return str(candidate.get(f"{key}_url") or candidate.get(key) or "")

    @staticmethod
    def _build_outreach(payload: ApplicationPacketExportRequest) -> str:
        if payload.recruiter_subject or payload.recruiter_body:
            body = f"Subject: {payload.recruiter_subject}\n\n{payload.recruiter_body}".strip()
            note = payload.connection_note or ApplicationPacketExportService._default_connection_note(
                payload.application_packet
            )
            body += f"\n\nLinkedIn connection note:\n{note[:299]}"
            return body + "\n"

        packet = payload.application_packet
        note = payload.connection_note or ApplicationPacketExportService._default_connection_note(packet)
        searches = "\n".join(
            f"- {item.get('label', '')}: {item.get('url', '')}"
            for item in packet.recruiter_searches
        )
        return (
            f"Subject: Interest in {packet.role} at {packet.company}\n\n"
            "LinkedIn connection note:\n"
            f"{note[:299]}\n\n"
            "Longer recruiter message:\n"
            "Hi,\n\n"
            f"I came across the {packet.role} role at {packet.company} and wanted to reach out. "
            "My background includes applied machine learning, analytics, RAG workflows, and deployment-focused AI systems. "
            "I would value the opportunity to learn what the team is looking for in strong candidates.\n\n"
            "Best regards,\n"
            "Akhilesh Kumbhar\n\n"
            "Search targets:\n"
            f"{searches}\n"
        )

    @staticmethod
    def _build_summary(payload: ApplicationPacketExportRequest, selected_projects: list[dict]) -> str:
        packet = payload.application_packet
        lines = [
            f"# Application Packet - {packet.company}",
            "",
            f"- Job ID: {packet.job_id or 'N/A'}",
            f"- Role: {packet.role}",
            f"- Decision: {packet.decision}",
            f"- Reason: {packet.decision_reason}",
            f"- Base score: {packet.base_score}",
            f"- Tailored score: {packet.tailored_score if packet.tailored_score is not None else 'N/A'}",
            f"- Official URL: {packet.official_url}",
            f"- Source: {packet.source or 'N/A'}",
            f"- Location: {packet.location or 'N/A'}",
            f"- Target role key: {packet.target_role_key or 'N/A'}",
            f"- Company folder: {packet.company_folder_path}",
            f"- Tailored resume DOCX path: {Path(packet.tailored_resume_path).with_suffix('.docx')}",
            f"- Intended resume PDF path: {packet.tailored_resume_path}",
            "",
            "## Selected Projects",
        ]

        for project in selected_projects:
            lines.append(f"- {project.get('name', project.get('id', 'Unknown project'))}")

        if payload.changes_summary:
            lines.extend(["", "## Tailoring Notes"])
            lines.extend(f"- {item}" for item in payload.changes_summary)

        return "\n".join(lines) + "\n"

    @staticmethod
    def _build_ats_answers(payload: ApplicationPacketExportRequest) -> str:
        packet = payload.application_packet
        answer_bank = packet.ats_answer_bank
        lines = [
            f"# ATS Answer Bank - {packet.company}",
            "",
            "Use these answers to prefill common ATS fields. Final review stays manual.",
            "",
        ]

        for section, values in answer_bank.items():
            lines.extend([f"## {section.replace('_', ' ').title()}"])
            if isinstance(values, dict):
                for key, value in values.items():
                    lines.append(f"- {key.replace('_', ' ').title()}: {value}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _build_apply_plan(payload: ApplicationPacketExportRequest) -> dict:
        packet = payload.application_packet
        return {
            "job": {
                "job_id": packet.job_id,
                "company": packet.company,
                "role": packet.role,
                "official_url": packet.official_url,
                "source": packet.source,
                "posted_at": packet.posted_at,
                "location": packet.location,
            },
            "decision": {
                "decision": packet.decision,
                "reason": packet.decision_reason,
                "base_score": packet.base_score,
                "tailored_score": packet.tailored_score,
                "target_role_key": packet.target_role_key,
            },
            "resume": {
                "base_resume_pdf": packet.base_resume_pdf,
                "tailored_resume_path": packet.tailored_resume_path,
                "tailored_resume_docx_path": str(Path(packet.tailored_resume_path).with_suffix(".docx")),
                "selected_project_ids": payload.selected_project_ids,
                "bullet_counts": payload.bullet_counts.model_dump(),
                "summary_text": payload.summary_text,
                "rewritten_bullets": payload.rewritten_bullets,
                "changes_summary": payload.changes_summary,
            },
            "ats_answer_bank": packet.ats_answer_bank,
            "application_steps": packet.application_steps,
            "recruiter_outreach": {
                "connection_note": (payload.connection_note or ApplicationPacketExportService._default_connection_note(packet))[:299],
                "searches": packet.recruiter_searches,
            },
            "human_control": {
                "allow_final_submit": False,
                "note": packet.human_control_note,
            },
        }

    @staticmethod
    def _default_connection_note(packet) -> str:
        return (
            f"Hi, I’m interested in the {packet.role} role at {packet.company}. "
            "My background spans data science, ML, Python, and deployment-focused AI systems. "
            "I’d appreciate connecting."
        )

    def _load_master_resume(self) -> dict:
        return json.loads(self.master_resume_path.read_text(encoding="utf-8"))

    @staticmethod
    def _render_pdf_with_edge(html_path: Path, pdf_path: Path) -> None:
        edge_candidates = [
            Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        ]
        edge_path = next((path for path in edge_candidates if path.exists()), None)
        if edge_path is None:
            raise RuntimeError("Microsoft Edge was not found for headless PDF rendering.")

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_output_path = pdf_path.resolve()
        command = [
            str(edge_path),
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={pdf_output_path}",
            html_path.resolve().as_uri(),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Unknown Edge PDF rendering error").strip()
            raise RuntimeError(detail)
        if not ApplicationPacketExportService._wait_for_pdf(pdf_output_path):
            detail = (result.stderr or result.stdout or "Edge finished without creating the PDF file.").strip()
            raise RuntimeError(detail)

    @staticmethod
    def _wait_for_pdf(pdf_path: Path, timeout_seconds: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout_seconds
        last_size = -1
        stable_reads = 0

        while time.monotonic() < deadline:
            if pdf_path.exists():
                size = pdf_path.stat().st_size
                if size > 1024 and size == last_size:
                    stable_reads += 1
                    if stable_reads >= 2:
                        return True
                else:
                    stable_reads = 0
                    last_size = size
            time.sleep(0.2)

        return False
