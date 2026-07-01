from pathlib import Path

from app.services.profile_evidence_service import ProfileEvidenceService


def test_profile_evidence_redacts_secrets_but_keeps_public_profile_links(tmp_path: Path) -> None:
    profile_dir = tmp_path / "Profile"
    profile_dir.mkdir()
    (profile_dir / "Instructions.txt").write_text(
        "\n".join(
            [
                "Github: https://github.com/akhileshkumbhar05-ui",
                "GitHub access link: https://github.com/org/private?token=ghp_should_not_leave",
                "API key: secret-value",
                "Use project evidence only when the JD connects clearly.",
            ]
        ),
        encoding="utf-8",
    )
    (profile_dir / "EREV Summary.txt").write_text("50-mile EREVs electrify 73.3% of U.S. LDV VMT.", encoding="utf-8")

    context = ProfileEvidenceService(profile_dir).build_prompt_context()
    context_text = str(context)

    assert "https://github.com/akhileshkumbhar05-ui" in context_text
    assert "ghp_should_not_leave" not in context_text
    assert "secret-value" not in context_text
    assert "[REDACTED_SECRET]" in context_text
    assert context["evidence_summaries"][0]["source"] == "EREV Summary.txt"


def test_profile_evidence_discovers_base_resume_pdf(tmp_path: Path) -> None:
    profile_dir = tmp_path / "Profile"
    profile_dir.mkdir()
    resume = profile_dir / "Akhilesh_Kumbhar_Resume_May_24_2026.pdf"
    resume.write_bytes(b"%PDF-1.4")

    assert ProfileEvidenceService(profile_dir).base_resume_pdf() == str(resume.resolve())
