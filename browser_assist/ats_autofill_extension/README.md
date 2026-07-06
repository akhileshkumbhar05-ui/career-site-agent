# CareerSite Third Eye Watcher

A local unpacked Chrome/Edge/Brave extension that watches whatever job or application page you are on, asks the local CareerSite API (powered by Claude) to understand it, and suggests safe field fills. It has no toolbar popup and no hardcoded field logic of its own. It fills only when you click, and never clicks submit.

## What it does

On any page it looks at, the watcher continuously (SPA-aware) sends the page text and form fields to the local API, which classifies the page and responds:

- **Page type** — job description, application form, both, confirmation, or other (ATS-agnostic; works the same on Greenhouse, Lever, Ashby, Workday, iCIMS, Jobvite, Zoho, custom sites).
- **Understood JD** — company, role, location, key requirements, and any work-visa-sponsorship note.
- **Field suggestions** — answers for safe fields (name, email, phone, location, LinkedIn/GitHub, US work authorization, relocation) plus short, JD-grounded answers for free-text questions, all built from your saved profile and the live JD.

A "Third Eye" panel appears top-right showing the understood JD and the suggested fills. Two buttons:

- **Fill safe fields** — applies the suggested safe fills to the page. Fill-on-click only.
- **Choose tailoring style** — lets you direct Claude before generating the draft. Choose balanced, technical depth, business impact, projects first, experience first, or minimal edits; set rewrite strength; choose section emphasis including Research papers; type bullet counts per subsection for Experience roles, Projects, and Research papers; and add a short custom instruction.
- **Create tailored draft** — spends one Claude call and opens an editable review inside Third Eye. It does not create resume files yet.
- **Review Claude draft** — edit the summary and individual rewrites, reject a rewrite to restore its verified original, drag selected projects into the preferred order when Projects is enabled, include or remove selected research papers when Research papers is enabled, and change per-subsection bullet counts before previewing, regenerating, or generating files.
- **Approve and generate DOCX + PDF** — renders locally without another Claude call. Download buttons use the browser Save As dialog.
- **Regenerate draft** — clearly warns before spending another Claude call.

These are always left to you and are never auto-filled: EEO/demographic, citizenship/security-clearance, salary/compensation, SSN/date of birth, passwords, signatures, resume upload, and the final submit button.

## Install locally

1. Open extensions: Chrome `chrome://extensions`, Edge `edge://extensions`, Brave `brave://extensions`.
2. Turn on Developer mode.
3. Choose `Load unpacked` and select this folder:

```text
....\career-site-agent\browser_assist\ats_autofill_extension
```

After updating the code, click the reload icon on the extension card to pick up changes.

## Use

1. Keep the CareerSite backend running at `http://127.0.0.1:8000` (it also falls back to `8001`). The Anthropic key loads automatically.
2. Browse to any job posting or application page. The Third Eye panel appears automatically when the page looks like a job/application page.
3. On a JD page: review the understood job, click **Choose tailoring style**, set your preferences, then click **Create tailored draft**.
4. Edit and approve the draft in Third Eye. Rejected bullet rewrites automatically restore their verified originals.
5. Review any selected projects or research papers, click **Approve and generate DOCX + PDF**, then download either format to your chosen location.

Tailoring defaults are stored locally by role family. Each job can override them. Local preference storage, review actions, rendering, downloads, and the audit trail do not consume Claude tokens.
4. On an application page: click **Fill safe fields**, then review everything, answer the sensitive/manual questions yourself, upload your resume, and submit manually.

Tailored resume artifacts and apply plans are written under:

```text
....\career-site-agent\data\outputs\autofill_packets
```

## Notes

- The watcher only calls the API on pages that look like job/application pages (ATS domains, pages with form fields, or pages with job-description text), so it does not fire on ordinary browsing.
- All page understanding and field answering happen server-side via Claude; the content script only reads the DOM, renders suggestions, and fills on click.
- Third Eye can now arm an apply assistant after you approve a tailored packet. It opens the application URL and fills only safe matched fields. Final submit always stays manual.
