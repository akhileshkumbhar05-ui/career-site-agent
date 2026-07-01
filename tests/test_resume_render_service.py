import os
import shutil
import zipfile
from pathlib import Path

from app.services.resume_render_service import ResumeRenderService


def test_resume_renderer_uses_real_profile_links_and_clean_title():
    output_dir = Path("data/outputs/test_resume_render_service") / str(os.getpid())
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    output_path = output_dir / "resume.html"
    ResumeRenderService().render_html(
        str(output_path),
        {
            "full_name": "Akhilesh Arunkumar Kumbhar",
            "location": "Arlington, TX",
            "email": "akhileshkumbhar0405@gmail.com",
            "phone": "+1 (346) 592-3971",
            "linkedin": "LinkedIn",
            "linkedin_url": "https://www.linkedin.com/in/akhilesh-kumbhar-aak",
            "github": "GitHub",
            "github_url": "https://github.com/akhileshkumbhar05-ui",
            "base_summary": "Summary.",
        },
        selected_projects=[],
        skills={},
    )

    rendered = output_path.read_text(encoding="utf-8")

    assert "<title>Akhilesh Arunkumar Kumbhar</title>" in rendered
    assert "Tailored Resume</title>" not in rendered
    assert 'href="https://www.linkedin.com/in/akhilesh-kumbhar-aak"' in rendered
    assert 'href="https://github.com/akhileshkumbhar05-ui"' in rendered


def test_resume_renderer_writes_docx_with_profile_hyperlinks():
    output_dir = Path("data/outputs/test_resume_render_service_docx") / str(os.getpid())
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    output_path = output_dir / "resume.docx"
    ResumeRenderService().render_docx(
        str(output_path),
        {
            "full_name": "Akhilesh Arunkumar Kumbhar",
            "location": "Arlington, TX",
            "email": "akhileshkumbhar0405@gmail.com",
            "phone": "+1 (346) 592-3971",
            "linkedin": "LinkedIn",
            "linkedin_url": "https://www.linkedin.com/in/akhilesh-kumbhar-aak",
            "github": "GitHub",
            "github_url": "https://github.com/akhileshkumbhar05-ui",
            "base_summary": "Data Scientist with Python and SQL experience.",
        },
        selected_projects=[],
        skills={"programming_languages": ["Python", "SQL"]},
        experience=[],
        education=[{"degree": "Master of Science in Data Science", "institution": "University of Texas at Arlington", "dates": "May 2026", "gpa": "3.9"}],
    )

    assert output_path.exists()
    with zipfile.ZipFile(output_path) as docx_zip:
        document_xml = docx_zip.read("word/document.xml").decode("utf-8")
        rels_xml = docx_zip.read("word/_rels/document.xml.rels").decode("utf-8")

    assert "Akhilesh Arunkumar Kumbhar".upper() in document_xml
    assert "https://www.linkedin.com/in/akhilesh-kumbhar-aak" in rels_xml
    assert "https://github.com/akhileshkumbhar05-ui" in rels_xml
