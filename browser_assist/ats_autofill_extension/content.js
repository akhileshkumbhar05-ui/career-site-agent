(() => {
  if (window.__careerSiteWatcherLoaded) return;
  window.__careerSiteWatcherLoaded = true;

  // ------------------------------------------------------------------
  // CareerSite "Third Eye" watcher.
  // The page sends its text + form fields to the local CareerSite API,
  // which uses Claude to classify the page, understand the JD, and
  // propose field answers. This content script does NO hardcoded field
  // matching of its own. It only extracts the DOM, renders suggestions,
  // and fills on click. It never clicks submit.
  // ------------------------------------------------------------------

  const ATS_URL_HINTS = [
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com", "icims.com",
    "smartrecruiters.com", "jobvite.com", "workable.com", "breezy.hr", "bamboohr.com",
    "taleo.net", "successfactors.com", "oraclecloud.com", "eightfold.ai", "zohorecruit",
    "ripplematch", "jobright", "linkedin.com/jobs", "indeed.com",
    "jobs.", "careers.", "/careers", "/jobs", "/apply", "apply.",
  ];
  const JD_TEXT_HINTS = [
    "responsibilities", "qualifications", "what you'll do", "what you will do",
    "about the role", "job description", "minimum qualifications", "preferred qualifications",
  ];

  let watcherTimer = null;
  let watcherBusy = false;
  let watcherLastSignature = "";

  installWatcher();

  function installWatcher() {
    const wrap = (type) => {
      const original = history[type];
      return function patched() {
        const result = original.apply(this, arguments);
        window.dispatchEvent(new Event("careersite:navigation"));
        return result;
      };
    };
    history.pushState = wrap("pushState");
    history.replaceState = wrap("replaceState");
    window.addEventListener("popstate", () => scheduleObserve(600));
    window.addEventListener("careersite:navigation", () => scheduleObserve(900));

    const observer = new MutationObserver(() => scheduleObserve(1500));
    if (document.body) observer.observe(document.body, { childList: true, subtree: true });

    scheduleObserve(1400);
  }

  function isDevUrl() {
    return /^https?:\/\/(localhost|127\.0\.0\.1):(5173|8000|8001|8501)/i.test(window.location.href);
  }

  function scheduleObserve(delay) {
    if (isDevUrl()) return;
    clearTimeout(watcherTimer);
    watcherTimer = setTimeout(runObserve, delay || 1200);
  }

  async function runObserve() {
    if (watcherBusy) return;
    const fields = watcherFieldPayload();
    if (!looksLikeJobPage(fields)) return;
    const pageText = extractPageText();
    const signature = `${window.location.href}::${fields.length}::${pageText.length >> 9}`;
    if (signature === watcherLastSignature) return;
    watcherLastSignature = signature;

    watcherBusy = true;
    try {
      const result = await sendRuntimeMessage({
        action: "CAREERSITE_WATCH",
        payload: {
          url: window.location.href,
          page_title: document.title || "",
          page_text: pageText,
          form_fields: fields,
        },
      });
      if (result && !result.error && result.page_type) {
        const autopilot = await sendRuntimeMessage({
          action: "CAREERSITE_AUTOPILOT_CONTEXT",
          payload: {
            url: window.location.href,
            page_title: document.title || "",
            page_text: pageText,
          },
        });
        if (autopilot && !autopilot.error) result.autopilot = autopilot;
        renderWatcherPanel(result);
      }
    } finally {
      watcherBusy = false;
    }
  }

  function looksLikeJobPage(fields) {
    const url = window.location.href.toLowerCase();
    if (ATS_URL_HINTS.some((hint) => url.includes(hint))) return true;
    const fillable = fields.filter(
      (field) => !["hidden", "submit", "button", "search", "reset", "image"].includes(field.input_type)
    );
    if (fillable.length >= 2) return true;
    const text = (document.body?.innerText || "").toLowerCase().slice(0, 6000);
    return JD_TEXT_HINTS.some((hint) => text.includes(hint));
  }

  function extractPageText() {
    const main = document.querySelector("main") || document.querySelector("[role='main']") || document.body;
    return cleanText((main?.innerText || document.body.innerText || "").slice(0, 30000));
  }

  // ----- DOM field extraction (no answer logic here) -----

  function watcherFieldPayload() {
    return extractFields().map((field) => ({
      field_id: field.fieldId,
      selector: field.selector,
      tag: field.tag,
      input_type: field.inputType,
      label: field.label,
      name: field.name,
      id_attr: field.idAttr,
      placeholder: field.placeholder,
      aria_label: field.ariaLabel,
      required: field.required,
      options: field.options,
      context: field.context,
    }));
  }

  function extractFields() {
    const fields = [];
    const radioGroups = new Map();
    const controls = document.querySelectorAll("input, select, textarea");
    controls.forEach((element, index) => {
      const inputType = (element.getAttribute("type") || element.tagName || "").toLowerCase();
      if (["hidden", "submit", "button", "reset", "image"].includes(inputType)) return;
      if (inputType === "radio") {
        const name = element.getAttribute("name") || element.id || `radio_${index}`;
        if (!radioGroups.has(name)) radioGroups.set(name, []);
        radioGroups.get(name).push(element);
        return;
      }
      fields.push(fieldFromElement(element, fields.length + 1));
    });

    for (const [name, elements] of radioGroups.entries()) {
      fields.push(fieldFromRadioGroup(name, elements, fields.length + 1));
    }
    return fields;
  }

  function fieldFromElement(element, index) {
    const fieldId = element.id || element.name || `${element.tagName.toLowerCase()}_${index}`;
    element.dataset.careersiteFieldId = fieldId;
    return {
      fieldId,
      selector: selectorFor(element),
      tag: element.tagName.toLowerCase(),
      inputType: (element.getAttribute("type") || element.tagName || "").toLowerCase(),
      label: labelFor(element),
      name: element.getAttribute("name") || "",
      idAttr: element.id || "",
      placeholder: element.getAttribute("placeholder") || "",
      ariaLabel: element.getAttribute("aria-label") || "",
      required: element.required || element.getAttribute("aria-required") === "true",
      options: element.tagName.toLowerCase() === "select" ? selectOptions(element) : [],
      context: contextFor(element),
    };
  }

  function fieldFromRadioGroup(name, elements, index) {
    const groupLabel = radioGroupLabel(elements[0]);
    const options = elements.map((element) => labelFor(element) || element.value).filter(Boolean);
    elements.forEach((element) => {
      element.dataset.careersiteFieldId = `radio_${name}_${index}`;
    });
    return {
      fieldId: `radio:${name || index}`,
      selector: `input[type="radio"][name="${cssEscape(name)}"]`,
      tag: "input",
      inputType: "radio_group",
      label: groupLabel || options.join(" / "),
      name,
      idAttr: "",
      placeholder: "",
      ariaLabel: "",
      required: elements.some((element) => element.required),
      options,
      context: contextFor(elements[0]),
    };
  }

  // ----- Panel + fill-on-click -----

  function watcherEscape(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (char) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]
    ));
  }

  function renderWatcherPanel(result) {
    const existing = document.getElementById("careersite-watcher-panel");
    if (existing) existing.remove();

    const suggestions = Array.isArray(result.field_suggestions) ? result.field_suggestions : [];
    const fillable = suggestions.filter(
      (item) => !item.sensitive && ["fill_text", "select_option", "choose_radio"].includes(item.action)
    );
    const sensitiveCount = suggestions.filter((item) => item.sensitive).length;

    const typeLabels = {
      job_description: "Job description",
      application_form: "Application form",
      both: "JD + application",
      confirmation: "Confirmation",
      other: "Other page",
    };
    const typeColor = result.page_type === "other" ? "#808080" : "#e50914";

    const panel = document.createElement("div");
    panel.id = "careersite-watcher-panel";
    panel.style.cssText = [
      "position:fixed", "top:16px", "right:16px", "z-index:2147483647", "width:min(440px, calc(100vw - 32px))",
      "max-height:80vh", "overflow:auto", "padding:14px 15px", "border-radius:12px",
      "background:#181818", "color:#fff", "border:1px solid rgba(255,255,255,.14)",
      "box-shadow:0 20px 50px rgba(0,0,0,.55)", "font:13px/1.5 Arial, sans-serif",
    ].join(";");

    let html = `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px;">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="width:22px;height:22px;border-radius:6px;background:#e50914;display:inline-flex;align-items:center;justify-content:center;font-weight:900;">C</span>
          <strong style="font-size:13px;letter-spacing:.02em;">Third Eye</strong>
        </div>
        <button data-cs="close" style="background:transparent;border:0;color:#b3b3b3;font-size:18px;cursor:pointer;line-height:1;">&times;</button>
      </div>
      <div style="display:inline-flex;align-items:center;gap:6px;background:rgba(255,255,255,.06);border:1px solid ${typeColor};color:#fff;border-radius:999px;padding:3px 10px;font-size:11px;font-weight:700;margin-bottom:8px;">
        ${watcherEscape(typeLabels[result.page_type] || result.page_type)} &middot; ${watcherEscape(result.engine)}
      </div>`;

    const jd = result.jd;
    const capturedPageText = extractPageText();
    const discoverySource = inferDiscoverySource(window.location.href);
    const closeoutAvailable = result.page_type === "confirmation" || (
      ["application_form", "both"].includes(result.page_type) && result.autopilot?.enabled
    );
    if (closeoutAvailable) {
      const closeoutAutomatic = result.page_type === "confirmation";
      html += `
        <div data-cs="closeout" style="padding:10px 0;border-top:1px solid rgba(255,255,255,.12);border-bottom:1px solid rgba(255,255,255,.12);margin-bottom:8px;">
          <strong style="display:block;font-size:13px;">${closeoutAutomatic ? "Close out this application" : "Application outcome"}</strong>
          ${closeoutAutomatic ? "" : `<button data-cs="closeout-toggle" style="margin-top:7px;width:100%;border:1px solid #666;border-radius:6px;padding:7px;background:#303030;color:#fff;font-weight:700;cursor:pointer;">Review application outcome</button>`}
          <div data-cs="closeout-status" style="margin-top:5px;color:#b3b3b3;font-size:11px;">${closeoutAutomatic ? "Matching this confirmation to the open ATS job..." : ""}</div>
          <div data-cs="closeout-review"${closeoutAutomatic ? "" : " hidden"}></div>
        </div>`;
    }
    if (jd && (jd.role || jd.company)) {
      const reqs = (jd.key_requirements || []).slice(0, 4)
        .map((req) => `<li style="margin:0 0 2px;">${watcherEscape(req)}</li>`).join("");
      html += `
        <div style="background:#232323;border:1px solid rgba(255,255,255,.1);border-radius:9px;padding:10px;margin-bottom:8px;">
          <div style="font-weight:700;font-size:13px;">${watcherEscape(jd.role || "Role")}</div>
          <div style="color:#b3b3b3;font-size:12px;">${watcherEscape(jd.company || "")}${jd.location ? " &middot; " + watcherEscape(jd.location) : ""}</div>
          ${jd.sponsorship_note ? `<div style="margin-top:6px;color:#f5c518;font-size:12px;">${watcherEscape(jd.sponsorship_note)}</div>` : ""}
          ${reqs ? `<ul style="margin:8px 0 0;padding-left:16px;color:#d6d6d6;font-size:12px;">${reqs}</ul>` : ""}
          <button data-cs="intake-toggle" style="margin-top:10px;width:100%;border:0;border-radius:6px;padding:8px;background:#e50914;color:#fff;font-weight:700;cursor:pointer;">Review and add job</button>
          <div data-cs="intake-options" hidden style="margin-top:8px;padding-top:9px;border-top:1px solid rgba(255,255,255,.12);">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:7px;">
              <label style="display:block;color:#b3b3b3;font-size:11px;">Company
                <input data-cs-intake="company" value="${watcherEscape(jd.company || "")}" style="display:block;width:100%;margin-top:3px;padding:6px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;box-sizing:border-box;">
              </label>
              <label style="display:block;color:#b3b3b3;font-size:11px;">Role
                <input data-cs-intake="role" value="${watcherEscape(jd.role || "")}" style="display:block;width:100%;margin-top:3px;padding:6px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;box-sizing:border-box;">
              </label>
            </div>
            <label style="display:block;margin-top:7px;color:#b3b3b3;font-size:11px;">Discovery source
              <select data-cs-intake="source" style="display:block;width:100%;margin-top:3px;padding:6px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;box-sizing:border-box;">
                ${intakeSourceOptions(discoverySource)}
              </select>
            </label>
            <label style="display:block;margin-top:7px;color:#b3b3b3;font-size:11px;">Job URL
              <input data-cs-intake="job_url" value="${watcherEscape(window.location.href)}" style="display:block;width:100%;margin-top:3px;padding:6px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;box-sizing:border-box;">
            </label>
            <label style="display:block;margin-top:7px;color:#b3b3b3;font-size:11px;">Job description
              <textarea data-cs-intake="jd_text" rows="5" maxlength="100000" style="display:block;width:100%;margin-top:3px;padding:6px;resize:vertical;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;font:11px/1.4 Arial,sans-serif;box-sizing:border-box;"></textarea>
            </label>
            <div style="margin-top:8px;color:#b3b3b3;font-size:11px;">Destination</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:4px;">
              <label style="display:flex;align-items:center;gap:6px;padding:7px;border:1px solid #555;border-radius:6px;color:#fff;font-size:11px;cursor:pointer;">
                <input data-cs-destination="active_sprint" name="careersite-intake-destination" type="radio" value="active_sprint" checked> Active sprint
              </label>
              <label style="display:flex;align-items:center;gap:6px;padding:7px;border:1px solid #555;border-radius:6px;color:#fff;font-size:11px;cursor:pointer;">
                <input data-cs-destination="inbox" name="careersite-intake-destination" type="radio" value="inbox"> Batch Inbox
              </label>
            </div>
            <div data-cs="intake-review-status" style="margin-top:7px;color:#b3b3b3;font-size:11px;"></div>
            <div style="display:grid;grid-template-columns:1fr 1.4fr;gap:6px;margin-top:8px;">
              <button data-cs="intake-review" style="border:1px solid #666;border-radius:6px;padding:7px;background:#303030;color:#fff;font-weight:700;cursor:pointer;">Check details</button>
              <button data-cs="intake-commit" disabled style="border:0;border-radius:6px;padding:7px;background:#e50914;color:#fff;font-weight:700;cursor:pointer;">Add to active sprint</button>
            </div>
          </div>
          <button data-cs="tailor-toggle" style="margin-top:10px;width:100%;border:1px solid rgba(255,255,255,.16);border-radius:6px;padding:8px;background:#303030;color:#fff;font-weight:700;cursor:pointer;">Choose tailoring style</button>
          <div data-cs="tailor-options" hidden style="margin-top:8px;padding:9px;background:#191919;border:1px solid rgba(255,255,255,.1);border-radius:7px;">
            <label style="display:block;color:#b3b3b3;font-size:11px;margin-bottom:7px;">
              Style
              <select data-cs="tailor-preset" style="display:block;width:100%;margin-top:3px;padding:6px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;">
                <option value="balanced">Balanced</option>
                <option value="technical_depth">Technical depth</option>
                <option value="business_impact">Business impact</option>
                <option value="projects_first">Projects first</option>
                <option value="experience_first">Experience first</option>
                <option value="minimal_edits">Minimal edits</option>
              </select>
            </label>
            <label style="display:block;color:#b3b3b3;font-size:11px;margin-bottom:7px;">
              Rewrite strength
              <select data-cs="tailor-intensity" style="display:block;width:100%;margin-top:3px;padding:6px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;">
                <option value="light">Light</option>
                <option value="balanced" selected>Balanced</option>
                <option value="strong">Strong alignment</option>
              </select>
            </label>
            <div style="color:#b3b3b3;font-size:11px;margin-bottom:4px;">Emphasize</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 8px;margin-bottom:7px;color:#e0e0e0;font-size:11px;">
              <label><input data-cs-emphasis="summary" type="checkbox" checked> Summary</label>
              <label><input data-cs-emphasis="experience" type="checkbox" checked> Experience</label>
              <label><input data-cs-emphasis="projects" type="checkbox" checked> Projects</label>
              <label><input data-cs-emphasis="skills" type="checkbox" checked> Skills</label>
              <label><input data-cs-emphasis="research_papers" type="checkbox"> Research papers</label>
            </div>
            <div style="color:#b3b3b3;font-size:11px;margin-bottom:4px;">Bullets per subsection</div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:7px;">
              <label style="display:block;color:#d6d6d6;font-size:10px;">Experience
                <input data-cs-count="experience_per_role" type="number" min="0" step="1" value="3" style="display:block;width:100%;margin-top:3px;padding:5px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;">
              </label>
              <label style="display:block;color:#d6d6d6;font-size:10px;">Projects
                <input data-cs-count="projects_per_project" type="number" min="0" step="1" value="2" style="display:block;width:100%;margin-top:3px;padding:5px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;">
              </label>
              <label style="display:block;color:#d6d6d6;font-size:10px;">Research
                <input data-cs-count="research_per_paper" type="number" min="0" step="1" value="2" style="display:block;width:100%;margin-top:3px;padding:5px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;">
              </label>
            </div>
            <label style="display:flex;align-items:center;gap:5px;color:#e0e0e0;font-size:11px;margin-bottom:7px;">
              <input data-cs="tailor-note" type="checkbox" checked>
              Include recruiter connection note
            </label>
            <label style="display:flex;align-items:center;gap:5px;color:#e0e0e0;font-size:11px;margin-bottom:7px;">
              <input data-cs="tailor-cover-letter" type="checkbox">
              Include cover letter draft
            </label>
            <label style="display:block;color:#b3b3b3;font-size:11px;">
              Additional direction
              <textarea data-cs="tailor-instructions" maxlength="600" rows="3" placeholder="Example: keep my original project bullets unless a rewrite clearly improves relevance." style="display:block;width:100%;margin-top:3px;padding:6px;resize:vertical;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;font:11px/1.4 Arial,sans-serif;box-sizing:border-box;"></textarea>
            </label>
            <div style="margin-top:5px;color:#777;font-size:10px;">Claude may change emphasis and wording only. Evidence, metrics, and eligibility guardrails stay fixed.</div>
            <button data-cs="tailor" style="margin-top:9px;width:100%;border:0;border-radius:6px;padding:8px;background:#e50914;color:#fff;font-weight:700;cursor:pointer;">Create tailored draft</button>
          </div>
          <div data-cs="tailor-status" style="margin-top:6px;color:#b3b3b3;font-size:11px;"></div>
          <div data-cs="tailor-review"></div>
        </div>`;
    }

    if (fillable.length || result.page_type === "application_form" || result.page_type === "both") {
      const rows = fillable.slice(0, 6).map((item) => `
        <div style="display:flex;justify-content:space-between;gap:8px;padding:3px 0;border-bottom:1px solid rgba(255,255,255,.06);">
          <span style="color:#b3b3b3;">${watcherEscape(item.label || item.field_id)}</span>
          <span style="color:#fff;text-align:right;max-width:55%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${watcherEscape(item.target_option || item.value)}</span>
        </div>`).join("");
      html += `
        <div style="margin-bottom:6px;">
          <div style="font-size:12px;color:#b3b3b3;margin-bottom:6px;">
            ${fillable.length} safe field${fillable.length === 1 ? "" : "s"} ready &middot; ${sensitiveCount} left to you
          </div>
          ${rows}
          ${fillable.length ? `<button data-cs="fill" style="margin-top:10px;width:100%;border:0;border-radius:6px;padding:8px;background:#e50914;color:#fff;font-weight:700;cursor:pointer;">Fill ${fillable.length} safe field${fillable.length === 1 ? "" : "s"}</button>` : ""}
          <div data-cs="fill-status" style="margin-top:6px;color:#b3b3b3;font-size:11px;"></div>
        </div>`;
    }

    html += `<div style="color:#808080;font-size:10.5px;margin-top:4px;">Suggestions only. Sensitive fields and final submit stay with you.</div>`;
    panel.innerHTML = html;
    const intakeJd = panel.querySelector('[data-cs-intake="jd_text"]');
    if (intakeJd) intakeJd.value = capturedPageText;

    panel.querySelector('[data-cs="close"]')?.addEventListener("click", () => panel.remove());
    panel.querySelector('[data-cs="fill"]')?.addEventListener("click", () => {
      const filled = applyWatcherSuggestions(fillable, false);
      const status = panel.querySelector('[data-cs="fill-status"]');
      if (status) status.textContent = `Filled ${filled} field${filled === 1 ? "" : "s"}. Review before submitting.`;
    });
    panel.querySelector('[data-cs="intake-toggle"]')?.addEventListener("click", async () => {
      const options = panel.querySelector('[data-cs="intake-options"]');
      const toggle = panel.querySelector('[data-cs="intake-toggle"]');
      if (!options || !toggle) return;
      options.hidden = !options.hidden;
      toggle.textContent = options.hidden ? "Review and add job" : "Hide job intake";
      if (!options.hidden) await reviewThirdEyeIntake(panel);
    });
    panel.querySelector('[data-cs="intake-review"]')?.addEventListener("click", async () => {
      await reviewThirdEyeIntake(panel);
    });
    panel.querySelector('[data-cs="intake-commit"]')?.addEventListener("click", async () => {
      await commitThirdEyeIntake(panel);
    });
    panel.querySelectorAll("[data-cs-intake]").forEach((input) => {
      input.addEventListener("input", () => invalidateIntakeReview(panel));
      input.addEventListener("change", () => invalidateIntakeReview(panel));
    });
    panel.querySelectorAll("[data-cs-destination]").forEach((input) => {
      input.addEventListener("change", () => updateIntakeCommitButton(panel));
    });
    panel.querySelector('[data-cs="tailor-toggle"]')?.addEventListener("click", () => {
      const options = panel.querySelector('[data-cs="tailor-options"]');
      const toggle = panel.querySelector('[data-cs="tailor-toggle"]');
      if (!options || !toggle) return;
      options.hidden = !options.hidden;
      toggle.textContent = options.hidden ? "Choose tailoring style" : "Hide tailoring options";
    });
    panel.querySelector('[data-cs="tailor"]')?.addEventListener("click", async () => {
      const status = panel.querySelector('[data-cs="tailor-status"]');
      const button = panel.querySelector('[data-cs="tailor"]');
      const preferences = readTailoringPreferences(panel);
      saveTailoringDefaults((jd && jd.role) || "", preferences);
      if (status) status.textContent = "Claude is creating your tailored draft...";
      if (button) button.disabled = true;
      const requestPayload = {
        url: window.location.href,
        page_title: document.title || "",
        page_text: extractPageText(),
        company: (jd && jd.company) || "",
        role: (jd && jd.role) || "",
        source: "watcher",
        force_prepare: true,
        render_pdf: false,
        tailoring_preferences: preferences,
      };
      const response = await sendRuntimeMessage({
        action: "CAREERSITE_TAILOR_PREVIEW",
        payload: requestPayload,
      });
      if (button) button.disabled = false;
      if (status) {
        if (response?.error) status.textContent = `Tailoring failed: ${friendlyRuntimeError(response.error)}`;
        else {
          status.textContent = response?.message || "Draft ready for review.";
          renderTailoringReview(panel, response, requestPayload);
        }
      }
    });

    document.documentElement.appendChild(panel);
    loadTailoringDefaults(panel, (jd && jd.role) || "");
    if (result.page_type === "confirmation") {
      reviewThirdEyeCloseout(panel, result);
    }
    panel.querySelector('[data-cs="closeout-toggle"]')?.addEventListener("click", async () => {
      const review = panel.querySelector('[data-cs="closeout-review"]');
      const toggle = panel.querySelector('[data-cs="closeout-toggle"]');
      if (!review || !toggle) return;
      review.hidden = !review.hidden;
      toggle.textContent = review.hidden ? "Review application outcome" : "Hide application outcome";
      if (!review.hidden && !review.hasChildNodes()) await reviewThirdEyeCloseout(panel, result);
    });
    if (result.autopilot?.enabled) {
      const filled = applyWatcherSuggestions(fillable, false);
      const status = panel.querySelector('[data-cs="fill-status"]');
      if (status) {
        status.textContent = filled
          ? `Apply assistant filled ${filled} safe field${filled === 1 ? "" : "s"}. Review before submitting.`
          : "Apply assistant found no safe fields to fill. Review the form manually.";
      }
      sendRuntimeMessage({
        action: "CAREERSITE_AUTOPILOT_RESULT",
        payload: {
          task_id: result.autopilot.task_id,
          url: window.location.href,
          filled_count: filled,
          total_fields: suggestions.length,
          fillable_count: fillable.length,
          manual_count: Number(result.manual_count || 0),
          skipped_count: Number(result.sensitive_count || 0),
          results: suggestions.slice(0, 60).map((item) => ({
            field_id: item.field_id,
            label: item.label,
            action: item.action,
            source: item.source,
            reason: item.reason,
            sensitive: Boolean(item.sensitive),
          })),
        },
      });
    }
  }

  async function reviewThirdEyeCloseout(panel, watcherResult) {
    const status = panel.querySelector('[data-cs="closeout-status"]');
    const response = await sendRuntimeMessage({
      action: "CAREERSITE_CLOSEOUT_REVIEW",
      payload: {
        loop_id: watcherResult.autopilot?.loop_id || "",
        task_id: watcherResult.autopilot?.task_id || "",
        url: window.location.href,
        page_title: document.title || "",
        page_text: extractPageText(),
      },
    });
    if (response?.error || !response?.matched) {
      if (status) {
        status.style.color = "#f5c518";
        status.textContent = response?.error
          ? `Could not prepare closeout: ${friendlyRuntimeError(response.error)}`
          : response?.reason || "Could not match this confirmation to an open application.";
      }
      return;
    }
    if (status) {
      status.style.color = "#b7e4c7";
      status.textContent = `${response.loop_item.company} - ${response.loop_item.role}. No additional Claude call.`;
    }
    renderThirdEyeCloseoutReview(panel, response);
  }

  function renderThirdEyeCloseoutReview(panel, review) {
    const container = panel.querySelector('[data-cs="closeout-review"]');
    if (!container || !review?.loop_item) return;
    const item = review.loop_item;
    const alreadySheetLogged = ["sheet_logged", "recruiter_note_ready", "outreach_done"].includes(item.state);
    const submittedRow = review.submitted_sheet_row || {};
    const source = submittedRow["Job Posted On"] || item.source || "Unknown";
    const appliedUsing = submittedRow["Applied Using"] || "Company Website";
    container.innerHTML = `
      <div style="margin-top:9px;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
          <label style="display:flex;align-items:center;gap:6px;padding:7px;border:1px solid #555;border-radius:6px;color:#fff;font-size:11px;cursor:pointer;">
            <input data-cs-closeout-outcome="submitted_confirmed" name="careersite-closeout-outcome" type="radio" value="submitted_confirmed" checked> Submitted
          </label>
          <label style="display:flex;align-items:center;gap:6px;padding:7px;border:1px solid #555;border-radius:6px;color:#fff;font-size:11px;cursor:pointer;">
            <input data-cs-closeout-outcome="technical_issue" name="careersite-closeout-outcome" type="radio" value="technical_issue"> Portal issue
          </label>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:8px;">
          <label style="display:block;color:#b3b3b3;font-size:11px;">Salary quoted
            <input data-cs-closeout="salary" value="${watcherEscape(submittedRow["Salary Quoted while Applying"] || "N/A")}" style="display:block;width:100%;margin-top:3px;padding:6px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;box-sizing:border-box;">
          </label>
          <label style="display:block;color:#b3b3b3;font-size:11px;">Discovery source
            <input data-cs-closeout="source" value="${watcherEscape(source)}" style="display:block;width:100%;margin-top:3px;padding:6px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;box-sizing:border-box;">
          </label>
        </div>
        <label style="display:block;margin-top:7px;color:#b3b3b3;font-size:11px;">Applied using
          <select data-cs-closeout="applied_using" style="display:block;width:100%;margin-top:3px;padding:6px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;box-sizing:border-box;">
            ${closeoutAppliedUsingOptions(appliedUsing)}
          </select>
        </label>
        <div style="margin-top:8px;color:#b3b3b3;font-size:11px;font-weight:700;">Canonical Sheets row</div>
        <div data-cs="closeout-row" style="margin-top:4px;padding:7px 0;border-top:1px solid rgba(255,255,255,.1);border-bottom:1px solid rgba(255,255,255,.1);"></div>
        <label data-cs="closeout-human-row" style="display:flex;align-items:flex-start;gap:6px;margin-top:8px;color:#fff;font-size:11px;font-weight:700;">
          <input data-cs-closeout="human_confirmed" type="checkbox">
          <span>I manually submitted this application and reviewed the confirmation.</span>
        </label>
        <label style="display:flex;align-items:flex-start;gap:6px;margin-top:8px;color:#e0e0e0;font-size:11px;">
          <input data-cs-closeout="log_to_sheets" type="checkbox" ${review.sheets_configured ? "checked" : "disabled"}>
          <span>${review.sheets_configured ? "Log this canonical row to Google Sheets" : "Google Sheets writer is not configured"}</span>
        </label>
        <label style="display:block;margin-top:8px;color:#b3b3b3;font-size:11px;">Confirmation note
          <textarea data-cs-closeout="note" rows="3" maxlength="1000" style="display:block;width:100%;margin-top:3px;padding:6px;resize:vertical;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;font:11px/1.4 Arial,sans-serif;box-sizing:border-box;">I reviewed the ATS confirmation page after submitting manually.</textarea>
        </label>
        <div data-cs="closeout-guard" style="margin-top:6px;color:#f5c518;font-size:10px;"></div>
        <button data-cs="closeout-commit" disabled style="margin-top:8px;width:100%;border:0;border-radius:6px;padding:8px;background:#e50914;color:#fff;font-weight:700;cursor:pointer;">Confirm submission and log</button>
        <div data-cs="closeout-result" style="margin-top:6px;color:#b3b3b3;font-size:11px;"></div>
      </div>`;
    panel.__careerSiteCloseoutReview = review;
    panel.__careerSiteCloseoutNotes = {
      submitted_confirmed: "I reviewed the ATS confirmation page after submitting manually.",
      technical_issue: "",
    };
    panel.dataset.csCloseoutOutcome = "submitted_confirmed";

    container.querySelectorAll("[data-cs-closeout-outcome]").forEach((input) => {
      input.addEventListener("change", () => switchThirdEyeCloseoutOutcome(panel));
    });
    container.querySelectorAll("[data-cs-closeout]").forEach((input) => {
      input.addEventListener("input", () => updateThirdEyeCloseoutForm(panel));
      input.addEventListener("change", () => updateThirdEyeCloseoutForm(panel));
    });
    container.querySelector('[data-cs="closeout-commit"]')?.addEventListener("click", async () => {
      await commitThirdEyeCloseout(panel);
    });
    if (alreadySheetLogged) {
      const result = container.querySelector('[data-cs="closeout-result"]');
      if (result) {
        result.style.color = "#b7e4c7";
        result.textContent = "This submitted application is already logged to Sheets.";
      }
    }
    panel.dataset.csCloseoutLocked = alreadySheetLogged ? "true" : "false";
    updateThirdEyeCloseoutForm(panel);
  }

  function switchThirdEyeCloseoutOutcome(panel) {
    const note = panel.querySelector('[data-cs-closeout="note"]');
    const notes = panel.__careerSiteCloseoutNotes || {};
    const previous = panel.dataset.csCloseoutOutcome || "submitted_confirmed";
    if (note) notes[previous] = note.value;
    const next = panel.querySelector("[data-cs-closeout-outcome]:checked")?.value || "submitted_confirmed";
    panel.dataset.csCloseoutOutcome = next;
    panel.__careerSiteCloseoutNotes = notes;
    if (note) note.value = notes[next] || "";
    updateThirdEyeCloseoutForm(panel);
  }

  function closeoutAppliedUsingOptions(selected) {
    return ["LinkedIn", "Indeed", "Company Website", "ZipRecruiter", "Jobright.ai"]
      .map((value) => `<option value="${value}"${value === selected ? " selected" : ""}>${value}</option>`)
      .join("");
  }

  function currentThirdEyeCloseoutRow(panel) {
    const review = panel.__careerSiteCloseoutReview || {};
    const outcome = panel.querySelector("[data-cs-closeout-outcome]:checked")?.value || "submitted_confirmed";
    const sourceRow = outcome === "technical_issue"
      ? review.technical_issue_sheet_row || {}
      : review.submitted_sheet_row || {};
    return {
      ...sourceRow,
      "Salary Quoted while Applying": panel.querySelector('[data-cs-closeout="salary"]')?.value.trim() || "N/A",
      "Job Posted On": panel.querySelector('[data-cs-closeout="source"]')?.value.trim() || "Unknown",
      "Applied Using": panel.querySelector('[data-cs-closeout="applied_using"]')?.value || "Company Website",
    };
  }

  function updateThirdEyeCloseoutForm(panel) {
    const row = currentThirdEyeCloseoutRow(panel);
    const outcome = panel.querySelector("[data-cs-closeout-outcome]:checked")?.value || "submitted_confirmed";
    const humanRow = panel.querySelector('[data-cs="closeout-human-row"]');
    const humanConfirmed = panel.querySelector('[data-cs-closeout="human_confirmed"]');
    const note = panel.querySelector('[data-cs-closeout="note"]');
    const logToSheets = panel.querySelector('[data-cs-closeout="log_to_sheets"]');
    const button = panel.querySelector('[data-cs="closeout-commit"]');
    const guard = panel.querySelector('[data-cs="closeout-guard"]');
    const rowContainer = panel.querySelector('[data-cs="closeout-row"]');
    if (humanRow) humanRow.style.display = outcome === "submitted_confirmed" ? "flex" : "none";
    if (note && panel.__careerSiteCloseoutNotes) panel.__careerSiteCloseoutNotes[outcome] = note.value;
    if (rowContainer) rowContainer.innerHTML = closeoutSheetRowHtml(row);

    const confirmed = outcome === "technical_issue" || Boolean(humanConfirmed?.checked);
    const noteReady = (note?.value.trim().length || 0) >= 3;
    const locked = panel.dataset.csCloseoutLocked === "true";
    if (button) {
      button.textContent = outcome === "technical_issue"
        ? (logToSheets?.checked ? "Record portal issue and log" : "Record portal issue")
        : (logToSheets?.checked ? "Confirm submission and log" : "Confirm submission");
      button.disabled = locked || !confirmed || !noteReady;
    }
    if (guard) {
      guard.textContent = outcome === "submitted_confirmed" && !humanConfirmed?.checked
        ? "Status remains unchanged until you confirm manual submission."
        : outcome === "technical_issue"
          ? "This records Not Yet Applied Due to Technical Issue, never Applied."
          : "Ready for your confirmed closeout.";
    }
  }

  function closeoutSheetRowHtml(row) {
    const columns = [
      "Date", "Company Applied", "Role", "Salary Quoted while Applying",
      "Job Posted On", "Applied Using", "Status", "Link",
    ];
    return columns.map((column) => `
      <div style="display:grid;grid-template-columns:116px minmax(0,1fr);gap:7px;padding:2px 0;font-size:10px;">
        <span style="color:#8f8f8f;">${watcherEscape(column)}</span>
        <span style="color:#e6e6e6;overflow-wrap:anywhere;">${watcherEscape(row[column] || "")}</span>
      </div>`).join("");
  }

  async function commitThirdEyeCloseout(panel) {
    const review = panel.__careerSiteCloseoutReview || {};
    const row = currentThirdEyeCloseoutRow(panel);
    const outcome = panel.querySelector("[data-cs-closeout-outcome]:checked")?.value || "submitted_confirmed";
    const button = panel.querySelector('[data-cs="closeout-commit"]');
    const resultContainer = panel.querySelector('[data-cs="closeout-result"]');
    if (button) button.disabled = true;
    if (resultContainer) {
      resultContainer.style.color = "#b3b3b3";
      resultContainer.textContent = "Recording your confirmed outcome...";
    }
    const response = await sendRuntimeMessage({
      action: "CAREERSITE_CLOSEOUT_COMMIT",
      payload: {
        loop_id: review.loop_item?.loop_id || "",
        outcome,
        note: panel.querySelector('[data-cs-closeout="note"]')?.value.trim() || "",
        human_confirmed_submission: Boolean(panel.querySelector('[data-cs-closeout="human_confirmed"]')?.checked),
        log_to_sheets: Boolean(panel.querySelector('[data-cs-closeout="log_to_sheets"]')?.checked),
        salary_quoted: row["Salary Quoted while Applying"] || "N/A",
        source: row["Job Posted On"] || "Unknown",
        applied_using: row["Applied Using"] || "Company Website",
      },
    });
    if (response?.error) {
      if (resultContainer) {
        resultContainer.style.color = "#f5c518";
        resultContainer.textContent = `Closeout failed: ${friendlyRuntimeError(response.error)}`;
      }
      if (button) button.disabled = false;
      return;
    }

    const sheetsFailed = response.sheet_result && !response.sheet_result.success;
    if (resultContainer) {
      resultContainer.style.color = sheetsFailed ? "#f5c518" : "#b7e4c7";
      resultContainer.innerHTML = `${watcherEscape(response.message)} No additional Claude call.${closeoutProgressHtml(response.progress)}`;
    }
    if (button) {
      button.textContent = sheetsFailed ? "Retry Sheets logging" : "Closeout recorded";
      button.disabled = !sheetsFailed;
    }
    if (!sheetsFailed) panel.dataset.csCloseoutLocked = "true";
  }

  function closeoutProgressHtml(progress) {
    if (!progress) return "";
    if (progress.next_company) {
      return `<div style="margin-top:5px;color:#fff;"><strong>Next:</strong> ${watcherEscape(progress.next_company)} - ${watcherEscape(progress.next_role)} &middot; ${watcherEscape(progress.next_action)}</div>`;
    }
    if (progress.outreach_unlocked) {
      return `<div style="margin-top:5px;color:#fff;"><strong>Next:</strong> Recruiter outreach batch</div>`;
    }
    return "";
  }

  function inferDiscoverySource(url) {
    const value = decodeURIComponent(String(url || "")).toLowerCase();
    if (value.includes("jobright")) return "Jobright AI";
    if (value.includes("linkedin.com")) return "LinkedIn";
    if (value.includes("indeed.com")) return "Indeed";
    if (value.includes("simplify.jobs")) return "Simplify";
    return "Company Website";
  }

  function intakeSourceOptions(selected) {
    const sources = [
      "Jobright AI", "LinkedIn", "Indeed", "Company Website", "Referral",
      "Simplify", "TikTok", "Cognizant", "Unknown",
    ];
    return sources.map((source) => (
      `<option value="${watcherEscape(source)}"${source === selected ? " selected" : ""}>${watcherEscape(source)}</option>`
    )).join("");
  }

  function readThirdEyeIntake(panel) {
    const value = (key) => (panel.querySelector(`[data-cs-intake="${key}"]`)?.value || "").trim();
    return {
      company: value("company"),
      role: value("role"),
      job_url: value("job_url"),
      jd_text: value("jd_text"),
      source: value("source") || "Unknown",
    };
  }

  async function reviewThirdEyeIntake(panel) {
    const status = panel.querySelector('[data-cs="intake-review-status"]');
    const reviewButton = panel.querySelector('[data-cs="intake-review"]');
    const commitButton = panel.querySelector('[data-cs="intake-commit"]');
    panel.dataset.csIntakeReviewed = "false";
    if (status) {
      status.style.color = "#b3b3b3";
      status.textContent = "Checking the canonical link, duplicate history, and sprint capacity...";
    }
    if (reviewButton) reviewButton.disabled = true;
    if (commitButton) commitButton.disabled = true;

    const response = await sendRuntimeMessage({
      action: "CAREERSITE_INTAKE_REVIEW",
      payload: readThirdEyeIntake(panel),
    });
    if (reviewButton) reviewButton.disabled = false;
    if (response?.error || !response?.valid) {
      if (status) {
        status.style.color = "#f5c518";
        status.textContent = response?.error
          ? `Could not check this job: ${friendlyRuntimeError(response.error)}`
          : response?.reason || "Company and role are required before this job can be added.";
      }
      return;
    }

    const normalized = response.normalized_item || {};
    for (const key of ["company", "role", "job_url", "jd_text", "source"]) {
      const input = panel.querySelector(`[data-cs-intake="${key}"]`);
      if (input && normalized[key] != null) input.value = normalized[key];
    }

    const activeSprint = panel.querySelector('[data-cs-destination="active_sprint"]');
    const inbox = panel.querySelector('[data-cs-destination="inbox"]');
    const canUseSprint = Boolean(response.sprint?.accepts_items || response.already_in_current_sprint);
    if (activeSprint) activeSprint.disabled = !canUseSprint;
    const destination = response.recommended_destination === "active_sprint" && canUseSprint
      ? activeSprint
      : inbox;
    if (destination) destination.checked = true;

    let message = "Ready to add to the Batch Inbox.";
    if (response.already_in_current_sprint) {
      message = `Already in ${response.sprint.name}.`;
    } else if (response.existing_loop_item && response.sprint?.accepts_items) {
      message = `${response.duplicate_reason} It can still be added to ${response.sprint.name}.`;
    } else if (response.existing_loop_item) {
      message = response.duplicate_reason || "This job is already in the Batch Inbox.";
    } else if (response.sprint?.accepts_items) {
      message = `${response.sprint.name}: ${response.sprint.open_slots} open slot${response.sprint.open_slots === 1 ? "" : "s"}.`;
    } else if (response.sprint?.status === "completed") {
      message = `${response.sprint.name} is complete. This job will go to the Batch Inbox.`;
    } else if (response.sprint) {
      message = `${response.sprint.name} has no open slots. This job will go to the Batch Inbox.`;
    }
    if (response.canonical_job_url && response.canonical_job_url !== normalized.job_url) {
      message += " Tracking parameters will be removed from the saved URL.";
    }
    if (status) {
      status.style.color = response.already_in_current_sprint ? "#f5c518" : "#b7e4c7";
      status.textContent = `${message} No Claude call.`;
    }
    panel.dataset.csIntakeReviewed = "true";
    panel.dataset.csIntakeAlreadyInSprint = response.already_in_current_sprint ? "true" : "false";
    updateIntakeCommitButton(panel);
  }

  function invalidateIntakeReview(panel) {
    if (panel.dataset.csIntakeReviewed !== "true") return;
    panel.dataset.csIntakeReviewed = "false";
    panel.dataset.csIntakeAlreadyInSprint = "false";
    const commitButton = panel.querySelector('[data-cs="intake-commit"]');
    const status = panel.querySelector('[data-cs="intake-review-status"]');
    if (commitButton) commitButton.disabled = true;
    if (status) {
      status.style.color = "#f5c518";
      status.textContent = "Details changed. Check them again before adding.";
    }
  }

  function updateIntakeCommitButton(panel) {
    const button = panel.querySelector('[data-cs="intake-commit"]');
    if (!button) return;
    const destination = panel.querySelector('[data-cs-destination]:checked')?.value || "inbox";
    const alreadyInSprint = panel.dataset.csIntakeAlreadyInSprint === "true";
    button.textContent = alreadyInSprint
      ? "Already in active sprint"
      : destination === "active_sprint" ? "Add to active sprint" : "Add to Batch Inbox";
    button.disabled = panel.dataset.csIntakeReviewed !== "true" || alreadyInSprint;
  }

  async function commitThirdEyeIntake(panel) {
    if (panel.dataset.csIntakeReviewed !== "true") return;
    const status = panel.querySelector('[data-cs="intake-review-status"]');
    const button = panel.querySelector('[data-cs="intake-commit"]');
    const destination = panel.querySelector('[data-cs-destination]:checked')?.value || "inbox";
    if (button) button.disabled = true;
    if (status) {
      status.style.color = "#b3b3b3";
      status.textContent = "Adding the reviewed job...";
    }
    const response = await sendRuntimeMessage({
      action: "CAREERSITE_INTAKE_COMMIT",
      payload: { ...readThirdEyeIntake(panel), destination },
    });
    if (response?.error) {
      if (button) button.disabled = false;
      if (status) {
        status.style.color = "#f5c518";
        status.textContent = `Could not add this job: ${friendlyRuntimeError(response.error)}`;
      }
      return;
    }
    panel.dataset.csIntakeReviewed = "false";
    if (button) {
      button.disabled = true;
      button.textContent = response.action === "added_to_sprint" ? "Added to sprint" : "Saved in Batch Inbox";
    }
    if (status) {
      status.style.color = response.action.startsWith("duplicate") ? "#f5c518" : "#b7e4c7";
      status.textContent = `${response.message} No Claude call.`;
    }
  }

  function readTailoringPreferences(panel) {
    return {
      preset: panel.querySelector('[data-cs="tailor-preset"]')?.value || "balanced",
      rewrite_intensity: panel.querySelector('[data-cs="tailor-intensity"]')?.value || "balanced",
      emphasis: [...panel.querySelectorAll("[data-cs-emphasis]:checked")]
        .map((input) => input.getAttribute("data-cs-emphasis"))
        .filter(Boolean),
      custom_instructions: (panel.querySelector('[data-cs="tailor-instructions"]')?.value || "").trim(),
      include_connection_note: Boolean(panel.querySelector('[data-cs="tailor-note"]')?.checked),
      include_cover_letter: Boolean(panel.querySelector('[data-cs="tailor-cover-letter"]')?.checked),
      bullet_counts: readBulletCounts(panel),
    };
  }

  function readBulletCounts(root) {
    return {
      experience_per_role: clampInt(root.querySelector('[data-cs-count="experience_per_role"]')?.value, 0, 50, 3),
      projects_per_project: clampInt(root.querySelector('[data-cs-count="projects_per_project"]')?.value, 0, 50, 2),
      research_per_paper: clampInt(root.querySelector('[data-cs-count="research_per_paper"]')?.value, 0, 50, 2),
    };
  }

  function normalizeBulletCounts(value) {
    const source = value && typeof value === "object" ? value : {};
    return {
      experience_per_role: clampInt(source.experience_per_role, 0, 50, 3),
      projects_per_project: clampInt(source.projects_per_project, 0, 50, 2),
      research_per_paper: clampInt(source.research_per_paper, 0, 50, 2),
    };
  }

  function applyBulletCounts(root, counts) {
    const normalized = normalizeBulletCounts(counts);
    for (const [key, value] of Object.entries(normalized)) {
      root.querySelectorAll(`[data-cs-count="${key}"]`).forEach((input) => {
        input.value = String(value);
      });
    }
  }

  function clampInt(value, low, high, fallback) {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(low, Math.min(high, parsed));
  }

  function rolePreferenceKey(role) {
    const lowered = String(role || "").toLowerCase();
    const family = lowered.includes("computer vision") ? "computer_vision"
      : lowered.includes("machine learning") || lowered.includes("ml ") ? "machine_learning"
      : lowered.includes("data engineer") ? "data_engineering"
      : lowered.includes("analyst") || lowered.includes("analytics") ? "analytics"
      : lowered.includes("data scientist") ? "data_science"
      : lowered.includes("ai ") || lowered.includes("artificial intelligence") ? "ai_engineering"
      : "general";
    return `careersite-tailoring-defaults:${family}`;
  }

  function saveTailoringDefaults(role, preferences) {
    try {
      chrome.storage?.local?.set({ [rolePreferenceKey(role)]: preferences });
    } catch (_error) {
      // Defaults are optional; tailoring must still work without extension storage.
    }
  }

  function loadTailoringDefaults(panel, role) {
    try {
      chrome.storage?.local?.get(rolePreferenceKey(role), (saved) => {
        const preferences = saved?.[rolePreferenceKey(role)];
        if (!preferences) return;
        const preset = panel.querySelector('[data-cs="tailor-preset"]');
        const intensity = panel.querySelector('[data-cs="tailor-intensity"]');
        const instructions = panel.querySelector('[data-cs="tailor-instructions"]');
        const note = panel.querySelector('[data-cs="tailor-note"]');
        const coverLetter = panel.querySelector('[data-cs="tailor-cover-letter"]');
        if (preset) preset.value = preferences.preset || "balanced";
        if (intensity) intensity.value = preferences.rewrite_intensity || "balanced";
        if (instructions) instructions.value = preferences.custom_instructions || "";
        if (note) note.checked = preferences.include_connection_note !== false;
        if (coverLetter) coverLetter.checked = preferences.include_cover_letter === true;
        applyBulletCounts(panel, preferences.bullet_counts);
        const emphasis = new Set(preferences.emphasis || []);
        panel.querySelectorAll("[data-cs-emphasis]").forEach((input) => {
          input.checked = emphasis.has(input.getAttribute("data-cs-emphasis"));
        });
      });
    } catch (_error) {
      // Defaults are optional.
    }
  }

  function renderTailoringReview(panel, draft, requestPayload) {
    const container = panel.querySelector('[data-cs="tailor-review"]');
    if (!container || !draft?.draft_id) return;
    const bullets = Array.isArray(draft.bullets) ? draft.bullets : [];
    const projects = Array.isArray(draft.projects) ? draft.projects : [];
    const publications = Array.isArray(draft.publications) ? draft.publications : [];
    const counts = normalizeBulletCounts(draft.preferences?.bullet_counts || requestPayload?.tailoring_preferences?.bullet_counts);
    const coverLetterText = String(draft.cover_letter_text || "");
    const bulletRows = bullets.map((bullet) => `
      <div data-cs-bullet="${watcherEscape(bullet.bullet_id)}" style="margin-top:8px;padding:8px;border:1px solid rgba(255,255,255,.1);border-radius:6px;background:#1d1d1d;">
        <label style="display:flex;gap:6px;align-items:flex-start;color:#fff;font-size:11px;font-weight:700;">
          <input data-cs="bullet-accepted" type="checkbox" checked>
          <span>${watcherEscape(bullet.item_label || bullet.section)}</span>
        </label>
        <textarea data-cs="bullet-text" rows="4" maxlength="700" style="display:block;width:100%;margin-top:5px;padding:6px;resize:vertical;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;font:11px/1.4 Arial,sans-serif;box-sizing:border-box;">${watcherEscape(bullet.proposed)}</textarea>
        <details style="margin-top:4px;color:#888;font-size:10px;"><summary>Verified original</summary><div style="margin-top:3px;">${watcherEscape(bullet.original)}</div></details>
      </div>`).join("");
    const projectRows = projects.map((project) => `
      <div draggable="true" data-cs-project="${watcherEscape(project.project_id)}" style="display:flex;align-items:center;gap:7px;margin-top:5px;padding:7px;border:1px solid rgba(255,255,255,.1);border-radius:6px;background:#222;cursor:grab;">
        <span aria-hidden="true" style="color:#777;">&#x2630;</span>
        <input data-cs="project-selected" type="checkbox" ${project.selected === false ? "" : "checked"}>
        <span style="flex:1;color:#e5e5e5;font-size:11px;">${watcherEscape(project.name)}</span>
      </div>`).join("");
    const publicationRows = publications.map((publication) => `
      <div data-cs-publication="${watcherEscape(publication.publication_id)}" style="display:flex;align-items:flex-start;gap:7px;margin-top:5px;padding:7px;border:1px solid rgba(255,255,255,.1);border-radius:6px;background:#222;">
        <input data-cs="publication-selected" type="checkbox" ${publication.selected === false ? "" : "checked"}>
        <span style="flex:1;color:#e5e5e5;font-size:11px;">${watcherEscape(publication.title)}${publication.venue ? `<br><span style="color:#999;">${watcherEscape(publication.venue)}${publication.year ? " · " + watcherEscape(publication.year) : ""}</span>` : ""}</span>
      </div>`).join("");
    container.innerHTML = `
      <div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,.12);">
        <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;">
          <strong style="font-size:12px;">Review Claude draft</strong>
          <span style="font-size:10px;color:#b3b3b3;">${watcherEscape(draft.base_score)}% to ${watcherEscape(draft.tailored_score)}%</span>
        </div>
        <button data-cs="open-resume-preview" style="margin-top:9px;width:100%;border:1px solid #666;border-radius:6px;padding:8px;background:#303030;color:#fff;font-weight:700;cursor:pointer;">Open full resume preview</button>
        <div style="margin-top:8px;padding:8px;border:1px solid rgba(255,255,255,.1);border-radius:6px;background:#1d1d1d;">
          <div style="color:#b3b3b3;font-size:11px;font-weight:700;margin-bottom:5px;">Bullets per subsection</div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;">
            <label style="display:block;color:#d6d6d6;font-size:10px;">Experience
              <input data-cs-count="experience_per_role" type="number" min="0" step="1" value="${watcherEscape(counts.experience_per_role)}" style="display:block;width:100%;margin-top:3px;padding:5px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;">
            </label>
            <label style="display:block;color:#d6d6d6;font-size:10px;">Projects
              <input data-cs-count="projects_per_project" type="number" min="0" step="1" value="${watcherEscape(counts.projects_per_project)}" style="display:block;width:100%;margin-top:3px;padding:5px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;">
            </label>
            <label style="display:block;color:#d6d6d6;font-size:10px;">Research
              <input data-cs-count="research_per_paper" type="number" min="0" step="1" value="${watcherEscape(counts.research_per_paper)}" style="display:block;width:100%;margin-top:3px;padding:5px;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;">
            </label>
          </div>
          <div style="margin-top:5px;color:#888;font-size:10px;">Open preview re-renders locally. Regenerate sends these per-subsection counts to Sonnet for more grounded bullets.</div>
        </div>
        <details style="margin-top:8px;">
          <summary style="cursor:pointer;color:#d6d6d6;font-size:11px;font-weight:700;">Edit draft details</summary>
        <label style="display:flex;gap:6px;align-items:center;margin-top:8px;color:#fff;font-size:11px;font-weight:700;">
          <input data-cs="summary-accepted" type="checkbox" checked>
          Use tailored summary
        </label>
        <textarea data-cs="summary-text" rows="5" maxlength="1400" style="display:block;width:100%;margin-top:5px;padding:6px;resize:vertical;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;font:11px/1.4 Arial,sans-serif;box-sizing:border-box;">${watcherEscape(draft.summary_proposed || draft.summary_original)}</textarea>
        <details style="margin-top:4px;color:#888;font-size:10px;"><summary>Original summary</summary><div style="margin-top:3px;">${watcherEscape(draft.summary_original)}</div></details>
        ${bullets.length ? `<div style="margin-top:10px;color:#b3b3b3;font-size:11px;font-weight:700;">Bullet rewrites</div>${bulletRows}` : ""}
        ${projects.length ? `<div style="margin-top:10px;color:#b3b3b3;font-size:11px;font-weight:700;">Projects: drag to reorder</div><div data-cs="project-list">${projectRows}</div>` : ""}
        ${publications.length ? `<div style="margin-top:10px;color:#b3b3b3;font-size:11px;font-weight:700;">Research papers</div><div data-cs="publication-list">${publicationRows}</div>` : ""}
        ${draft.skill_gaps?.length ? `<div style="margin-top:8px;color:#f5c518;font-size:10px;">Honest gaps: ${watcherEscape(draft.skill_gaps.join(", "))}</div>` : ""}
        <label style="display:block;margin-top:8px;color:#b3b3b3;font-size:11px;">Recruiter note
          <textarea data-cs="connection-note" rows="3" maxlength="299" style="display:block;width:100%;margin-top:3px;padding:6px;resize:vertical;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;font:11px/1.4 Arial,sans-serif;box-sizing:border-box;">${watcherEscape(draft.connection_note || "")}</textarea>
        </label>
        ${coverLetterText ? `
        <label style="display:flex;gap:6px;align-items:center;margin-top:8px;color:#fff;font-size:11px;font-weight:700;">
          <input data-cs="cover-letter-accepted" type="checkbox" checked>
          Include cover letter in apply plan
        </label>
        <textarea data-cs="cover-letter-text" rows="8" maxlength="4000" style="display:block;width:100%;margin-top:5px;padding:6px;resize:vertical;border-radius:5px;border:1px solid #555;background:#262626;color:#fff;font:11px/1.4 Arial,sans-serif;box-sizing:border-box;">${watcherEscape(coverLetterText)}</textarea>
        ` : ""}
        </details>
        <button data-cs="finalize" style="margin-top:10px;width:100%;border:0;border-radius:6px;padding:8px;background:#e50914;color:#fff;font-weight:700;cursor:pointer;">Approve and generate DOCX + PDF</button>
        <button data-cs="regenerate" style="margin-top:6px;width:100%;border:1px solid #555;border-radius:6px;padding:7px;background:#242424;color:#fff;font-weight:700;cursor:pointer;">Regenerate draft (another Claude call)</button>
        <div data-cs="finalize-status" style="margin-top:6px;color:#b3b3b3;font-size:11px;"></div>
        <div data-cs="download-actions"></div>
      </div>`;

    for (const bullet of bullets) {
      const row = container.querySelector(`[data-cs-bullet="${bullet.bullet_id}"]`);
      const accepted = row?.querySelector('[data-cs="bullet-accepted"]');
      const text = row?.querySelector('[data-cs="bullet-text"]');
      accepted?.addEventListener("change", () => {
        if (!text) return;
        text.disabled = !accepted.checked;
        text.value = accepted.checked ? bullet.proposed : bullet.original;
      });
    }
    installProjectReordering(container);

    container.querySelector('[data-cs="open-resume-preview"]')?.addEventListener("click", async () => {
      const status = container.querySelector('[data-cs="finalize-status"]');
      if (status) status.textContent = "Rendering preview locally...";
      const response = await sendRuntimeMessage({
        action: "CAREERSITE_TAILOR_RENDER_PREVIEW",
        payload: collectTailoringReviewPayload(container, draft, bullets),
      });
      if (response?.error) {
        if (status) status.textContent = `Preview failed: ${friendlyRuntimeError(response.error)}`;
        return;
      }
      if (status) status.textContent = "Preview is open. Rendering did not use another Claude call.";
      openResumePreview(`${draft.role || "Tailored resume"} preview`, response.resume_preview_html || draft.resume_preview_html || "");
    });

    if (draft.resume_preview_html) {
      openResumePreview(`${draft.role || "Tailored resume"} preview`, draft.resume_preview_html);
    }

    container.querySelector('[data-cs="finalize"]')?.addEventListener("click", async () => {
      const status = container.querySelector('[data-cs="finalize-status"]');
      if (status) status.textContent = "Rendering DOCX and PDF locally...";
      const response = await sendRuntimeMessage({
        action: "CAREERSITE_TAILOR_FINALIZE",
        payload: collectTailoringReviewPayload(container, draft, bullets),
      });
      if (response?.error) {
        if (status) status.textContent = `Generation failed: ${friendlyRuntimeError(response.error)}`;
        return;
      }
      if (status) status.textContent = response.message || "Resume files are ready.";
      renderDownloadActions(container, response);
    });

    container.querySelector('[data-cs="regenerate"]')?.addEventListener("click", async () => {
      if (!window.confirm("Regenerating uses another Claude call. Continue?")) return;
      const status = container.querySelector('[data-cs="finalize-status"]');
      if (status) status.textContent = "Claude is regenerating the draft...";
      const preferences = readTailoringPreferences(panel);
      preferences.bullet_counts = readBulletCounts(container);
      saveTailoringDefaults(requestPayload.role || "", preferences);
      const response = await sendRuntimeMessage({
        action: "CAREERSITE_TAILOR_PREVIEW",
        payload: { ...requestPayload, tailoring_preferences: preferences },
      });
      if (response?.error) {
        if (status) status.textContent = `Regeneration failed: ${friendlyRuntimeError(response.error)}`;
        return;
      }
      renderTailoringReview(panel, response, requestPayload);
    });
  }

  function installProjectReordering(container) {
    let dragged = null;
    container.querySelectorAll("[data-cs-project]").forEach((row) => {
      row.addEventListener("dragstart", () => {
        dragged = row;
        row.style.opacity = ".55";
      });
      row.addEventListener("dragend", () => {
        row.style.opacity = "1";
        dragged = null;
      });
      row.addEventListener("dragover", (event) => event.preventDefault());
      row.addEventListener("drop", (event) => {
        event.preventDefault();
        if (!dragged || dragged === row) return;
        row.parentElement?.insertBefore(dragged, row);
      });
    });
  }

  function collectTailoringReviewPayload(container, draft, bullets) {
    const selectedProjects = [...container.querySelectorAll("[data-cs-project]")]
      .filter((row) => row.querySelector('[data-cs="project-selected"]')?.checked)
      .map((row) => row.getAttribute("data-cs-project"))
      .filter(Boolean);
    const selectedPublications = [...container.querySelectorAll("[data-cs-publication]")]
      .filter((row) => row.querySelector('[data-cs="publication-selected"]')?.checked)
      .map((row) => row.getAttribute("data-cs-publication"))
      .filter(Boolean);
    const bulletDecisions = bullets.map((bullet) => {
      const row = container.querySelector(`[data-cs-bullet="${bullet.bullet_id}"]`);
      return {
        bullet_id: bullet.bullet_id,
        accepted: Boolean(row?.querySelector('[data-cs="bullet-accepted"]')?.checked),
        text: row?.querySelector('[data-cs="bullet-text"]')?.value || "",
      };
    });
    return {
      draft_id: draft.draft_id,
      summary_accepted: Boolean(container.querySelector('[data-cs="summary-accepted"]')?.checked),
      summary_text: container.querySelector('[data-cs="summary-text"]')?.value || "",
      bullets: bulletDecisions,
      project_ids: selectedProjects,
      publication_ids: selectedPublications,
      bullet_counts: readBulletCounts(container),
      connection_note: container.querySelector('[data-cs="connection-note"]')?.value || "",
      cover_letter_accepted: Boolean(container.querySelector('[data-cs="cover-letter-accepted"]')?.checked),
      cover_letter_text: container.querySelector('[data-cs="cover-letter-text"]')?.value || "",
      render_pdf: true,
    };
  }

  function openResumePreview(title, resumeHtml) {
    if (!resumeHtml) return;
    document.querySelector("[data-cs-preview-overlay]")?.remove();
    const overlay = document.createElement("div");
    overlay.setAttribute("data-cs-preview-overlay", "true");
    overlay.style.cssText = [
      "position:fixed", "inset:0", "z-index:2147483647", "background:rgba(0,0,0,.72)",
      "display:flex", "align-items:center", "justify-content:center", "padding:22px",
      "font:13px/1.4 Arial,sans-serif",
    ].join(";");
    overlay.innerHTML = `
      <div style="width:min(1120px, 96vw);height:min(920px, 92vh);display:flex;flex-direction:column;background:#151515;border:1px solid rgba(255,255,255,.18);border-radius:10px;box-shadow:0 24px 70px rgba(0,0,0,.6);overflow:hidden;">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.12);color:#fff;">
          <strong style="font-size:13px;">${watcherEscape(title)}</strong>
          <span style="margin-left:auto;color:#9f9f9f;font-size:11px;">Screen preview</span>
          <button data-cs-preview-close style="border:1px solid #555;border-radius:6px;background:#252525;color:#fff;padding:5px 9px;cursor:pointer;font-weight:700;">Close</button>
        </div>
        <iframe data-cs-preview-frame sandbox="" style="flex:1;width:100%;border:0;background:#e8e8e8;"></iframe>
      </div>`;
    document.documentElement.appendChild(overlay);
    const frame = overlay.querySelector("[data-cs-preview-frame]");
    if (frame) frame.srcdoc = resumePreviewDocument(resumeHtml);
    overlay.querySelector("[data-cs-preview-close]")?.addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) overlay.remove();
    });
  }

  function resumePreviewDocument(resumeHtml) {
    const previewCss = `
      <style>
        @media screen {
          html {
            min-height: 100%;
            background: #e8e8e8;
          }
          body {
            width: 8.5in;
            min-height: 11in;
            margin: 22px auto;
            padding: 0.36in 0.42in;
            background: #fff;
            box-shadow: 0 12px 34px rgba(0, 0, 0, .22);
            font-size: 10.6px;
            line-height: 1.28;
          }
          h1 {
            font-size: 20px;
            margin-bottom: 3px;
          }
          h2 {
            margin-top: 9px;
            font-size: 12px;
            border-bottom-color: #333;
          }
          h3 {
            font-size: 10.8px;
          }
          .contact {
            font-size: 9.8px;
            margin-bottom: 5px;
          }
          .summary,
          .skills-line,
          li,
          p {
            font-size: 10.2px;
          }
          li {
            margin: 2px 0;
          }
        }
      </style>`;
    if (String(resumeHtml).includes("</head>")) {
      return String(resumeHtml).replace("</head>", `${previewCss}</head>`);
    }
    return `<!DOCTYPE html><html><head>${previewCss}</head><body>${resumeHtml}</body></html>`;
  }

  function renderDownloadActions(container, response) {
    const actions = container.querySelector('[data-cs="download-actions"]');
    if (!actions) return;
    actions.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px;">
        ${response.docx_download_path ? `<button data-cs-download="${watcherEscape(response.docx_download_path)}" style="border:1px solid #666;border-radius:6px;padding:7px;background:#303030;color:#fff;font-weight:700;cursor:pointer;">Download DOCX</button>` : ""}
        ${response.pdf_download_path ? `<button data-cs-download="${watcherEscape(response.pdf_download_path)}" style="border:1px solid #666;border-radius:6px;padding:7px;background:#303030;color:#fff;font-weight:700;cursor:pointer;">Download PDF</button>` : ""}
      </div>`;
    if (response.prepared_apply_plan_path && response.apply_url) {
      actions.insertAdjacentHTML("beforeend", `
        <button data-cs="start-apply-assistant" style="margin-top:7px;width:100%;border:0;border-radius:6px;padding:8px;background:#e50914;color:#fff;font-weight:700;cursor:pointer;">Open application and fill safe fields</button>
        <div data-cs="apply-assistant-status" style="margin-top:5px;color:#b3b3b3;font-size:11px;"></div>
      `);
      actions.querySelector('[data-cs="start-apply-assistant"]')?.addEventListener("click", async () => {
        const status = actions.querySelector('[data-cs="apply-assistant-status"]');
        if (status) status.textContent = "Arming apply assistant...";
        const applyUrl = findApplyUrl() || response.apply_url;
        const result = await sendRuntimeMessage({
          action: "CAREERSITE_ARM_APPLY_ASSISTANT",
          payload: {
            url: applyUrl,
            apply_plan_path: response.prepared_apply_plan_path,
            overwrite: false,
            open_browser: true,
          },
        });
        if (status) {
          status.textContent = result?.error
            ? `Apply assistant failed: ${friendlyRuntimeError(result.error)}`
            : "Application page opened. Safe fields will fill when Third Eye matches the page.";
        }
      });
    }
    actions.querySelectorAll("[data-cs-download]").forEach((button) => {
      button.addEventListener("click", async () => {
        const result = await sendRuntimeMessage({
          action: "CAREERSITE_TAILOR_DOWNLOAD",
          path: button.getAttribute("data-cs-download"),
        });
        if (result?.error) button.textContent = friendlyRuntimeError(result.error);
      });
    });
  }

  function findApplyUrl() {
    const candidates = [...document.querySelectorAll("a[href]")]
      .map((anchor) => ({
        href: anchor.getAttribute("href") || "",
        text: cleanText(anchor.innerText || anchor.getAttribute("aria-label") || anchor.title || ""),
      }))
      .filter((item) => /apply|start application|submit application/i.test(`${item.text} ${item.href}`));
    for (const item of candidates) {
      try {
        const url = new URL(item.href, window.location.href);
        if (/^https?:$/i.test(url.protocol)) return url.href;
      } catch (_error) {
        // Ignore malformed job-board links and fall back to the current job URL.
      }
    }
    return "";
  }

  function applyWatcherSuggestions(suggestions, overwrite) {
    let filled = 0;
    for (const suggestion of suggestions) {
      if (suggestion.sensitive) continue;
      if (!["fill_text", "select_option", "choose_radio"].includes(suggestion.action)) continue;
      if (fillSuggestion(suggestion, Boolean(overwrite))) filled += 1;
    }
    return filled;
  }

  function fillSuggestion(suggestion, overwrite) {
    const target = suggestion.target_option || suggestion.value;
    if (suggestion.action === "choose_radio") {
      const radios = [...document.querySelectorAll(suggestion.selector)];
      const want = normalize(target);
      for (const radio of radios) {
        const label = normalize(labelFor(radio) || radio.value);
        if (label === want || normalize(radio.value) === want || (want && label.includes(want))) {
          radio.checked = true;
          notifyInput(radio);
          highlight(radio, "#e50914");
          return true;
        }
      }
      return false;
    }
    const element = document.querySelector(suggestion.selector);
    if (!element) return false;
    if (!overwrite && element.value) return false;
    if (suggestion.action === "select_option") {
      const want = normalize(target);
      for (const option of element.options) {
        if (normalize(option.textContent) === want || normalize(option.value) === want) {
          element.value = option.value;
          notifyInput(element);
          highlight(element, "#e50914");
          return true;
        }
      }
      return false;
    }
    element.value = suggestion.value;
    notifyInput(element);
    highlight(element, "#e50914");
    return true;
  }

  // ----- messaging + DOM utilities -----

  function sendRuntimeMessage(message) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(message, (response) => {
          if (chrome.runtime.lastError) {
            resolve({ error: chrome.runtime.lastError.message });
            return;
          }
          resolve(response || {});
        });
      } catch (error) {
        resolve({ error: error.message });
      }
    });
  }

  function friendlyRuntimeError(message) {
    const text = String(message || "Unknown error.");
    const lowered = text.toLowerCase();
    if (
      lowered.includes("extension context invalidated") ||
      lowered.includes("context invalidated") ||
      lowered.includes("receiving end does not exist") ||
      lowered.includes("message port closed")
    ) {
      return "Extension was reloaded. Refresh this job page, then try again.";
    }
    return text;
  }

  function labelFor(element) {
    if (!element) return "";
    if (element.id) {
      const explicit = document.querySelector(`label[for="${cssEscape(element.id)}"]`);
      if (explicit) return cleanText(explicit.textContent);
    }
    const parentLabel = element.closest("label");
    if (parentLabel) {
      const value = element.value || "";
      return cleanText(value ? parentLabel.textContent.replace(value, " ") : parentLabel.textContent);
    }
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {
      return labelledBy
        .split(/\s+/)
        .map((id) => document.getElementById(id)?.textContent || "")
        .join(" ")
        .trim();
    }
    return "";
  }

  function radioGroupLabel(element) {
    const fieldset = element?.closest("fieldset");
    const legend = fieldset?.querySelector("legend");
    return cleanText(legend?.textContent || "");
  }

  function contextFor(element) {
    const parent = element?.closest("fieldset, div, section, li");
    return cleanText((parent?.textContent || "").slice(0, 280));
  }

  function selectOptions(select) {
    return [...select.options].map((option) => cleanText(option.textContent || option.value)).filter(Boolean);
  }

  function selectorFor(element) {
    if (element.id) return `#${cssEscape(element.id)}`;
    if (element.name) return `${element.tagName.toLowerCase()}[name="${cssEscape(element.name)}"]`;
    return `[data-careersite-field-id="${cssEscape(element.dataset.careersiteFieldId)}"]`;
  }

  function notifyInput(element) {
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function highlight(element, color) {
    element.style.outline = `2px solid ${color}`;
    element.style.outlineOffset = "2px";
  }

  function normalize(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function cleanText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(String(value));
    return String(value).replace(/"/g, '\\"');
  }
})();
