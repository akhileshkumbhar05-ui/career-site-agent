from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import anthropic
except ImportError:  # pragma: no cover - optional runtime dependency
    anthropic = None

from app.config import settings
from app.schemas.job import JDParseRequest, JobQualityGateRequest
from app.schemas.resume import ResumeScoreRequest
from app.services.jd_parser_service import JDParserService
from app.services.job_quality_gate_service import JobQualityGateService
from app.services.llm_service import LLMService
from app.services.scoring_service import ScoringService

logger = logging.getLogger(__name__)


class LLMMatchService:
    """Scores job fit with an LLM when available and a deterministic fallback otherwise."""

    def __init__(
        self,
        *,
        parser: JDParserService,
        scorer: ScoringService,
        quality_gate: JobQualityGateService,
        cache_dir: str = "data/cache/llm_match",
        resume_path: str = "data/master_resume/master_resume.json",
    ) -> None:
        self.parser = parser
        self.scorer = scorer
        self.quality_gate = quality_gate
        self.cache_dir = Path(cache_dir)
        self.resume_path = Path(resume_path)
        self.ollama = LLMService()

    def analyze(self, job: dict[str, Any], *, use_llm: bool = True) -> dict[str, Any]:
        prepared = self._prepare_job(job)
        deterministic = self._deterministic_analysis(prepared)

        if not use_llm:
            return deterministic

        cache_path = self._cache_path(prepared)
        if cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                return self._sanitize_analysis(prepared, deterministic, payload) if isinstance(payload, dict) else deterministic
            except json.JSONDecodeError:
                pass

        llm_result = self._call_llm(prepared, deterministic)
        if not llm_result:
            return deterministic

        merged = self._merge_llm_result(prepared, deterministic, llm_result)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        return merged

    def cached_analysis(self, job: dict[str, Any]) -> dict[str, Any] | None:
        prepared = self._prepare_job(job)
        deterministic = self._deterministic_analysis(prepared)
        if self._hard_blockers(deterministic["risks"]):
            return deterministic

        cache_path = self._cache_path(prepared)
        if not cache_path.exists():
            return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return self._sanitize_analysis(prepared, deterministic, payload) if isinstance(payload, dict) else None

    def _prepare_job(self, job: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(job)
        prepared["job_id"] = str(job.get("job_id") or self._stable_job_id(job))
        prepared["company"] = str(job.get("company") or "Unknown Company")
        prepared["title"] = str(job.get("title") or "Untitled Role")
        prepared["jd_text"] = str(job.get("jd_text") or "")
        prepared["discovered_url"] = str(job.get("discovered_url") or job.get("url") or "")
        prepared["source"] = str(job.get("source") or "job_feed")
        return prepared

    def _deterministic_analysis(self, job: dict[str, Any]) -> dict[str, Any]:
        gate = self.quality_gate.evaluate(
            JobQualityGateRequest(
                company=job["company"],
                title=job["title"],
                jd_text=job["jd_text"],
                location=job.get("location"),
                source=job["source"],
            )
        )
        parsed = self.parser.parse(
            JDParseRequest(
                job_id=job["job_id"],
                company=job["company"],
                title=job["title"],
                official_url=job.get("discovered_url") or None,
                jd_text=job["jd_text"],
            )
        )
        score = self.scorer.score(
            ResumeScoreRequest(
                job_id=job["job_id"],
                resume_version="base_resume_v1",
                parsed_jd=parsed,
            )
        )

        final_score = self._quality_adjusted_score(score.overall_score, gate.decision, gate.blockers)
        verdict = self._verdict(final_score, gate.decision)
        return {
            "job_id": job["job_id"],
            "company": job["company"],
            "title": job["title"],
            "location": job.get("location") or "",
            "source": job["source"],
            "url": job.get("discovered_url") or "",
            "score": final_score,
            "base_score": score.overall_score,
            "verdict": verdict,
            "worth_applying": verdict in {"strong_match", "good_match"},
            "label": self._label(final_score, verdict),
            "one_line_reason": self._fallback_reason(final_score, gate.decision, gate.blockers, gate.reasons),
            "strengths": self._fallback_strengths(score.matched_skills, gate.signals),
            "gaps": score.missing_items[:5],
            "risks": (gate.blockers or gate.reasons)[:5],
            "suggested_actions": self._suggested_actions(verdict),
            "sponsorship_note": self._sponsorship_note(gate.authorization_risk),
            "scoring_mode": "deterministic_fallback",
            "quality_gate_decision": gate.decision,
            "target_role_key": gate.role_key,
            "years_required": gate.years_required,
            "components": {
                "required_skills": score.required_skills_score,
                "preferred_skills": score.preferred_skills_score,
                "experience": score.experience_score,
                "education": score.education_score,
                "domain": score.domain_score,
                "constraints": score.constraints_score,
            },
            "parsed": {
                "required_skills": parsed.required_skills,
                "preferred_skills": parsed.preferred_skills,
                "keywords": parsed.keywords,
                "constraints": parsed.constraints,
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def _call_llm(self, job: dict[str, Any], deterministic: dict[str, Any]) -> dict[str, Any]:
        prompt = self._prompt(job, deterministic)
        system = (
            "You are a careful job-match analyst for a junior US-based Data/AI candidate. "
            "Return only valid JSON. Be honest about visa, seniority, clearance, and skill fit. "
            "Do not invent experience. Keep explanations concise. Treat security clearance, "
            "US citizenship, senior-only scope, and hard work-authorization conflicts as blockers."
        )

        if settings.llm_provider == "ollama" and self.ollama.is_available():
            result = self.ollama.generate_json(prompt, system=system)
            if result:
                result["_llm_provider"] = "ollama"
                result["_llm_model"] = settings.ollama_model
                return result

        if settings.anthropic_api_key and anthropic is not None:
            try:
                client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                message = client.messages.create(
                    model=settings.anthropic_model,
                    max_tokens=1200,
                    temperature=0.1,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = message.content[0].text.strip()
                result = self._parse_json(raw)
                if result:
                    result["_llm_provider"] = "anthropic"
                    result["_llm_model"] = settings.anthropic_model
                return result
            except Exception as exc:
                logger.warning("Anthropic match scoring failed: %s", exc)
                return {}

        if self.ollama.is_available():
            result = self.ollama.generate_json(prompt, system=system)
            if result:
                result["_llm_provider"] = "ollama"
                result["_llm_model"] = settings.ollama_model
            return result

        return {}

    def _prompt(self, job: dict[str, Any], deterministic: dict[str, Any]) -> str:
        profile = self._profile_excerpt()
        skills = self._compact_skills(profile.get("skills", {}))
        projects = ", ".join(
            item.get("name", "")
            for item in profile.get("project_evidence", [])[:4]
            if item.get("name")
        )
        experience = "; ".join(
            f"{item.get('title', '')} using {', '.join(item.get('skills_used', [])[:4])}"
            for item in profile.get("experience_titles", [])[:3]
        )
        jd = job["jd_text"][:2800]
        hard_blockers = "; ".join(self._hard_blockers(deterministic["risks"])) or "none detected by rules"
        risks = "; ".join(deterministic["risks"][:4]) or "none"
        strengths = "; ".join(deterministic["strengths"][:4]) or "none"

        return f"""
Classify whether this job is worth applying to for Akhilesh.

Candidate:
- Targets: junior Data Scientist, ML Engineer, AI Engineer, Data Analyst, Business Analyst, Computer Vision Engineer, Python/AI Software Engineer.
- Experience target: 0-1.4 years preferred; up to 2 years can be review/apply if fit is strong.
- Work auth: F1 OPT until 2027-06-21, STEM OPT available, H1B needed only after OPT/STEM OPT. No US citizenship or security-clearance jobs.
- Skills: {skills}
- Experience evidence: {experience}
- Projects: {projects}

Job:
- Company: {job["company"]}
- Title: {job["title"]}
- Location: {job.get("location", "")}
- JD: {jd}

Deterministic baseline:
- Score: {deterministic["score"]}
- Gate: {deterministic["quality_gate_decision"]}
- Strengths: {strengths}
- Risks: {risks}
- Hard blockers detected: {hard_blockers}

Policy:
- If hard blockers are present, worth_applying must be false.
- A title-only reject is soft. Override it if the JD duties are actually data/ML/AI/analytics/computer-vision/Python-AI and no hard blocker is present.
- Be strict about senior/staff/lead/manager roles, 2+ years required, citizenship, clearance, and sponsorship refusal.

Return only JSON with exactly these keys:
match_score integer 0-100;
verdict one of strong_match, good_match, review, skip;
worth_applying boolean;
one_line_reason string;
strengths array of short strings;
gaps array of short strings;
risks array of short strings;
suggested_actions array of short strings;
sponsorship_note string;
confidence number 0-1.
""".strip()

    @staticmethod
    def _compact_skills(skills: dict[str, Any]) -> str:
        flattened: list[str] = []
        for value in skills.values():
            if isinstance(value, list):
                flattened.extend(str(item) for item in value)
        preferred = [
            skill
            for skill in flattened
            if skill.lower()
            in {
                "python",
                "sql",
                "machine learning",
                "deep learning",
                "pytorch",
                "tensorflow",
                "scikit-learn",
                "computer vision",
                "rag pipelines",
                "langchain",
                "fastapi",
                "docker",
                "aws ec2",
                "pandas",
                "numpy",
                "power bi",
                "streamlit",
            }
        ]
        return ", ".join(dict.fromkeys(preferred or flattened[:28]))

    def _merge_llm_result(
        self,
        job: dict[str, Any],
        deterministic: dict[str, Any],
        llm_result: dict[str, Any],
    ) -> dict[str, Any]:
        score = self._coerce_int(llm_result.get("match_score"), deterministic["score"])
        score = max(0, min(100, score))
        verdict = str(llm_result.get("verdict") or self._verdict(score, deterministic["quality_gate_decision"]))
        if verdict == "skip":
            verdict = "skip"
        elif verdict not in {"strong_match", "good_match", "review"}:
            verdict = self._verdict(score, deterministic["quality_gate_decision"])

        hard_blockers = self._hard_blockers(deterministic["risks"])
        worth_applying = bool(llm_result.get("worth_applying", verdict in {"strong_match", "good_match"}))
        if verdict in {"strong_match", "good_match"} and score >= 78 and not hard_blockers:
            worth_applying = True
        if verdict == "skip":
            worth_applying = False

        merged = dict(deterministic)
        merged.update(
            {
                "score": score,
                "verdict": verdict,
                "worth_applying": worth_applying,
                "label": self._label(score, verdict),
                "one_line_reason": str(llm_result.get("one_line_reason") or deterministic["one_line_reason"]),
                "strengths": self._list_of_strings(llm_result.get("strengths")) or deterministic["strengths"],
                "gaps": self._list_of_strings(llm_result.get("gaps")) or deterministic["gaps"],
                "risks": self._list_of_strings(llm_result.get("risks")) or deterministic["risks"],
                "suggested_actions": self._list_of_strings(llm_result.get("suggested_actions"))
                or deterministic["suggested_actions"],
                "sponsorship_note": str(llm_result.get("sponsorship_note") or deterministic["sponsorship_note"]),
                "confidence": float(llm_result.get("confidence") or 0.72),
                "scoring_mode": "llm",
                "llm_model": str(llm_result.get("_llm_model") or settings.ollama_model),
                "llm_provider": str(llm_result.get("_llm_provider") or settings.llm_provider),
                "created_at": datetime.now(UTC).isoformat(),
            }
        )

        if hard_blockers:
            merged["worth_applying"] = False
            if merged["score"] > 74:
                merged["score"] = 74
            if merged["verdict"] in {"strong_match", "good_match"}:
                merged["verdict"] = "review"
                merged["label"] = self._label(merged["score"], merged["verdict"])
            merged["risks"] = list(dict.fromkeys(hard_blockers + merged.get("risks", [])))[:5]
        return self._sanitize_analysis(job, deterministic, merged)

    def _sanitize_analysis(
        self,
        job: dict[str, Any],
        deterministic: dict[str, Any],
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        sanitized = dict(analysis)
        sanitized["gaps"] = self._clean_optional_list(sanitized.get("gaps"))
        sanitized["risks"] = self._clean_optional_list(sanitized.get("risks"))
        sanitized["strengths"] = self._clean_optional_list(sanitized.get("strengths")) or deterministic["strengths"]
        sanitized["suggested_actions"] = self._clean_optional_list(sanitized.get("suggested_actions")) or deterministic[
            "suggested_actions"
        ]

        hard_blockers = self._hard_blockers(deterministic["risks"])
        reason = str(sanitized.get("one_line_reason") or "").strip()
        if not hard_blockers and self._reason_sounds_like_false_blocker(reason):
            sanitized["one_line_reason"] = deterministic["one_line_reason"]
        self._normalize_score_verdict(sanitized, deterministic)
        if str(deterministic.get("quality_gate_decision") or "").lower() == "review":
            sanitized["score"] = min(self._coerce_int(sanitized.get("score"), deterministic["score"]), 77)
            sanitized["verdict"] = "review"
            sanitized["label"] = self._label(sanitized["score"], "review")
            sanitized["worth_applying"] = False
        return sanitized

    def _normalize_score_verdict(self, analysis: dict[str, Any], deterministic: dict[str, Any]) -> None:
        score = self._coerce_int(analysis.get("score"), deterministic["score"])
        verdict = str(analysis.get("verdict") or "")
        if score < 50 and verdict in {"strong_match", "good_match"} and deterministic["score"] >= 50:
            score = deterministic["score"]
        normalized = self._verdict(score, str(deterministic.get("quality_gate_decision") or "pass"))
        if verdict == "strong_match" and score < 88:
            verdict = normalized
        elif verdict == "good_match" and score < 78:
            verdict = normalized
        elif verdict not in {"strong_match", "good_match", "review", "skip"}:
            verdict = normalized
        analysis["score"] = score
        analysis["verdict"] = verdict
        analysis["label"] = self._label(score, verdict)
        analysis["worth_applying"] = verdict in {"strong_match", "good_match"}

    def _cache_path(self, job: dict[str, Any]) -> Path:
        mode = settings.llm_provider
        model = settings.ollama_model
        if mode != "ollama" and settings.anthropic_api_key:
            mode = "anthropic"
            model = settings.anthropic_model
        raw = "|".join(
            [
                "semantic_match_v4",
                mode,
                model,
                job["job_id"],
                job["company"],
                job["title"],
                hashlib.sha256(job["jd_text"].encode("utf-8")).hexdigest()[:16],
            ]
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"{digest}.json"

    def _profile_excerpt(self) -> dict[str, Any]:
        resume = json.loads(self.resume_path.read_text(encoding="utf-8"))
        candidate = resume.get("candidate", {})
        skills = resume.get("skills", {})
        projects = resume.get("projects", [])
        experience = resume.get("experience", [])
        return {
            "headline": candidate.get("headline", ""),
            "summary": candidate.get("base_summary", ""),
            "work_authorization": candidate.get("work_authorization", {}),
            "skills": skills,
            "experience_titles": [
                {
                    "title": item.get("title", ""),
                    "company": item.get("company", ""),
                    "dates": item.get("dates", ""),
                    "skills_used": item.get("skills_used", [])[:8],
                }
                for item in experience[:3]
            ],
            "project_evidence": [
                {
                    "name": project.get("name", ""),
                    "tags": project.get("tags", [])[:10],
                    "tech_stack": project.get("tech_stack", [])[:8],
                }
                for project in projects[:5]
            ],
        }

    @staticmethod
    def _quality_adjusted_score(score: int, gate_decision: str, blockers: list[str]) -> int:
        if blockers:
            return min(score, 59)
        if gate_decision == "reject":
            return min(score, 59)
        if gate_decision == "review":
            return min(score, 84)
        return score

    @staticmethod
    def _verdict(score: int, gate_decision: str) -> str:
        if gate_decision == "reject":
            return "skip"
        if score >= 88:
            return "strong_match"
        if score >= 78:
            return "good_match"
        return "review"

    @staticmethod
    def _label(score: int, verdict: str) -> str:
        if verdict == "strong_match":
            return "Strong Match"
        if verdict == "good_match":
            return "Good Match"
        if verdict == "skip":
            return "Skip"
        if score >= 70:
            return "Needs Review"
        return "Low Confidence"

    @staticmethod
    def _fallback_reason(score: int, gate_decision: str, blockers: list[str], reasons: list[str]) -> str:
        if blockers:
            return blockers[0]
        if reasons:
            return reasons[0]
        if score >= 88:
            return "Strong alignment with your target role family and resume evidence."
        if score >= 78:
            return "Good alignment, but review the JD before committing time."
        return "Some fit signals exist, but the role needs manual review before applying."

    @staticmethod
    def _fallback_strengths(matched_skills: list[str], signals: list[str]) -> list[str]:
        strengths = [f"Matched skill: {skill}" for skill in matched_skills[:4]]
        strengths.extend(signals[:2])
        return strengths[:5] or ["Profile has partial overlap with the job description."]

    @staticmethod
    def _suggested_actions(verdict: str) -> list[str]:
        if verdict in {"strong_match", "good_match"}:
            return [
                "Generate tailored resume packet.",
                "Open the original job posting.",
                "Run automated autofill and review before final submission.",
            ]
        if verdict == "skip":
            return ["Skip unless there is a special reason to pursue this company."]
        return ["Open the JD and review risks.", "Tailor only if the role still looks worth your time."]

    @staticmethod
    def _sponsorship_note(risk: str) -> str:
        if risk == "high":
            return "Work authorization language looks risky; review before applying."
        if risk == "medium":
            return "Sponsorship/work authorization wording needs review."
        return "No obvious sponsorship blocker found."

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = "\n".join(line for line in clean.splitlines() if not line.strip().startswith("```")).strip()
        if not clean.startswith("{"):
            start = clean.find("{")
            end = clean.rfind("}")
            if start >= 0 and end > start:
                clean = clean[start : end + 1]
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            logger.warning("LLM match JSON parse failed: %s", raw[:300])
            return {}

    @staticmethod
    def _coerce_int(value: Any, fallback: int) -> int:
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _list_of_strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return LLMMatchService._clean_optional_list(value)

    @staticmethod
    def _clean_optional_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        empty_markers = {"none", "none listed", "n/a", "na", "no major risks", "no major gaps", "no gaps"}
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if not text or text.lower().rstrip(".") in empty_markers:
                continue
            cleaned.append(text)
        return cleaned[:5]

    @staticmethod
    def _reason_sounds_like_false_blocker(reason: str) -> bool:
        lowered = reason.lower()
        if not lowered or "no " in lowered and ("blocker" in lowered or "blocked" in lowered):
            return False
        hard_terms = (
            "security clearance",
            "clearance",
            "us citizenship",
            "u.s. citizenship",
            "citizen",
            "sponsorship",
            "visa",
            "work authorization",
        )
        blocker_words = ("blocked", "blocker", "hard blocker", "cannot apply", "skip")
        return any(term in lowered for term in hard_terms) and any(word in lowered for word in blocker_words)

    @staticmethod
    def _hard_blockers(risks: list[str]) -> list[str]:
        hard_markers = (
            "seniority blocker",
            "experience requirement appears above",
            "work authorization blocker",
            "security clearance",
            "requires clearance",
            "active clearance",
            "us citizenship",
            "u.s. citizenship",
            "citizen",
            "sponsorship not available",
            "will not sponsor",
            "location blocker",
        )
        blockers: list[str] = []
        for risk in risks:
            text = risk.lower()
            if any(marker in text for marker in hard_markers):
                blockers.append(risk)
        return blockers

    @staticmethod
    def _stable_job_id(job: dict[str, Any]) -> str:
        raw = "|".join(
            [
                str(job.get("company", "")),
                str(job.get("title", "")),
                str(job.get("discovered_url") or job.get("url") or ""),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
