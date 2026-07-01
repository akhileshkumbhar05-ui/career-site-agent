from app.schemas.pipeline import JobProcessRequest
from app.schemas.queue import JobQueueItem
from scripts.queue_status_report import build_records, render_markdown


def test_queue_report_highlights_packet_ready_items():
    item = JobQueueItem(
        queue_id="job_report_1",
        fingerprint="fingerprint",
        job=JobProcessRequest(
            job_id="report_001",
            company="Report Labs",
            title="Junior Data Scientist",
            jd_text="Python SQL ML",
            discovered_url="https://example.com/report-labs",
            source="pytest",
            location="Remote",
        ),
        status="packet_ready",
        priority=1,
        attempts=1,
        result={
            "pipeline_result": {
                "decision": "apply_now",
                "decision_reason": "Strong data science fit.",
                "base_score": 82,
                "tailored_score": 90,
                "official_url": "https://example.com/official",
            },
            "export_result": {
                "packet_folder_path": "data/outputs/queue_packets/Report Labs/application_packets/report",
                "tailored_resume_pdf_path": "data/outputs/queue_packets/Report Labs/resume.pdf",
                "apply_plan_path": "data/outputs/queue_packets/Report Labs/application_packets/report/apply_plan.json",
                "outreach_path": "data/outputs/queue_packets/Report Labs/application_packets/report/recruiter_outreach.txt",
            },
        },
        created_at="2026-05-26T00:00:00+00:00",
        updated_at="2026-05-26T00:05:00+00:00",
    )

    records = build_records([item])
    markdown = render_markdown(records, created_at="2026-05-26T00:10:00+00:00")

    assert records[0]["status"] == "packet_ready"
    assert records[0]["apply_plan_path"].endswith("apply_plan.json")
    assert "Ready To Review / Apply" in markdown
    assert "Report Labs - Junior Data Scientist" in markdown
    assert "Score: 82 base / 90 tailored" in markdown
