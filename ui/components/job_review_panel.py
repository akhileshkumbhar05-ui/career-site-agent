import streamlit as st


def render_job_review_panel(job: dict, parsed) -> None:
    st.subheader("Job Review")

    top_col1, top_col2 = st.columns(2)

    with top_col1:
        st.markdown("**Company**")
        st.write(job.get("company", "N/A"))

        st.markdown("**Role**")
        st.write(job.get("title", "N/A"))

    with top_col2:
        st.markdown("**Job ID**")
        st.write(job.get("job_id", "N/A"))

        if getattr(parsed, "years_required", None):
            st.markdown("**Experience Required**")
            st.write(parsed.years_required)

    if getattr(parsed, "education", None):
        st.markdown("**Education Requirement**")
        st.write(parsed.education)

    if getattr(parsed, "constraints", None):
        st.markdown("**Constraints**")
        if parsed.constraints:
            for item in parsed.constraints:
                st.write(f"- {item}")
        else:
            st.write("None identified.")

    st.markdown("### Skills Extracted")

    skills_col1, skills_col2 = st.columns(2)

    with skills_col1:
        st.markdown("**Required Skills**")
        if parsed.required_skills:
            for skill in parsed.required_skills:
                st.write(f"- {skill}")
        else:
            st.write("No required skills extracted.")

    with skills_col2:
        st.markdown("**Preferred Skills**")
        if parsed.preferred_skills:
            for skill in parsed.preferred_skills:
                st.write(f"- {skill}")
        else:
            st.write("No preferred skills extracted.")

    if getattr(parsed, "keywords", None):
        st.markdown("### Keywords")
        if parsed.keywords:
            st.caption(", ".join(parsed.keywords))

    st.markdown("### Responsibilities")
    if parsed.responsibilities:
        for item in parsed.responsibilities:
            st.write(f"- {item}")
    else:
        st.write("No responsibilities extracted.")