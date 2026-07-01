from pathlib import Path
import os
import shutil

from app.services.resume_quality_service import ResumeQualityService


def test_resume_quality_catches_unsupported_rewritten_metric():
    tmp_path = Path("data/outputs/test_resume_quality") / str(os.getpid())
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    tmp_path.mkdir(parents=True)

    html = """
    <html><body>
    <h1>Akhilesh Arunkumar Kumbhar</h1>
    <p>akhileshkumbhar0405@gmail.com Python SQL Data Science</p>
    <h2>Technical Skills</h2>
    <h2>Professional Experience</h2>
    <h2>Key Projects</h2>
    <h2>Education</h2>
    """ + " ".join(["word"] * 500) + """
    </body></html>
    """
    html_path = tmp_path / "resume.html"
    html_path.write_text(html, encoding="utf-8")

    passed, checks = ResumeQualityService().validate(
        html_path=html_path,
        master_resume={"projects": [{"bullets": ["Achieved 70% accuracy."]}]},
        rewritten_bullets=[
            {
                "project_id": "example",
                "rewritten": "Improved model accuracy by 99.9% using unsupported evidence.",
            }
        ],
    )

    assert passed is False
    assert any(
        item["name"] == "rewritten_bullet_1_metrics_supported" and item["passed"] is False
        for item in checks
    )
