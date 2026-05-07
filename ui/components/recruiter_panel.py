import streamlit as st


def render_recruiter_panel(company: str, title: str) -> None:
    st.subheader("Recruiter Discovery")

    info_col1, info_col2 = st.columns(2)

    with info_col1:
        st.markdown("**Company**")
        st.write(company)

    with info_col2:
        st.markdown("**Target Role**")
        st.write(title)

    st.markdown("### Current Status")
    st.info("Recruiter lookup is not wired yet. This panel is reserved for the contacts API integration.")

    st.markdown("### Planned Output")
    st.write("- Recruiter / talent acquisition contact name")
    st.write("- Title / function")
    st.write("- Source link")
    st.write("- Confidence score")
    st.write("- Outreach draft")

    st.markdown("### Next Integration")
    st.caption("Connect this panel to the `/contacts/find-recruiter` and `/contacts/draft-outreach` endpoints.")