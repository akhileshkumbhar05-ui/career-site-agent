def weighted_score(
    *,
    required_skills_score: int,
    preferred_skills_score: int,
    experience_score: int,
    education_score: int,
    domain_score: int,
    constraints_score: int,
) -> int:
    total = (
        required_skills_score * 0.35
        + preferred_skills_score * 0.15
        + experience_score * 0.25
        + education_score * 0.10
        + domain_score * 0.10
        + constraints_score * 0.05
    )
    return round(total)
