from app.services.application_packet_service import ApplicationPacketService


def test_application_packet_uses_company_folder_and_manual_submit_boundary():
    service = ApplicationPacketService()

    packet = service.build(
        company="Best Buy",
        role="Associate Decision Scientist, Market Share",
        official_url="https://example.com/job",
        base_score=82,
        tailored_score=88,
        decision="apply_now",
        decision_reason="Strong fit after tailoring.",
        target_role_key="data_scientist",
    )

    assert packet.company_folder_path.endswith("Best Buy")
    assert "associate_decision_scientist_market_share" in packet.tailored_resume_path
    assert packet.base_resume_pdf.endswith("Akhilesh_Kumbhar_Resume_May_24_2026.pdf")
    assert packet.prefill_profile["work_authorization"]["requires_current_sponsorship"] is False
    assert packet.prefill_profile["work_authorization"]["requires_future_sponsorship"] is True
    assert "final review and submission" in packet.human_control_note.lower()
    assert packet.ats_answer_bank["work_authorization"]["authorized_to_work_us_now"] == "Yes"
    assert packet.ats_answer_bank["work_authorization"]["requires_sponsorship_now"] == "No"
    assert packet.ats_answer_bank["work_authorization"]["requires_sponsorship_future"] == "Yes"
    assert any("linkedin.com/search" in item["url"] for item in packet.recruiter_searches)
    assert any(step["step"] == "human_submit" for step in packet.application_steps)
