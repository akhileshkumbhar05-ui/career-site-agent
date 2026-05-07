import streamlit as st


def render_score_card(score) -> None:
    st.subheader("Resume Fit Score")

    overall = score.overall_score
    recommendation = getattr(score, "recommendation", None)

    metric_col1, metric_col2 = st.columns([1, 1])

    with metric_col1:
        st.metric("Overall Match", f"{overall}%")

    with metric_col2:
        if overall >= 85:
            st.success("Strong fit")
        elif overall >= 65:
            st.warning("Needs tailoring/review")
        else:
            st.error("Weak fit")

    if recommendation:
        label_map = {
            "apply_now": "Apply Now",
            "tailor_resume": "Tailor Resume",
            "manual_review": "Manual Review",
        }
        st.caption(f"Model recommendation: {label_map.get(recommendation, recommendation)}")

    st.markdown("### Score Breakdown")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Required Skills", f"{score.required_skills_score}%")
        st.metric("Experience / Projects", f"{score.experience_score}%")
        st.metric("Domain Fit", f"{score.domain_score}%")

    with col2:
        st.metric("Preferred Skills", f"{score.preferred_skills_score}%")
        st.metric("Education", f"{score.education_score}%")
        st.metric("Constraints Fit", f"{score.constraints_score}%")

    st.markdown("### Skills Alignment")

    skills_col1, skills_col2 = st.columns(2)

    with skills_col1:
        st.markdown("**Matched Skills**")
        if score.matched_skills:
            for skill in score.matched_skills:
                st.write(f"- {skill}")
        else:
            st.write("No matched skills identified.")

    with skills_col2:
        st.markdown("**Missing Required Skills**")
        if score.missing_items:
            for skill in score.missing_items:
                st.write(f"- {skill}")
        else:
            st.write("No missing required skills.")

    st.markdown("### Score Interpretation")

    if overall >= 85:
        st.info("The current resume is already well aligned with this role.")
    elif overall >= 65:
        st.info("This role is potentially salvageable with targeted resume tailoring.")
    else:
        st.info("The current resume appears weakly aligned with this role and may not be worth targeting.")