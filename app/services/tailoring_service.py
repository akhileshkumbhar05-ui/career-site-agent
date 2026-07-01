import json
from pathlib import Path

from app.core.skill_mapper import normalize_skills
from app.schemas.resume import ResumeTailorRequest, ResumeTailorResponse


class TailoringService:
    def __init__(self) -> None:
        self.master_resume = self._load_json("data/master_resume/master_resume.json")
        self.role_profiles = self._load_json("data/master_resume/role_profiles.json")

    def tailor(self, payload: ResumeTailorRequest) -> ResumeTailorResponse:
        target_role = self._infer_role_key(payload.parsed_jd.title)
        role_profile = self.role_profiles.get(target_role, {})
        summary_variant_key = role_profile.get("summary_variant_key", target_role)
        summary_variant = self._select_summary_variant(summary_variant_key)

        if payload.current_score < 65:
            return ResumeTailorResponse(
                job_id=payload.job_id,
                resume_version=payload.resume_version,
                source_resume_version=payload.resume_version,
                tailored_resume_version=f"{payload.job_id}_not_tailored",
                changes_summary=[
                    "Rule-based tailoring skipped because the current match score is below the tailoring threshold."
                ],
                tailored_score=payload.current_score,
                selected_project_ids=[],
                summary_variant_key=summary_variant_key,
                summary_text="",
            )

        target_keywords = normalize_skills(
            payload.parsed_jd.required_skills
            + payload.parsed_jd.preferred_skills
            + payload.parsed_jd.keywords
        )

        ranked_projects = self._rank_projects(
            target_keywords=target_keywords,
            target_role=target_role,
            role_profile=role_profile,
        )
        selected_project_ids = (
            [project["id"] for project in ranked_projects[:3]]
            if "projects" in payload.preferences.emphasis
            else []
        )

        tailored_score = self._estimate_tailored_score(
            current_score=payload.current_score,
            selected_projects=ranked_projects[:3],
            target_keywords=target_keywords,
            role_profile=role_profile,
        )

        changes = self._build_changes_summary(
            target_role=target_role,
            summary_variant=summary_variant,
            selected_projects=selected_project_ids,
        )
        changes.insert(
            0,
            f"Tailoring preference: {payload.preferences.preset} with {payload.preferences.rewrite_intensity} edits.",
        )

        return ResumeTailorResponse(
            job_id=payload.job_id,
            resume_version=payload.resume_version,
            source_resume_version=payload.resume_version,
            tailored_resume_version=f"{payload.job_id}_tailored_v1",
            changes_summary=changes,
            tailored_score=tailored_score,
            selected_project_ids=selected_project_ids,
            summary_variant_key=summary_variant_key,
            summary_text=summary_variant if "summary" in payload.preferences.emphasis else "",
        )

    def _infer_role_key(self, title: str) -> str:
        lowered_title = title.lower()

        for role_key, profile in self.role_profiles.items():
            aliases = [alias.lower() for alias in profile.get("title_aliases", [])]
            if any(alias in lowered_title for alias in aliases):
                return role_key

        if any(token in lowered_title for token in ["ai engineer", "llm", "genai", "rag"]):
            return "ai_engineer"
        if any(token in lowered_title for token in ["computer vision", "vision engineer", "image processing"]):
            return "computer_vision_engineer"
        if any(token in lowered_title for token in ["software engineer", "python developer", "backend engineer"]):
            return "ai_software_engineer"
        if any(token in lowered_title for token in ["machine learning", "ml engineer", "research engineer", "computer vision"]):
            return "ml_engineer"
        if any(token in lowered_title for token in ["business analyst", "business intelligence", "bi analyst", "product analyst"]):
            return "business_analyst"
        if any(token in lowered_title for token in ["data analyst", "analytics analyst", "reporting analyst", "operations analyst"]):
            return "data_analyst"
        if any(token in lowered_title for token in ["data scientist", "analytics", "applied scientist"]):
            return "data_scientist"

        return "ml_engineer"

    def _rank_projects(
        self,
        target_keywords: list[str],
        target_role: str,
        role_profile: dict,
    ) -> list[dict]:
        ranked = []

        priority_tags = normalize_skills(role_profile.get("priority_tags", []))
        prefer_tags = normalize_skills(
            role_profile.get("project_priority_rules", {}).get("prefer_tags", [])
        )
        avoid_tags = normalize_skills(
            role_profile.get("project_priority_rules", {}).get("avoid_if_better_options_exist", [])
        )

        for project in self.master_resume.get("projects", []):
            tags = normalize_skills(project.get("tags", []))
            tech_stack = normalize_skills(project.get("tech_stack", []))
            role_fit = [role.lower() for role in project.get("role_fit", [])]

            project_terms = set(tags + tech_stack)

            keyword_overlap = len(project_terms.intersection(target_keywords))
            priority_overlap = len([tag for tag in priority_tags if tag in project_terms and tag in target_keywords])
            prefer_overlap = len([tag for tag in prefer_tags if tag in project_terms])
            role_bonus = 2 if target_role in role_fit else 0
            avoid_penalty = 1 if any(tag in project_terms for tag in avoid_tags) else 0

            total_score = keyword_overlap + (priority_overlap * 2) + prefer_overlap + role_bonus - avoid_penalty

            if total_score > 0:
                ranked.append(
                    {
                        "id": project["id"],
                        "score": total_score,
                        "name": project.get("name", ""),
                    }
                )

        ranked.sort(key=lambda item: item["score"], reverse=True)

        if not ranked:
            fallback = []
            for project in self.master_resume.get("projects", [])[:3]:
                fallback.append(
                    {
                        "id": project["id"],
                        "score": 0,
                        "name": project.get("name", ""),
                    }
                )
            return fallback

        return ranked

    def _select_summary_variant(self, summary_variant_key: str) -> str:
        variants = self.master_resume.get("summary_variants", {})
        return variants.get(summary_variant_key, self.master_resume.get("base_summary", ""))

    def _estimate_tailored_score(
        self,
        current_score: int,
        selected_projects: list[dict],
        target_keywords: list[str],
        role_profile: dict,
    ) -> int:
        if not selected_projects:
            return min(95, current_score + 3)

        overlap_signal = sum(project["score"] for project in selected_projects)
        priority_tags = normalize_skills(role_profile.get("priority_tags", []))
        priority_signal = len([tag for tag in priority_tags if tag in target_keywords])

        if current_score >= 85:
            lift = 2
        elif current_score >= 75:
            lift = 4 + min(5, (overlap_signal + priority_signal) // 3)
        elif current_score >= 65:
            lift = 6 + min(7, (overlap_signal + priority_signal) // 2)
        else:
            lift = 4 + min(5, (overlap_signal + priority_signal) // 2)

        return min(95, current_score + lift)

    def _build_changes_summary(
        self,
        target_role: str,
        summary_variant: str,
        selected_projects: list[str],
    ) -> list[str]:
        role_label = target_role.replace("_", " ").title()

        changes = [
            f"Selected the {role_label} summary variant to better align with job intent.",
            f"Reordered projects to prioritize the most relevant evidence: {', '.join(selected_projects)}.",
            "Planned bullet rewrites to use JD-aligned terminology without changing facts.",
        ]

        if summary_variant:
            changes.insert(
                1,
                "Updated the professional summary emphasis to better reflect relevant skills, project alignment, and deployment context.",
            )

        return changes

    @staticmethod
    def _load_json(path_str: str) -> dict:
        path = Path(path_str)
        return json.loads(path.read_text(encoding="utf-8"))
