import json
import re
from pathlib import Path

from app.schemas.job import JobQualityGateRequest, JobQualityGateResponse


class JobQualityGateService:
    US_LOCATION_MARKERS = {
        "united states",
        "usa",
        "u.s.",
        "us",
        "alabama",
        "alaska",
        "arizona",
        "arkansas",
        "california",
        "colorado",
        "connecticut",
        "delaware",
        "florida",
        "georgia",
        "hawaii",
        "idaho",
        "illinois",
        "indiana",
        "iowa",
        "kansas",
        "kentucky",
        "louisiana",
        "maine",
        "maryland",
        "massachusetts",
        "michigan",
        "minnesota",
        "mississippi",
        "missouri",
        "montana",
        "nebraska",
        "nevada",
        "new hampshire",
        "new jersey",
        "new mexico",
        "new york",
        "north carolina",
        "north dakota",
        "ohio",
        "oklahoma",
        "oregon",
        "pennsylvania",
        "rhode island",
        "south carolina",
        "south dakota",
        "tennessee",
        "texas",
        "utah",
        "vermont",
        "virginia",
        "washington",
        "west virginia",
        "wisconsin",
        "wyoming",
        "al",
        "ak",
        "az",
        "ar",
        "ca",
        "co",
        "ct",
        "de",
        "fl",
        "ga",
        "hi",
        "id",
        "il",
        "in",
        "ia",
        "ks",
        "ky",
        "la",
        "me",
        "md",
        "ma",
        "mi",
        "mn",
        "ms",
        "mo",
        "mt",
        "ne",
        "nv",
        "nh",
        "nj",
        "nm",
        "ny",
        "nc",
        "nd",
        "oh",
        "ok",
        "or",
        "pa",
        "ri",
        "sc",
        "sd",
        "tn",
        "tx",
        "ut",
        "vt",
        "va",
        "wa",
        "wv",
        "wi",
        "wy",
    }
    NON_US_LOCATION_MARKERS = {
        "apac",
        "asia",
        "australia",
        "bangalore",
        "barcelona",
        "berlin",
        "brazil",
        "bengaluru",
        "canada",
        "delhi",
        "dublin",
        "emea",
        "eu",
        "europe",
        "european union",
        "france",
        "germany",
        "hyderabad",
        "iasi",
        "india",
        "ireland",
        "japan",
        "korea",
        "latam",
        "latin america",
        "london",
        "madrid",
        "mexico",
        "munich",
        "netherlands",
        "paris",
        "poland",
        "pune",
        "romania",
        "seoul",
        "singapore",
        "south korea",
        "spain",
        "sydney",
        "tokyo",
        "toronto",
        "uk",
        "united kingdom",
        "vancouver",
        "warsaw",
    }

    def __init__(
        self,
        profile_path: str = "data/job_search_profile.json",
        role_profiles_path: str = "data/master_resume/role_profiles.json",
    ) -> None:
        self.profile = self._load_json(profile_path)
        self.role_profiles = self._load_json(role_profiles_path)

    def evaluate(self, payload: JobQualityGateRequest) -> JobQualityGateResponse:
        title_text = self._normalize(payload.title)
        jd_text = self._normalize(payload.jd_text)
        location_text = self._normalize(payload.location or "")
        combined = " ".join(part for part in [title_text, jd_text, location_text] if part)

        reasons: list[str] = []
        blockers: list[str] = []
        signals: list[str] = []

        role_key, title_score = self._match_role(title_text)
        keyword_score = self._keyword_score(role_key, combined)

        if role_key:
            signals.append(f"Target role match: {self.role_profiles.get(role_key, {}).get('display_name', role_key)}")
        elif self.profile.get("quality_gate", {}).get("reject_non_target_titles", True):
            blockers.append("Title does not match the configured target role families.")

        experience_risk, years_required, experience_notes = self._experience_check(title_text, jd_text)
        signals.extend(experience_notes["signals"])
        blockers.extend(experience_notes["blockers"])
        reasons.extend(experience_notes["reasons"])

        authorization_risk, authorization_notes = self._authorization_check(combined)
        signals.extend(authorization_notes["signals"])
        blockers.extend(authorization_notes["blockers"])
        reasons.extend(authorization_notes["reasons"])

        location_notes = self._location_check(location_text)
        signals.extend(location_notes["signals"])
        blockers.extend(location_notes["blockers"])
        reasons.extend(location_notes["reasons"])

        language_notes = self._language_check(combined)
        blockers.extend(language_notes["blockers"])
        reasons.extend(language_notes["reasons"])
        signals.extend(language_notes["signals"])

        if blockers:
            decision = "reject"
        elif reasons:
            decision = "review"
        else:
            decision = "pass"

        return JobQualityGateResponse(
            decision=decision,
            actionable=decision != "reject",
            role_key=role_key,
            reasons=reasons,
            blockers=blockers,
            signals=signals,
            title_score=title_score,
            keyword_score=keyword_score,
            years_required=years_required,
            experience_risk=experience_risk,
            authorization_risk=authorization_risk,
        )

    def _match_role(self, title_text: str) -> tuple[str | None, int]:
        best_role: str | None = None
        best_score = 0

        for role in self.profile.get("target_roles", []):
            role_key = role.get("role_key")
            for title in role.get("titles", []):
                normalized_title = self._normalize(title)
                if normalized_title and normalized_title in title_text:
                    score = len(normalized_title.split())
                    if score > best_score:
                        best_role = role_key
                        best_score = score

        return best_role, best_score

    def _keyword_score(self, role_key: str | None, text: str) -> int:
        if not role_key:
            return 0

        profile = self.role_profiles.get(role_key, {})
        keywords = [
            *profile.get("priority_skills", []),
            *profile.get("preferred_skills", []),
            *profile.get("priority_tags", []),
        ]
        return len({item for item in keywords if self._normalize(item) in text})

    def _experience_check(self, title_text: str, jd_text: str) -> tuple[str, float | None, dict[str, list[str]]]:
        config = self.profile.get("experience_filter", {})
        notes = {"signals": [], "blockers": [], "reasons": []}

        if config.get("reject_senior_roles", True):
            senior_terms = config.get("senior_terms", [])
            senior_hit = next((term for term in senior_terms if self._normalize(term) in title_text), None)
            if senior_hit:
                notes["blockers"].append(f"Seniority blocker in title: {senior_hit}.")
                return "high", None, notes

        text = f"{title_text} {jd_text}"
        years = self._extract_years(text)
        hard_max = float(config.get("hard_max_years", 2.0))
        preferred_max = float(config.get("preferred_max_years", 1.4))

        if years is None:
            if config.get("allow_unspecified_years", True):
                notes["signals"].append("Experience requirement is unspecified or not clearly above target.")
                return "low", None, notes
            notes["reasons"].append("Experience requirement is unclear.")
            return "medium", None, notes

        if self._has_required_plus_years_at_or_above(text, hard_max):
            notes["blockers"].append(f"Experience requirement appears above junior target: {years:g}+ years.")
            return "high", years, notes

        if years > hard_max:
            notes["blockers"].append(f"Experience requirement appears above junior target: {years:g}+ years.")
            return "high", years, notes

        if years > preferred_max:
            notes["reasons"].append(f"Experience requirement is slightly above preferred target: {years:g} years.")
            return "medium", years, notes

        notes["signals"].append(f"Experience requirement fits junior target: {years:g} years.")
        return "low", years, notes

    def _authorization_check(self, text: str) -> tuple[str, dict[str, list[str]]]:
        config = self.profile.get("work_authorization", {})
        notes = {"signals": [], "blockers": [], "reasons": []}

        hard_blocker = self._hard_authorization_blocker(text)
        if hard_blocker:
            notes["blockers"].append(hard_blocker)
            return "high", notes

        for term in config.get("reject_terms", []):
            normalized = self._normalize(term)
            if normalized and normalized in text:
                notes["blockers"].append(f"Work authorization blocker: {term}.")
                return "high", notes

        for term in config.get("review_terms", []):
            normalized = self._normalize(term)
            if normalized and normalized in text:
                notes["reasons"].append(f"Work authorization needs review: {term}.")
                return "medium", notes

        notes["signals"].append("No citizenship, clearance, or sponsorship blocker found.")
        return "low", notes

    @staticmethod
    def _hard_authorization_blocker(text: str) -> str:
        no_sponsor_patterns = [
            r"(?:does not|do not|will not|cannot|can't|unable to|not able to)\s+(?:sponsor|support|sponsor/support|support/sponsor)",
            r"(?:does not|do not|will not|cannot|can't|unable to|not able to)\s+(?:provide|offer)\s+(?:visa\s+)?sponsorship",
            r"without\s+(?:current\s+or\s+future\s+)?(?:visa\s+)?sponsorship",
            r"no\s+(?:opt|cpt|stem[/\s-]?opt|h-?1b|visa|,|\s|or|and)+sponsorship(?:\s+now\s+or\s+in\s+future)?",
            r"(?:visa\s+)?sponsorship\s+(?:is\s+)?(?:not available|unavailable)",
            r"no\s+(?:visa\s+)?sponsorship",
        ]
        if any(re.search(pattern, text) for pattern in no_sponsor_patterns):
            if any(term in text for term in ["h-1b", "h1b", "tn", "i-983", "stem opt", "visa", "sponsorship"]):
                return "Work authorization blocker: company does not sponsor/support H-1B, TN, STEM OPT, or visa sponsorship for this role."
            return "Work authorization blocker: company does not provide visa sponsorship for this role."

        if "i-983" in text or "stem opt" in text:
            if re.search(r"(?:not|no|unable)\s+\w{0,20}\s*(?:support|sponsor)", text):
                return "Work authorization blocker: company does not support STEM OPT/I-983 for this role."

        return ""

    def _location_check(self, location_text: str) -> dict[str, list[str]]:
        config = self.profile.get("location_filter", {})
        notes = {"signals": [], "blockers": [], "reasons": []}

        if not location_text:
            notes["signals"].append("Location not specified; relocation flexibility applies.")
            return notes

        if config.get("us_only", False):
            us_hit = self._contains_location_marker(location_text, self.US_LOCATION_MARKERS)
            non_us_hit = self._contains_location_marker(location_text, self.NON_US_LOCATION_MARKERS)
            remote_only = bool(config.get("remote_ok", True)) and location_text in {"remote", "virtual"}
            if non_us_hit and not us_hit:
                notes["blockers"].append("Location blocker: role is outside the configured United States search scope.")
                return notes
            if non_us_hit and us_hit:
                notes["reasons"].append("Location includes both US and non-US scope; confirm the role is US eligible.")
                return notes
            if not us_hit and not remote_only:
                notes["reasons"].append("Location needs review: role is not clearly within the configured United States scope.")
                return notes

        for term in config.get("avoid_locations", []):
            normalized = self._normalize(term)
            if normalized and normalized in location_text:
                notes["blockers"].append(f"Location blocker: {term}.")

        notes["signals"].append("Location accepted under relocation/remote preferences.")
        return notes

    @staticmethod
    def _contains_location_marker(text: str, markers: set[str]) -> bool:
        return any(re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", text) for marker in markers)

    @staticmethod
    def _language_check(text: str) -> dict[str, list[str]]:
        notes = {"signals": [], "blockers": [], "reasons": []}
        languages = [
            "spanish",
            "mandarin",
            "chinese",
            "french",
            "german",
            "japanese",
            "korean",
            "portuguese",
            "arabic",
            "italian",
        ]

        for language in languages:
            patterns = [
                rf"\b(?:fluent|native|bilingual|proficient|professional)\s+(?:in\s+)?{language}\b",
                rf"\b{language}\s+(?:speaker|speakers|fluency|required|language)\b",
                rf"\b(?:requires|required|must have)\s+{language}\b",
            ]
            if any(re.search(pattern, text) for pattern in patterns):
                notes["blockers"].append(
                    f"Language requirement blocker: role explicitly requires {language} language ability not listed in the profile."
                )
                break

        return notes

    @staticmethod
    def _extract_years(text: str) -> float | None:
        patterns = [
            r"(?:less than|under)\s+(\d+(?:\.\d+)?)\s*(?:years|year|yrs|yr)",
            r"(?:up to|upto)\s+(\d+(?:\.\d+)?)\s*(?:years|year|yrs|yr)",
            r"(\d+(?:\.\d+)?)\s*(?:\+|plus)?\s*(?:years|year|yrs|yr)",
            r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:years|year|yrs|yr)",
        ]

        candidates: list[float] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                if not JobQualityGateService._is_experience_year_context(text, match.start(), match.end()):
                    continue
                numbers = [float(group) for group in match.groups() if group is not None]
                if numbers:
                    candidates.append(max(numbers))

        return min(candidates) if candidates else None

    @staticmethod
    def _is_experience_year_context(text: str, start: int, end: int) -> bool:
        context = text[max(0, start - 90) : min(len(text), end + 90)]
        if re.search(r"\bover\s+$", text[max(0, start - 10) : start]):
            return False
        experience_markers = [
            "experience",
            "qualification",
            "qualifications",
            "required",
            "requirement",
            "minimum",
            "preferred",
            "must have",
            "skills you",
            "bring",
            "background",
        ]
        if any(marker in context for marker in experience_markers):
            return True
        history_markers = ["industry", "reputation", "founded", "history", "employees", "customers", "communities"]
        return not any(marker in context for marker in history_markers)

    @staticmethod
    def _has_required_plus_years_at_or_above(text: str, hard_max: float) -> bool:
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:\+|plus)\s*(?:years|year|yrs|yr)", text):
            if not JobQualityGateService._is_experience_year_context(text, match.start(), match.end()):
                continue
            years = float(match.group(1))
            if years < hard_max:
                continue
            context = text[max(0, match.start() - 24) : match.start()]
            if re.search(r"(?:up to|upto|less than|under)\s+$", context):
                continue
            return True
        return False

    @staticmethod
    def _normalize(value: str) -> str:
        lowered = value.lower()
        lowered = re.sub(r"[^a-z0-9+./#-]+", " ", lowered)
        return re.sub(r"\s+", " ", lowered).strip()

    @staticmethod
    def _load_json(path_str: str) -> dict:
        path = Path(path_str)
        return json.loads(path.read_text(encoding="utf-8"))
