def select_summary_variant(title: str) -> str:
    lowered = title.lower()
    if "data scientist" in lowered:
        return "data_scientist"
    if "machine learning" in lowered or "ml engineer" in lowered:
        return "ml_engineer"
    return "ai_engineer"
