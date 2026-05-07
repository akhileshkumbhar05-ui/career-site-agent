import json
import re
from pathlib import Path


_TAXONOMY_PATH = Path("data/master_resume/skill_taxonomy.json")


def _load_taxonomy() -> dict[str, list[str]]:
    if not _TAXONOMY_PATH.exists():
        return {}
    return json.loads(_TAXONOMY_PATH.read_text(encoding="utf-8"))


def _clean_text(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[\/_,\-]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_skills(skills: list[str]) -> list[str]:
    taxonomy = _load_taxonomy()

    alias_to_canonical: dict[str, str] = {}

    for canonical, aliases in taxonomy.items():
        canonical_clean = _clean_text(canonical)
        alias_to_canonical[canonical_clean] = canonical_clean

        for alias in aliases:
            alias_clean = _clean_text(alias)
            alias_to_canonical[alias_clean] = canonical_clean

    normalized: list[str] = []
    seen: set[str] = set()

    for skill in skills:
        cleaned = _clean_text(skill)
        if not cleaned:
            continue

        canonical = alias_to_canonical.get(cleaned, cleaned)

        if canonical not in seen:
            seen.add(canonical)
            normalized.append(canonical)

    return normalized