import re

from app.core.skill_mapper import normalize_skills
from app.schemas.job import JDParseRequest, ParsedJD


COMMON_SKILLS = [
    "python",
    "sql",
    "machine learning",
    "deep learning",
    "fastapi",
    "aws",
    "docker",
    "pandas",
    "scikit-learn",
    "pytorch",
    "tensorflow",
    "llm",
    "rag",
    "nlp",
    "computer vision",
    "streamlit",
    "power bi",
    "api development",
    "statistics",
    "java",
    "matlab",
    "opencv",
    "langchain",
    "sentence transformers",
    "forecasting",
    "time series",
    "recommender systems",
    "deployment",
    "analytics",
    "data pipelines",
    "model evaluation",
    "prompt engineering",
    "human in the loop",
]


SECTION_PATTERNS = {
    "required": [
        r"(required qualifications|minimum qualifications|basic qualifications|must have|requirements|what we're looking for)(.*?)(preferred qualifications|nice to have|bonus|preferred skills|about the role|responsibilities|what you'll do|$)",
    ],
    "preferred": [
        r"(preferred qualifications|nice to have|bonus|preferred skills|good to have)(.*?)(responsibilities|about the role|what you'll do|requirements|qualifications|$)",
    ],
    "responsibilities": [
        r"(responsibilities|what you'll do|what you will do|about the role|your responsibilities)(.*?)(requirements|qualifications|preferred|minimum qualifications|$)",
    ],
}


class JDParserService:
    def parse(self, payload: JDParseRequest) -> ParsedJD:
        original_text = payload.jd_text
        text = self._normalize_text(original_text)

        required_section = self._extract_section(text, "required")
        preferred_section = self._extract_section(text, "preferred")
        responsibilities_section = self._extract_section(text, "responsibilities")

        required_skills = self._extract_skills(required_section) if required_section else []
        preferred_skills = self._extract_skills(preferred_section) if preferred_section else []

        if not required_skills and not preferred_skills:
            all_found = self._extract_skills(text)
            required_skills = all_found[: min(6, len(all_found))]
            preferred_skills = all_found[1:min(8, len(all_found))] if len(all_found) > 2 else []

        responsibilities = self._extract_bullets_from_section(responsibilities_section)
        if not responsibilities:
            responsibilities = self._extract_bullets(original_text)

        keywords = sorted(
            set(
                normalize_skills(
                    required_skills
                    + preferred_skills
                    + self._extract_keywords(text)
                )
            )
        )

        years_required = self._extract_years(original_text)
        education = self._extract_education(text)
        constraints = self._extract_constraints(text)

        return ParsedJD(
            job_id=payload.job_id,
            company=payload.company,
            title=payload.title,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            years_required=years_required,
            education=education,
            responsibilities=responsibilities,
            keywords=keywords,
            constraints=constraints,
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        return text.lower()

    def _extract_section(self, text: str, section_type: str) -> str:
        for pattern in SECTION_PATTERNS.get(section_type, []):
            match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(2).strip()
        return ""

    @staticmethod
    def _extract_skills(text: str) -> list[str]:
        found = []
        cleaned_text = text.lower()

        for skill in COMMON_SKILLS:
            if skill.lower() in cleaned_text:
                found.append(skill)

        return normalize_skills(found)

    @staticmethod
    def _extract_bullets_from_section(section_text: str) -> list[str]:
        if not section_text:
            return []

        lines = [line.strip("-• \t") for line in section_text.splitlines() if line.strip()]
        cleaned = [
            line for line in lines
            if len(line) > 12 and not line.lower().startswith(("required qualifications", "preferred qualifications"))
        ]
        return cleaned[:8]

    @staticmethod
    def _extract_bullets(text: str) -> list[str]:
        raw_lines = text.splitlines()
        lines = [line.strip("-• \t") for line in raw_lines if line.strip()]

        bullet_like = [
            line for line in lines
            if len(line) > 12 and (
                line.startswith(("-", "•"))
                or len(line.split()) > 4
            )
        ]

        cleaned = []
        for line in bullet_like:
            line = line.strip("-• \t")
            if line and line not in cleaned:
                cleaned.append(line)

        return cleaned[:8]

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        phrases = []
        for phrase in [
            "entry level",
            "new grad",
            "communication",
            "experimentation",
            "deployment",
            "production",
            "analytics",
            "data pipelines",
            "model evaluation",
            "cloud",
            "stakeholder",
            "cross functional",
            "real time",
            "decision support",
        ]:
            if phrase in text:
                phrases.append(phrase)
        return phrases

    @staticmethod
    def _extract_years(text: str) -> str | None:
        patterns = [
            r"(\d+\+?\s*(?:-|to)?\s*\d*\s*years?)",
            r"(\d+\+?\s*yrs?)",
            r"((?:one|two|three|four|five)\s+years?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    @staticmethod
    def _extract_education(text: str) -> str | None:
        if "phd" in text or "doctorate" in text:
            return "phd"
        if "master" in text:
            return "master's"
        if "bachelor" in text or "undergraduate degree" in text:
            return "bachelor's"
        return None

    @staticmethod
    def _extract_constraints(text: str) -> list[str]:
        constraints = []
        for phrase in [
            "visa",
            "sponsorship",
            "hybrid",
            "remote",
            "onsite",
            "relocation",
            "work authorization",
            "authorized to work",
            "no sponsorship",
            "cannot require sponsorship",
        ]:
            if phrase in text:
                constraints.append(phrase)

        return sorted(set(constraints))