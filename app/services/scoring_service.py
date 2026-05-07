import json
from pathlib import Path

from app.core.score_calculator import weighted_score
from app.core.skill_mapper import normalize_skills
from app.schemas.resume import ResumeScoreRequest, ResumeScoreResponse


class ScoringService:
    def __init__(self) -> None:
        self.master_resume = self._load_json("data/master_resume/master_resume.json")
        self.role_profiles = self._load_json("data/master_resume/role_profiles.json")

    def score(self, payload: ResumeScoreRequest) -> ResumeScoreResponse:
        resume_skills = self._flatten_resume_skills()
        resume_project_tags = self._flatten_project_tags()

        jd_required = normalize_skills(payload.parsed_jd.required_skills)
        jd_preferred = normalize_skills(payload.parsed_jd.preferred_skills)
        jd_keywords = normalize_skills(payload.parsed_jd.keywords)
        jd_constraints = [c.lower() for c in payload.parsed_jd.constraints]

        role_key = self._infer_role_key(payload.parsed_jd.title)
        role_profile = self.role_profiles.get(role_key, {})

        matched_required = [skill for skill in jd_required if skill in resume_skills]
        matched_preferred = [skill for skill in jd_preferred if skill in resume_skills]
        missing_items = [skill for skill in jd_required if skill not in resume_skills]

        required_score = self._ratio_score(len(matched_required), len(jd_required))
        preferred_score = self._ratio_score(len(matched_preferred), len(jd_preferred))
        experience_score = self._experience_score(jd_keywords, resume_project_tags, role_profile)
        education_score = self._education_score(payload.parsed_jd.education)
        domain_score = self._domain_score(payload.parsed_jd.title, jd_keywords, resume_skills, role_key, role_profile)
        constraints_score = self._constraints_score(jd_constraints)

        overall = weighted_score(
            required_skills_score=required_score,
            preferred_skills_score=preferred_score,
            experience_score=experience_score,
            education_score=education_score,
            domain_score=domain_score,
            constraints_score=constraints_score,
        )

        recommendation = (
            "apply_now" if overall >= 85
            else "tailor_resume" if overall >= 65
            else "manual_review"
        )

        return ResumeScoreResponse(
            job_id=payload.job_id,
            resume_version=payload.resume_version,
            overall_score=overall,
            required_skills_score=required_score,
            preferred_skills_score=preferred_score,
            experience_score=experience_score,
            education_score=education_score,
            domain_score=domain_score,
            constraints_score=constraints_score,
            missing_items=missing_items,
            matched_skills=sorted(set(matched_required + matched_preferred)),
            recommendation=recommendation,
        )

    @staticmethod
    def _ratio_score(matched: int, total: int) -> int:
        if total <= 0:
            return 80
        return round((matched / total) * 100)

    def _infer_role_key(self, title: str) -> str:
        lowered_title = title.lower()

        for role_key, profile in self.role_profiles.items():
            aliases = [alias.lower() for alias in profile.get("title_aliases", [])]
            if any(alias in lowered_title for alias in aliases):
                return role_key

        if any(token in lowered_title for token in ["ai engineer", "llm", "genai", "rag"]):
            return "ai_engineer"
        if any(token in lowered_title for token in ["machine learning", "ml engineer", "research engineer", "computer vision"]):
            return "ml_engineer"
        if any(token in lowered_title for token in ["data scientist", "analytics", "applied scientist"]):
            return "data_scientist"

        return "ml_engineer"

    def _experience_score(
        self,
        jd_keywords: list[str],
        resume_project_tags: set[str],
        role_profile: dict,
    ) -> int:
        if not jd_keywords:
            return 75

        priority_tags = normalize_skills(role_profile.get("priority_tags", []))
        prefer_tags = normalize_skills(
            role_profile.get("project_priority_rules", {}).get("prefer_tags", [])
        )

        total_overlap = len([key for key in jd_keywords if key in resume_project_tags])
        priority_overlap = len([tag for tag in priority_tags if tag in resume_project_tags and tag in jd_keywords])
        prefer_overlap = len([tag for tag in prefer_tags if tag in resume_project_tags and tag in jd_keywords])

        score = 55 + (total_overlap * 6) + (priority_overlap * 5) + (prefer_overlap * 3)
        return min(95, score)

    def _education_score(self, jd_education: str | None) -> int:
        resume_education = [edu.get("degree", "").lower() for edu in self.master_resume.get("education", [])]

        has_masters = any("master" in degree for degree in resume_education)
        has_bachelors = any("bachelor" in degree for degree in resume_education)

        if not jd_education:
            return 85
        if jd_education == "phd":
            return 60
        if jd_education == "master's":
            return 95 if has_masters else 75
        if jd_education == "bachelor's":
            return 95 if has_bachelors or has_masters else 70
        return 80

    def _domain_score(
        self,
        title: str,
        jd_keywords: list[str],
        resume_skills: set[str],
        role_key: str,
        role_profile: dict,
    ) -> int:
        lowered_title = title.lower()

        title_aliases = [alias.lower() for alias in role_profile.get("title_aliases", [])]
        priority_skills = normalize_skills(role_profile.get("priority_skills", []))
        preferred_skills = normalize_skills(role_profile.get("preferred_skills", []))
        priority_tags = normalize_skills(role_profile.get("priority_tags", []))

        title_score = 72
        if any(alias in lowered_title for alias in title_aliases):
            title_score = 88

        priority_skill_overlap = len([skill for skill in priority_skills if skill in resume_skills and skill in jd_keywords])
        preferred_skill_overlap = len([skill for skill in preferred_skills if skill in resume_skills and skill in jd_keywords])
        priority_tag_overlap = len([tag for tag in priority_tags if tag in jd_keywords])

        role_bonus = 0
        if role_key in {"data_scientist", "ml_engineer", "ai_engineer"}:
            role_bonus = 2

        score = (
            title_score
            + (priority_skill_overlap * 2)
            + preferred_skill_overlap
            + priority_tag_overlap
            + role_bonus
        )

        return min(95, score)

    def _constraints_score(self, jd_constraints: list[str]) -> int:
        if not jd_constraints:
            return 95

        negative_hits = 0
        for item in jd_constraints:
            if item in {"visa", "sponsorship", "authorized to work", "work authorization"}:
                negative_hits += 1

        return max(70, 100 - negative_hits * 10)

    def _flatten_resume_skills(self) -> set[str]:
        skills = set()

        for value in self.master_resume.get("skills", {}).values():
            for item in value:
                skills.add(item.lower())

        for project in self.master_resume.get("projects", []):
            for tag in project.get("tags", []):
                skills.add(tag.lower())
            for tech in project.get("tech_stack", []):
                skills.add(tech.lower())

        for experience in self.master_resume.get("experience", []):
            for skill in experience.get("skills_used", []):
                skills.add(skill.lower())

        return set(normalize_skills(list(skills)))

    def _flatten_project_tags(self) -> set[str]:
        tags = set()
        for project in self.master_resume.get("projects", []):
            for tag in project.get("tags", []):
                tags.add(tag.lower())
        return set(normalize_skills(list(tags)))

    @staticmethod
    def _load_json(path_str: str) -> dict:
        path = Path(path_str)
        return json.loads(path.read_text(encoding="utf-8"))