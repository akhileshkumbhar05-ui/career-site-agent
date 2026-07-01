# Tailoring Rules

## Allowed
- reorder bullets
- prioritize relevant projects
- switch summary variant
- rewrite wording for clarity
- select only projects and skills already present in `data/master_resume/master_resume.json`
- use evidence from `Profile/Instructions.txt`, `Profile/* Summary.txt`, and Profile project/research artifacts when the JD has a clear connection
- create DOCX/HTML/PDF resume artifacts for review
- create an apply plan for safe browser form filling
- filter the technical skills section to JD-relevant, role-relevant, and evidence-backed skills instead of dumping the full master skill bank
- merge rewritten bullets with original evidence bullets so a weak or partial rewrite cannot erase useful verified experience

## Forbidden
- invent skills
- invent experience
- change metrics without support
- expose or send GitHub access links, tokens, API keys, or other credentials to LLM prompts or generated artifacts
- imply production scope not present in the source resume
- answer EEO, salary, citizenship/security-clearance, signature, or final-submit fields automatically
- claim sponsorship safety when the JD says OPT, CPT, STEM OPT, H-1B, visa sponsorship, citizenship, or clearance is restricted

## Review Boundary
- Tailored resumes are drafts until Akhilesh reviews them.
- Browser autofill may fill high-confidence profile fields, but resume upload and final submit stay manual.
- If the current page is only an application form and not a full job description, the system should use saved profile answers instead of generating a tailored resume from incomplete context.
- `Profile/` is local project knowledge. Public GitHub and LinkedIn profile URLs may appear in resumes; private access links must stay local-only.
- If Claude or the fallback scorer estimates the role below the tailoring threshold, the system should return a clear "not generated" message instead of creating a weak tailored resume artifact.
- Empty optional sections, such as publications, should be omitted from rendered resumes.
