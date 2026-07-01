import re
from pathlib import Path

from bs4 import BeautifulSoup

from app.services.profile_evidence_service import ProfileEvidenceService


class ResumeQualityService:
    REQUIRED_SECTIONS = [
        "technical skills",
        "professional experience",
        "key projects",
        "education",
    ]

    REQUIRED_TERMS = [
        "Akhilesh",
        "Python",
        "SQL",
        "Data Science",
    ]

    def validate(
        self,
        *,
        html_path: Path,
        pdf_path: Path | None = None,
        master_resume: dict | None = None,
        rewritten_bullets: list[dict] | None = None,
    ) -> tuple[bool, list[dict]]:
        checks: list[dict] = []
        html = html_path.read_text(encoding="utf-8")
        text = self._html_to_text(html)

        checks.append(self._check("html_exists", html_path.exists(), str(html_path)))
        checks.append(self._check("no_template_tokens", "{{" not in html and "{%" not in html, "No unresolved template tokens"))
        checks.append(self._check("has_contact_email", "@" in text, "Email visible in resume text"))

        lowered = text.lower()
        for section in self.REQUIRED_SECTIONS:
            passed = section in lowered
            detail = section
            if section == "key projects" and not passed:
                passed = "research & publications" in lowered
                detail = "key projects or research & publications"
            checks.append(self._check(f"section_{section.replace(' ', '_')}", passed, detail))

        for term in self.REQUIRED_TERMS:
            checks.append(self._check(f"term_{self._slug(term)}", term.lower() in lowered, term))

        checks.append(self._check("reasonable_length", 360 <= len(text.split()) <= 950, f"{len(text.split())} words"))
        checks.append(self._check("ats_safe_links", "javascript:" not in lowered and "data:" not in lowered, "No unsafe embedded links"))
        checks.append(self._check_xyz_bullets(html))
        checks.append(self._check_metric_density(html))

        if master_resume is not None and rewritten_bullets:
            checks.extend(self._validate_rewritten_metrics(master_resume, rewritten_bullets))

        if pdf_path is not None:
            checks.append(self._check("pdf_exists", pdf_path.exists(), str(pdf_path)))
            if pdf_path.exists():
                checks.append(self._check("pdf_nonempty", pdf_path.stat().st_size > 10_000, f"{pdf_path.stat().st_size} bytes"))
                pdf_text = self._extract_pdf_text(pdf_path)
                if pdf_text is None:
                    checks.append(self._check("pdf_text_extractable", True, "PDF text extraction library unavailable; skipped"))
                else:
                    checks.append(self._check("pdf_text_extractable", len(pdf_text.split()) > 300, f"{len(pdf_text.split())} words extracted"))
                    checks.append(self._check("pdf_contains_name", "akhilesh" in pdf_text.lower(), "Name found in PDF text"))

        return all(item["passed"] for item in checks), checks

    def _validate_rewritten_metrics(self, master_resume: dict, rewritten_bullets: list[dict]) -> list[dict]:
        source_text = str(master_resume) + "\n" + str(ProfileEvidenceService().build_prompt_context(max_chars=60000))
        source_numbers = set(re.findall(r"\d+(?:\.\d+)?%?|\d+\.\d+", source_text))
        checks = []

        for index, item in enumerate(rewritten_bullets):
            rewritten = item.get("rewritten", "")
            numbers = set(re.findall(r"\d+(?:\.\d+)?%?|\d+\.\d+", rewritten))
            unsupported = sorted(number for number in numbers if number not in source_numbers)
            checks.append(
                self._check(
                    f"rewritten_bullet_{index + 1}_metrics_supported",
                    not unsupported,
                    f"Unsupported metrics: {', '.join(unsupported)}" if unsupported else "Metrics supported",
                )
            )
            original_numbers = self._numbers_in_text(str(item.get("original", "")))
            rewritten_numbers = self._numbers_in_text(str(rewritten))
            missing_original = sorted(original_numbers - rewritten_numbers)
            checks.append(
                self._check(
                    f"rewritten_bullet_{index + 1}_metrics_preserved",
                    not missing_original,
                    (
                        f"Missing original metrics: {', '.join(missing_original)}"
                        if missing_original
                        else "Original metrics preserved"
                    ),
                )
            )

        return checks

    def _check_metric_density(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        bullets = [item.get_text(" ", strip=True) for item in soup.find_all("li")]
        substantive = [bullet for bullet in bullets if len(bullet.split()) >= 8]
        metric_bullets = [bullet for bullet in substantive if self._numbers_in_text(bullet)]
        required = min(4, max(2, int(len(substantive) * 0.35)))
        return self._check(
            "numeric_evidence_density",
            len(metric_bullets) >= required,
            f"{len(metric_bullets)}/{len(substantive)} substantive bullets include numbers",
        )

    def _check_xyz_bullets(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        bullets = [item.get_text(" ", strip=True) for item in soup.find_all("li")]
        substantive = [bullet for bullet in bullets if len(bullet.split()) >= 8]
        if not substantive:
            return self._check("xyz_bullet_shape", False, "No substantive resume bullets found")
        strong = [bullet for bullet in substantive if self._looks_like_xyz_bullet(bullet)]
        required = max(1, int(len(substantive) * 0.75))
        return self._check(
            "xyz_bullet_shape",
            len(strong) >= required,
            f"{len(strong)}/{len(substantive)} bullets include outcome, explicit evidence, and method",
        )

    @staticmethod
    def _looks_like_xyz_bullet(text: str) -> bool:
        lowered = text.lower().strip()
        if any(phrase in lowered for phrase in ("responsible for", "worked on", "helped with")):
            return False
        evidence_markers = (
            "as measured by",
            "as evidenced by",
            "measured by",
            "evidenced by",
            "validated by",
            "shown by",
        )
        outcome_markers = (
            "achieved",
            "enabled",
            "improved",
            "delivered",
            "designed",
            "built",
            "quantified",
            "reduced",
            "supported",
            "produced",
            "created",
            "increased",
            "validated",
            "translated",
            "optimized",
            "deployed",
            "predicted",
            "connected",
            "reached",
            "informed",
        )
        has_method = " by " in lowered
        has_evidence = any(marker in lowered for marker in evidence_markers)
        has_outcome = lowered.startswith(outcome_markers)
        return has_outcome and has_evidence and has_method

    @staticmethod
    def _numbers_in_text(text: str) -> set[str]:
        return set(re.findall(r"\d+(?:\.\d+)?%?", text))

    @staticmethod
    def _extract_pdf_text(pdf_path: Path) -> str | None:
        try:
            from pypdf import PdfReader
        except ImportError:
            return None

        reader = PdfReader(str(pdf_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    @staticmethod
    def _html_to_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(" ", strip=True)

    @staticmethod
    def _check(name: str, passed: bool, detail: str) -> dict:
        return {"name": name, "passed": bool(passed), "detail": detail}

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
