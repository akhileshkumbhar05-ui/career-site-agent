import React from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Bot,
  BriefcaseBusiness,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  Clock3,
  ExternalLink,
  Eye,
  FilePenLine,
  FileText,
  Gauge,
  Inbox,
  Link2,
  Loader2,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  ShieldAlert,
  Sparkles,
  Trash2,
  Upload,
  XCircle
} from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

const defaultFilters = {
  search: "",
  minScore: 60,
  showReviews: true,
  showHidden: false,
  useLlm: true
};

function App() {
  const [feed, setFeed] = React.useState("manual");
  const [filters, setFilters] = React.useState(defaultFilters);
  const [data, setData] = React.useState(null);
  const [selectedKey, setSelectedKey] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [action, setAction] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [error, setError] = React.useState("");
  const [prepared, setPrepared] = React.useState(null);

  const activeJob = data?.jobs?.find((row) => row.key === selectedKey) || data?.jobs?.[0] || null;
  const standaloneWorkspace = feed === "manual" || feed === "batch";
  const feedTitle =
    feed === "manual"
      ? "Manual JD Review"
      : feed === "batch"
        ? "Ten-Job Batch Inbox"
        : feed === "fresh24"
          ? "Fresh 24h Jobs"
          : feed === "applied"
            ? "Already Applied"
            : "Recommended Jobs";

  const loadDashboard = React.useCallback(async () => {
    if (feed === "manual" || feed === "batch") {
      setLoading(false);
      setData(null);
      setSelectedKey("");
      setError("");
      return;
    }
    setLoading(true);
    setError("");
    const params = new URLSearchParams({
      feed,
      search: filters.search,
      min_score: String(filters.minScore),
      show_reviews: String(filters.showReviews),
      show_hidden: String(filters.showHidden),
      use_llm: String(filters.useLlm),
      limit: filters.useLlm ? "8" : "30"
    });
    try {
      const next = await apiGet(`/webapp/dashboard?${params}`);
      setData(next);
      setSelectedKey((current) => {
        if (current && next.jobs.some((row) => row.key === current)) return current;
        return next.jobs[0]?.key || "";
      });
    } catch (err) {
      setError(err.message || "Could not load dashboard.");
    } finally {
      setLoading(false);
    }
  }, [feed, filters]);

  React.useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  async function refreshJobs() {
    if (feed === "applied") {
      await loadDashboard();
      return;
    }
    setAction("refresh");
    setNotice("");
    setError("");
    try {
      const path = feed === "fresh24" ? "/webapp/refresh-fresh24" : "/webapp/refresh-main";
      const payload =
        feed === "fresh24"
          ? { hours: 24, max_results: 35, max_target_companies: 40, include_rejected: false }
          : {
              max_companies: 40,
              max_jobs_per_company: 25,
              include_rejected: false,
              include_web: true,
              web_max_results: 80,
              include_sponsors: true,
              sponsor_max_companies: 25,
              sponsor_max_results: 25
            };
      const result = await apiPost(path, payload);
      const targets = Array.isArray(result.targets) ? result.targets : [];
      const scraped = targets.reduce((total, row) => total + Number(row.scraped || 0), 0);
      const kept = targets.reduce((total, row) => total + Number(row.kept || 0), 0);
      setNotice(`Refresh complete: ${scraped} scraped, ${kept} kept.`);
      await loadDashboard();
    } catch (err) {
      setError(err.message || "Refresh failed.");
    } finally {
      setAction("");
    }
  }

  async function markAlreadyApplied(row) {
    setAction(`applied:${row.key}`);
    setNotice("");
    try {
      await apiPost("/webapp/already-applied", { job: row.job, reason: "already_applied" });
      setNotice("Moved to Already Applied.");
      await loadDashboard();
    } catch (err) {
      setError(err.message || "Could not move job.");
    } finally {
      setAction("");
    }
  }

  async function preparePacket(row) {
    setAction(`prepare:${row.key}`);
    setPrepared(null);
    try {
      const context = await apiPost("/webapp/prepare-tailored-resume", { job: row.job, render_pdf: true });
      setPrepared(context);
      if (context.prepared_resume_path || context.prepared_resume_html_path || context.prepared_resume_pdf_path) {
        setNotice(context.message || "Tailored resume ready.");
      } else {
        setError(context.message || "Tailor Resume did not create a resume file.");
      }
    } catch (err) {
      setError(err.message || "Could not prepare tailored resume.");
    } finally {
      setAction("");
    }
  }

  return (
    <main className="app-shell">
      <aside className="side-rail">
        <div className="brand-block">
          <div className="brand-mark" />
          <div>
            <div className="brand-name">CareerSite</div>
            <div className="brand-meta">Agent Console</div>
          </div>
        </div>
        <nav className="nav-stack" aria-label="Job feeds">
          <RailButton active={feed === "manual"} icon={FileText} label="Manual JD" onClick={() => setFeed("manual")} />
          <RailButton active={feed === "batch"} icon={Inbox} label="Batch Inbox" onClick={() => setFeed("batch")} />
          <RailButton active={feed === "recommended"} icon={BriefcaseBusiness} label="Recommended" onClick={() => setFeed("recommended")} />
          <RailButton active={feed === "fresh24"} icon={Clock3} label="Fresh 24h" onClick={() => setFeed("fresh24")} />
          <RailButton active={feed === "applied"} icon={CheckCircle2} label="Already Applied" onClick={() => setFeed("applied")} />
        </nav>
        <div className="side-metrics">
          <Metric label="Loaded" value={data?.stats?.raw_count ?? "--"} />
          <Metric label="Visible" value={data?.stats?.visible_count ?? "--"} />
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>{feedTitle}</h1>
            <div className="topline">
              <StatusPill tone={error ? "bad" : "good"} icon={error ? XCircle : CheckCircle2} text={error ? "Needs attention" : "Ready"} />
              <StatusPill tone="neutral" icon={Bot} text={feed === "manual" ? "Paste JD analysis" : feed === "batch" ? "Deterministic intake" : filters.useLlm ? "LLM scoring" : "Deterministic scoring"} />
              <StatusPill tone="neutral" icon={Eye} text={standaloneWorkspace ? "Human review" : "Browser watcher fills"} />
              {feed === "recommended" && <StatusPill tone="sponsor" icon={ShieldAlert} text="DOL sponsor source" />}
            </div>
          </div>
          <div className="top-actions">
            {!standaloneWorkspace && (
              <button className="icon-button secondary" onClick={loadDashboard} disabled={loading || Boolean(action)}>
                {loading ? <Loader2 className="spin" size={18} /> : <RefreshCw size={18} />}
                <span>Reload</span>
              </button>
            )}
            {feed !== "applied" && !standaloneWorkspace && (
              <button className="icon-button primary" onClick={refreshJobs} disabled={loading || Boolean(action)}>
                {action === "refresh" ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />}
                <span>{feed === "fresh24" ? "Refresh Fresh Jobs" : "Refresh Jobs"}</span>
              </button>
            )}
          </div>
        </header>

        {(notice || error) && (
          <div className={`notice ${error ? "notice-bad" : "notice-good"}`}>
            {error ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
            <span>{error || notice}</span>
          </div>
        )}

        {feed === "manual" ? (
          <ManualJDWorkspace />
        ) : feed === "batch" ? (
          <BatchInboxWorkspace />
        ) : (
          <>
            <Toolbar feed={feed} filters={filters} setFilters={setFilters} />

            <section className="content-grid">
              <section className="job-list" aria-label="Ranked jobs">
                <div className="list-header">
                  <h2>{data?.jobs?.length ?? 0} matches</h2>
                  <span>{data?.stats?.hidden_count ?? 0} hidden/applied</span>
                </div>
                {loading ? <SkeletonList /> : data?.jobs?.length ? (
                  data.jobs.map((row) => (
                    <JobCard
                      key={row.key}
                      row={row}
                      active={activeJob?.key === row.key}
                      action={action}
                      onSelect={() => setSelectedKey(row.key)}
                      onAlreadyApplied={() => markAlreadyApplied(row)}
                      onPrepare={() => preparePacket(row)}
                    />
                  ))
                ) : (
                  <EmptyState feed={feed} />
                )}
              </section>

              <aside className="detail-panel" aria-label="Job details">
                {activeJob ? (
                  <JobDetail
                    row={activeJob}
                    prepared={prepared}
                    action={action}
                    onPrepare={() => preparePacket(activeJob)}
                    onAlreadyApplied={() => markAlreadyApplied(activeJob)}
                  />
                ) : (
                  <div className="detail-empty">No job selected</div>
                )}
              </aside>
            </section>
          </>
        )}
      </section>
    </main>
  );
}

function RailButton({ active, icon: Icon, label, onClick }) {
  return (
    <button className={`rail-button ${active ? "active" : ""}`} onClick={onClick}>
      <Icon size={18} />
      <span>{label}</span>
    </button>
  );
}

function Metric({ label, value }) {
  return (
    <div className="side-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ tone, icon: Icon, text }) {
  return (
    <span className={`status-pill ${tone}`}>
      <Icon size={14} />
      {text}
    </span>
  );
}

function Toolbar({ feed, filters, setFilters }) {
  const compact = feed === "applied";
  return (
    <section className="toolbar">
      <label className="search-box">
        <Search size={18} />
        <input
          value={filters.search}
          onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
          placeholder="Search company or role"
        />
      </label>
      {!compact && (
        <>
          <label className="range-control">
            <span>Minimum score</span>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={filters.minScore}
              onChange={(event) => setFilters((current) => ({ ...current, minScore: Number(event.target.value) }))}
            />
            <strong>{filters.minScore}</strong>
          </label>
          <Toggle label="Reviews" checked={filters.showReviews} onChange={(value) => setFilters((current) => ({ ...current, showReviews: value }))} />
          <Toggle label="Hidden" checked={filters.showHidden} onChange={(value) => setFilters((current) => ({ ...current, showHidden: value }))} />
          <Toggle label="Use LLM" checked={filters.useLlm} onChange={(value) => setFilters((current) => ({ ...current, useLlm: value }))} />
        </>
      )}
    </section>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <label className="toggle-control">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span />
      <strong>{label}</strong>
    </label>
  );
}

const BATCH_SOURCES = ["Jobright AI", "LinkedIn", "Referral", "Company Website", "Simplify", "TikTok", "Cognizant", "Unknown"];
let batchEntrySequence = 0;

function newBatchEntry(overrides = {}) {
  batchEntrySequence += 1;
  return {
    id: `batch-entry-${batchEntrySequence}`,
    company: "",
    role: "",
    job_url: "",
    jd_text: "",
    source: "Jobright AI",
    expanded: false,
    ...overrides
  };
}

function BatchInboxWorkspace() {
  const [entries, setEntries] = React.useState(() => [newBatchEntry()]);
  const [bulkLinks, setBulkLinks] = React.useState("");
  const [inbox, setInbox] = React.useState([]);
  const [batchResult, setBatchResult] = React.useState(null);
  const [busy, setBusy] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [error, setError] = React.useState("");
  const [useClaude, setUseClaude] = React.useState(true);
  const [fitResult, setFitResult] = React.useState(null);
  const [jdEditors, setJdEditors] = React.useState({});
  const [reviewItemId, setReviewItemId] = React.useState("");
  const [overrideNote, setOverrideNote] = React.useState("");

  const loadInbox = React.useCallback(async () => {
    setBusy((current) => current || "load");
    try {
      const items = await apiGet("/application-loop/items?limit=100");
      setInbox(Array.isArray(items) ? items : []);
    } catch (err) {
      setError(err.message || "Could not load the batch inbox.");
    } finally {
      setBusy((current) => current === "load" ? "" : current);
    }
  }, []);

  React.useEffect(() => {
    loadInbox();
  }, [loadInbox]);

  function updateEntry(id, field, value) {
    setEntries((current) => current.map((entry) => entry.id === id ? { ...entry, [field]: value } : entry));
    setBatchResult(null);
    setMessage("");
    setError("");
  }

  function addEntry() {
    if (entries.length >= 10) return;
    setEntries((current) => [...current, newBatchEntry()]);
    setBatchResult(null);
  }

  function removeEntry(id) {
    setEntries((current) => current.length === 1 ? [newBatchEntry()] : current.filter((entry) => entry.id !== id));
    setBatchResult(null);
  }

  function resetEntries() {
    setEntries([newBatchEntry()]);
    setBulkLinks("");
    setBatchResult(null);
    setMessage("");
    setError("");
  }

  function loadBulkLinks() {
    const urls = bulkLinks
      .split(/\r?\n/)
      .map((value) => value.trim())
      .filter((value) => /^https?:\/\//i.test(value))
      .slice(0, 10);
    if (!urls.length) {
      setError("No complete http or https job links found.");
      return;
    }
    setEntries(urls.map((job_url) => newBatchEntry({ job_url })));
    setBatchResult(null);
    setMessage(`${urls.length} link${urls.length === 1 ? "" : "s"} loaded into the batch.`);
    setError("");
  }

  async function importBatch() {
    const submittedEntries = entries.filter((entry) => entry.job_url.trim() || entry.jd_text.trim());
    const items = submittedEntries.map(({ company, role, job_url, jd_text, source }) => ({ company, role, job_url, jd_text, source }));
    if (!submittedEntries.length) {
      setError("Add at least one job link or job description.");
      return;
    }

    setBusy("import");
    setError("");
    setMessage("");
    try {
      const result = await apiPost("/application-loop/batches", { items });
      setBatchResult({
        ...result,
        outcomes: result.outcomes.map((outcome) => ({
          ...outcome,
          entry_id: submittedEntries[outcome.input_index]?.id || ""
        }))
      });
      setMessage(`${result.summary.imported} imported, ${result.summary.duplicate} duplicate, ${result.summary.invalid} invalid.`);
      await loadInbox();
    } catch (err) {
      setError(err.message || "Could not import this batch.");
    } finally {
      setBusy("");
    }
  }

  async function runFitGate(loopIds, forceRefresh = false) {
    if (!loopIds.length) return;
    const busyKey = loopIds.length === 1 ? `fit:${loopIds[0]}` : "fit";
    setBusy(busyKey);
    setError("");
    setMessage("");
    try {
      const result = await apiPost("/application-loop/fit-gate", {
        loop_ids: loopIds,
        use_llm: useClaude,
        force_refresh: forceRefresh
      });
      setFitResult(result);
      const summary = result.summary;
      setMessage(`${summary.apply} apply, ${summary.maybe} maybe, ${summary.skip} skip, ${summary.needs_jd} need JD.`);
      await loadInbox();
    } catch (err) {
      setError(err.message || "Fit Gate could not complete.");
    } finally {
      setBusy("");
    }
  }

  function openJdEditor(item) {
    setJdEditors((current) => ({ ...current, [item.loop_id]: item.jd_text || "" }));
    setReviewItemId("");
    setOverrideNote("");
  }

  function closeJdEditor(loopId) {
    setJdEditors((current) => {
      const next = { ...current };
      delete next[loopId];
      return next;
    });
  }

  async function saveJd(item) {
    const jdText = String(jdEditors[item.loop_id] || "").trim();
    if (jdText.length < 20) {
      setError("The JD needs at least 20 characters.");
      return;
    }
    setBusy(`jd:${item.loop_id}`);
    setError("");
    setMessage("");
    try {
      await apiPut(`/application-loop/items/${item.loop_id}/jd`, { jd_text: jdText });
      closeJdEditor(item.loop_id);
      setMessage("JD saved. This item is ready for Fit Gate.");
      await loadInbox();
    } catch (err) {
      setError(err.message || "Could not save this JD.");
    } finally {
      setBusy("");
    }
  }

  function openReview(item) {
    setReviewItemId((current) => current === item.loop_id ? "" : item.loop_id);
    setOverrideNote("");
    setJdEditors({});
  }

  async function overrideFit(item, decision) {
    if (overrideNote.trim().length < 3) {
      setError("Add a short reason before overriding Fit Gate.");
      return;
    }
    setBusy(`override:${item.loop_id}`);
    setError("");
    setMessage("");
    try {
      await apiPost(`/application-loop/items/${item.loop_id}/fit-override`, {
        decision,
        note: overrideNote.trim()
      });
      setReviewItemId("");
      setOverrideNote("");
      setMessage(`Decision changed to ${decision}.`);
      await loadInbox();
    } catch (err) {
      setError(err.message || "Could not override this decision.");
    } finally {
      setBusy("");
    }
  }

  const outcomes = new Map((batchResult?.outcomes || []).map((outcome) => [outcome.entry_id, outcome]));
  const readyCount = entries.filter((entry) => entry.job_url.trim() || entry.jd_text.trim()).length;
  const pendingFitIds = inbox.filter((item) => item.state === "imported").map((item) => item.loop_id);

  return (
    <section className="batch-workspace">
      <section className="batch-compose" aria-label="New application batch">
        <div className="batch-section-header">
          <div>
            <h2>New batch</h2>
            <span>{entries.length} of 10 slots</span>
          </div>
          <div className="batch-header-actions">
            <button className="icon-button ghost" title="Clear batch" onClick={resetEntries} disabled={busy === "import"}>
              <Trash2 size={17} />
              <span>Clear</span>
            </button>
            <button className="icon-button secondary" onClick={addEntry} disabled={entries.length >= 10 || busy === "import"}>
              <Plus size={17} />
              <span>Add job</span>
            </button>
          </div>
        </div>

        <div className="batch-bulk-input">
          <label>
            <span>Paste links</span>
            <textarea
              value={bulkLinks}
              onChange={(event) => setBulkLinks(event.target.value)}
              placeholder={"One canonical job URL per line\nhttps://company.example/jobs/data-analyst"}
            />
          </label>
          <button className="icon-button secondary" onClick={loadBulkLinks} disabled={!bulkLinks.trim() || busy === "import"}>
            <Link2 size={17} />
            <span>Load links</span>
          </button>
        </div>

        <div className="batch-entry-list">
          {entries.map((entry, index) => {
            const outcome = outcomes.get(entry.id);
            return (
              <article className={`batch-entry ${outcome ? `outcome-${outcome.status}` : ""}`} key={entry.id}>
                <header className="batch-entry-header">
                  <div className="batch-entry-number">
                    <strong>{String(index + 1).padStart(2, "0")}</strong>
                    {outcome && <span className={`tag ${outcome.status === "imported" ? "good" : outcome.status === "duplicate" ? "warn" : "bad"}`}>{outcome.status}</span>}
                  </div>
                  <div className="batch-entry-actions">
                    <button
                      className="icon-button ghost compact-icon"
                      title={entry.expanded ? "Hide job description" : "Add job description"}
                      onClick={() => updateEntry(entry.id, "expanded", !entry.expanded)}
                    >
                      {entry.expanded ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
                    </button>
                    <button className="icon-button ghost compact-icon" title="Remove job" onClick={() => removeEntry(entry.id)} disabled={busy === "import"}>
                      <Trash2 size={17} />
                    </button>
                  </div>
                </header>

                <div className="batch-entry-fields">
                  <label>
                    <span>Company</span>
                    <input value={entry.company} onChange={(event) => updateEntry(entry.id, "company", event.target.value)} placeholder="Infer from URL or JD" />
                  </label>
                  <label>
                    <span>Role</span>
                    <input value={entry.role} onChange={(event) => updateEntry(entry.id, "role", event.target.value)} placeholder="Infer from URL or JD" />
                  </label>
                  <label>
                    <span>Discovery source</span>
                    <select value={entry.source} onChange={(event) => updateEntry(entry.id, "source", event.target.value)}>
                      {BATCH_SOURCES.map((source) => <option value={source} key={source}>{source}</option>)}
                    </select>
                  </label>
                  <label className="batch-url-field">
                    <span>Canonical link</span>
                    <input value={entry.job_url} onChange={(event) => updateEntry(entry.id, "job_url", event.target.value)} placeholder="https://" />
                  </label>
                </div>

                {entry.expanded && (
                  <label className="batch-jd-field">
                    <span>Job description</span>
                    <textarea value={entry.jd_text} onChange={(event) => updateEntry(entry.id, "jd_text", event.target.value)} placeholder="Paste the full JD" />
                  </label>
                )}
                {outcome && <p className="batch-outcome-reason">{outcome.reason}</p>}
              </article>
            );
          })}
        </div>

        {(message || error) && (
          <div className={`notice ${error ? "notice-bad" : "notice-good"}`}>
            {error ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
            <span>{error || message}</span>
          </div>
        )}

        <div className="batch-submit-bar">
          <span>{readyCount} ready</span>
          <button className="icon-button primary" onClick={importBatch} disabled={!readyCount || busy === "import"}>
            {busy === "import" ? <Loader2 className="spin" size={18} /> : <Upload size={18} />}
            <span>Import batch</span>
          </button>
        </div>
      </section>

      <aside className="batch-inbox" aria-label="Application loop inbox">
        <div className="batch-section-header">
          <div>
            <h2>Application inbox</h2>
            <span>{pendingFitIds.length} pending / {inbox.length} total</span>
          </div>
          <button className="icon-button ghost compact-icon" title="Reload inbox" onClick={loadInbox} disabled={Boolean(busy)}>
            {busy === "load" ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
          </button>
        </div>

        <div className="fit-gate-toolbar">
          <div className="fit-gate-heading">
            <Gauge size={20} />
            <div>
              <h3>Fit Gate</h3>
              <span>{pendingFitIds.length} ready to check</span>
            </div>
          </div>
          <Toggle label="Use Claude" checked={useClaude} onChange={setUseClaude} />
          <button className="icon-button primary" onClick={() => runFitGate(pendingFitIds)} disabled={!pendingFitIds.length || Boolean(busy)}>
            {busy === "fit" ? <Loader2 className="spin" size={17} /> : <Gauge size={17} />}
            <span>Run Fit Gate</span>
          </button>
        </div>

        {batchResult && (
          <div className="batch-summary" aria-label="Latest import summary">
            <BatchStat label="Requested" value={batchResult.summary.requested} />
            <BatchStat label="Imported" value={batchResult.summary.imported} tone="good" />
            <BatchStat label="Duplicate" value={batchResult.summary.duplicate} tone="warn" />
            <BatchStat label="Invalid" value={batchResult.summary.invalid} tone="bad" />
          </div>
        )}

        {fitResult && (
          <div className="fit-gate-summary" aria-label="Latest Fit Gate summary">
            <BatchStat label="Apply" value={fitResult.summary.apply} tone="good" />
            <BatchStat label="Maybe" value={fitResult.summary.maybe} tone="warn" />
            <BatchStat label="Skip" value={fitResult.summary.skip} tone="bad" />
            <BatchStat label="Needs JD" value={fitResult.summary.needs_jd} />
            <BatchStat label="Claude calls" value={fitResult.summary.llm_calls} />
            <BatchStat label="Cached" value={fitResult.summary.cached} />
          </div>
        )}

        <div className="batch-inbox-list">
          {inbox.length ? inbox.map((item) => {
            const fit = item.fit_gate;
            const hasCompleteFit = fit?.evaluation_status === "complete";
            const needsJd = !item.jd_text || item.jd_text.trim().length < 80 || fit?.evaluation_status === "needs_jd";
            const jdEditorOpen = Object.prototype.hasOwnProperty.call(jdEditors, item.loop_id);
            const reviewOpen = reviewItemId === item.loop_id;
            const decisionTone = fit?.decision === "apply" ? "good" : fit?.decision === "skip" ? "bad" : "warn";
            return (
              <article className={`batch-inbox-item ${hasCompleteFit ? `fit-${fit.decision}` : ""}`} key={item.loop_id}>
                <div className="batch-inbox-title">
                  <div>
                    <h3>{item.role}</h3>
                    <p>{item.company}</p>
                  </div>
                  <div className="fit-tag-stack">
                    {fit && <span className={`tag ${fit.evaluation_status === "needs_jd" ? "warn" : decisionTone}`}>{fit.evaluation_status === "needs_jd" ? "needs JD" : fit.decision}</span>}
                    <span className="tag blue">{item.state.replaceAll("_", " ")}</span>
                  </div>
                </div>
                <div className="batch-inbox-meta">
                  <span>{item.source}</span>
                  <span>{formatDateTime(item.created_at)}</span>
                  {item.jd_text && <span>JD saved</span>}
                  {fit?.used_llm && <span>{fit.llm_model || "Claude"}{fit.cache_hit ? " / cached" : ""}</span>}
                  {fit && !fit.used_llm && <span>Deterministic</span>}
                  {fit?.overridden && <span>Human override</span>}
                </div>
                {item.job_url && (
                  <a className="batch-job-link" href={item.job_url} target="_blank" rel="noreferrer">
                    <ExternalLink size={15} />
                    <span>{item.job_url}</span>
                  </a>
                )}

                {fit && (
                  <section className="fit-result-panel">
                    <div className="fit-result-score">
                      <strong>{fit.score}</strong>
                      <span>fit score</span>
                    </div>
                    <p>{fit.one_line_reason}</p>
                  </section>
                )}
                {fit?.overridden && <p className="fit-override-note"><strong>Override:</strong> {fit.override_note}</p>}

                {hasCompleteFit && (
                  <details className="fit-evidence">
                    <summary>Fit evidence</summary>
                    <FitSignal label="Sponsorship" value={fit.sponsorship_note} />
                    <FitSignal label="Seniority" value={fit.seniority_note} />
                    <FitSignal label="Location" value={fit.location_note} />
                    <FitSignal label="Title fit" value={fit.title_fit_note} />
                    <FitSignal label="Skills fit" value={fit.skills_fit_note} />
                  </details>
                )}

                <div className="fit-item-actions">
                  {item.state === "imported" && needsJd && (
                    <button className="icon-button secondary" onClick={() => jdEditorOpen ? closeJdEditor(item.loop_id) : openJdEditor(item)} disabled={Boolean(busy)}>
                      <FilePenLine size={16} />
                      <span>{jdEditorOpen ? "Close JD" : "Add JD"}</span>
                    </button>
                  )}
                  {hasCompleteFit && (
                    <button className="icon-button secondary" onClick={() => openReview(item)} disabled={Boolean(busy)}>
                      <Eye size={16} />
                      <span>{reviewOpen ? "Close review" : "Review"}</span>
                    </button>
                  )}
                  {item.state === "fit_checked" && hasCompleteFit && (
                    <button className="icon-button ghost compact-icon" title="Recheck Fit Gate; may use Claude" onClick={() => runFitGate([item.loop_id], true)} disabled={Boolean(busy)}>
                      {busy === `fit:${item.loop_id}` ? <Loader2 className="spin" size={16} /> : <RotateCcw size={16} />}
                    </button>
                  )}
                </div>

                {jdEditorOpen && (
                  <div className="fit-inline-editor">
                    <label>
                      <span>Full job description</span>
                      <textarea
                        value={jdEditors[item.loop_id] || ""}
                        onChange={(event) => setJdEditors((current) => ({ ...current, [item.loop_id]: event.target.value }))}
                        placeholder="Paste the complete JD"
                      />
                    </label>
                    <button className="icon-button primary" onClick={() => saveJd(item)} disabled={(jdEditors[item.loop_id] || "").trim().length < 20 || Boolean(busy)}>
                      {busy === `jd:${item.loop_id}` ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
                      <span>Save JD</span>
                    </button>
                  </div>
                )}

                {reviewOpen && (
                  <div className="fit-review-panel">
                    <label>
                      <span>Override reason</span>
                      <textarea value={overrideNote} onChange={(event) => setOverrideNote(event.target.value)} placeholder="Record why your judgment differs" />
                    </label>
                    <div className="fit-decision-control" aria-label="Override Fit Gate decision">
                      <button className="decision-apply" onClick={() => overrideFit(item, "apply")} disabled={overrideNote.trim().length < 3 || Boolean(busy)}>
                        <CheckCircle2 size={16} />
                        <span>Apply</span>
                      </button>
                      <button className="decision-maybe" onClick={() => overrideFit(item, "maybe")} disabled={overrideNote.trim().length < 3 || Boolean(busy)}>
                        <CircleHelp size={16} />
                        <span>Maybe</span>
                      </button>
                      <button className="decision-skip" onClick={() => overrideFit(item, "skip")} disabled={overrideNote.trim().length < 3 || Boolean(busy)}>
                        <XCircle size={16} />
                        <span>Skip</span>
                      </button>
                    </div>
                  </div>
                )}
              </article>
            );
          }) : (
            <div className="batch-empty">
              <Inbox size={26} />
              <strong>Inbox is empty</strong>
            </div>
          )}
        </div>
      </aside>
    </section>
  );
}

function BatchStat({ label, value, tone = "neutral" }) {
  return (
    <div className={`batch-stat ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FitSignal({ label, value }) {
  return (
    <div className="fit-signal">
      <span>{label}</span>
      <p>{value || "Needs review."}</p>
    </div>
  );
}

function ManualJDWorkspace() {
  const [form, setForm] = React.useState({
    company: "",
    role: "",
    location: "United States",
    source: "Unknown",
    applied_using: "",
    salary_quoted: "N/A",
    link: "",
    jd_text: "",
    use_llm: false
  });
  const [analysis, setAnalysis] = React.useState(null);
  const [confirmed, setConfirmed] = React.useState(false);
  const [technicalIssue, setTechnicalIssue] = React.useState(false);
  const [busy, setBusy] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [error, setError] = React.useState("");

  function updateField(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function analyze() {
    setBusy("analyze");
    setError("");
    setMessage("");
    setAnalysis(null);
    try {
      const result = await apiPost("/copilot/analyze-jd", form);
      setAnalysis(result);
      setMessage("JD analyzed and apply plan prepared for review.");
    } catch (err) {
      setError(err.message || "Could not analyze JD.");
    } finally {
      setBusy("");
    }
  }

  async function logApplication() {
    if (!analysis) return;
    setBusy("log");
    setError("");
    setMessage("");
    try {
      const result = await apiPost("/copilot/confirm-log", {
        lead_id: analysis.lead_id,
        company: form.company,
        role: form.role,
        link: form.link,
        salary_quoted: form.salary_quoted || "N/A",
        source: form.source || "Unknown",
        applied_using: form.applied_using,
        status: technicalIssue ? "Not Yet Applied Due to Technical Issue" : "Applied",
        human_confirmed_submission: confirmed,
        technical_issue: technicalIssue
      });
      setMessage(result.message);
    } catch (err) {
      setError(err.message || "Could not log application.");
    } finally {
      setBusy("");
    }
  }

  const canAnalyze = form.company.trim() && form.role.trim() && form.jd_text.trim().length >= 20;
  const canLog = Boolean(analysis) && (technicalIssue || confirmed);
  const match = analysis?.match || {};
  const plan = analysis?.apply_plan || null;
  const tailoring = analysis?.tailoring || {};

  return (
    <section className="manual-grid">
      <section className="manual-editor" aria-label="Manual JD input">
        <div className="manual-fields">
          <label>
            <span>Company</span>
            <input value={form.company} onChange={(event) => updateField("company", event.target.value)} />
          </label>
          <label>
            <span>Role</span>
            <input value={form.role} onChange={(event) => updateField("role", event.target.value)} />
          </label>
          <label>
            <span>Location</span>
            <input value={form.location} onChange={(event) => updateField("location", event.target.value)} />
          </label>
          <label>
            <span>Salary</span>
            <input value={form.salary_quoted} onChange={(event) => updateField("salary_quoted", event.target.value)} />
          </label>
          <label>
            <span>Source</span>
            <input value={form.source} onChange={(event) => updateField("source", event.target.value)} placeholder="Jobright AI, LinkedIn, Company Website" />
          </label>
          <label>
            <span>Applied Using</span>
            <select value={form.applied_using} onChange={(event) => updateField("applied_using", event.target.value)}>
              <option value="">Infer from source/link</option>
              <option value="LinkedIn">LinkedIn</option>
              <option value="Indeed">Indeed</option>
              <option value="Company Website">Company Website</option>
              <option value="ZipRecruiter">ZipRecruiter</option>
              <option value="Jobright.ai">Jobright.ai</option>
            </select>
          </label>
        </div>
        <label className="manual-url">
          <span>Canonical Link</span>
          <input value={form.link} onChange={(event) => updateField("link", event.target.value)} />
        </label>
        <label className="jd-box">
          <span>Job Description</span>
          <textarea value={form.jd_text} onChange={(event) => updateField("jd_text", event.target.value)} />
        </label>
        <div className="manual-actions">
          <Toggle label="Use LLM" checked={form.use_llm} onChange={(value) => updateField("use_llm", value)} />
          <button className="icon-button primary" onClick={analyze} disabled={!canAnalyze || busy === "analyze"}>
            {busy === "analyze" ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />}
            Analyze JD
          </button>
        </div>
        {(message || error) && (
          <div className={`notice ${error ? "notice-bad" : "notice-good"}`}>
            {error ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
            <span>{error || message}</span>
          </div>
        )}
      </section>

      <aside className="manual-results" aria-label="Manual JD analysis">
        {analysis ? (
          <>
            <div className="manual-score">
              <div>
                <p>{match.label || match.verdict || "Review"}</p>
                <h2>{plan?.recommendation?.replace("_", " ") || "manual review"}</h2>
              </div>
              <ScoreRing score={Number(match.score || 0)} tone={match.verdict === "skip" ? "bad" : Number(match.score || 0) >= 78 ? "good" : "warn"} />
            </div>
            <p className="detail-reason">{match.one_line_reason}</p>
            <InsightGrid strengths={match.strengths || []} gaps={match.gaps || []} risks={match.risks || []} />
            <section className="packet-panel">
              <h3>Apply Plan</h3>
              {(plan?.human_review_required || []).map((item) => <p key={item}>{item}</p>)}
              {(plan?.blocked_actions || []).map((item) => <p className="packet-warning" key={item}>{item}</p>)}
            </section>
            <section className="packet-panel">
              <h3>
                Tailoring Draft
                {tailoring.engine === "ClaudeTailoringService" && <span className="tag good">Dynamic (Claude)</span>}
                {tailoring.engine === "TailoringService" && <span className="tag blue">Rule-based</span>}
              </h3>
              {tailoring.tailored_score ? (
                <p className="detail-reason">Tailored score estimate: {tailoring.tailored_score}%</p>
              ) : null}
              {tailoring.summary_text ? <p>{tailoring.summary_text}</p> : null}
              {(tailoring.changes_summary || []).map((item) => <p key={item}>{item}</p>)}
              {(tailoring.rewritten_bullets || []).length > 0 && (
                <>
                  <h3>Rewritten Bullets</h3>
                  {(tailoring.rewritten_bullets || []).map((bullet, index) => (
                    <p key={index}>• {bullet?.rewritten || bullet?.original || String(bullet)}</p>
                  ))}
                </>
              )}
              {(tailoring.skill_gaps || []).length > 0 && (
                <>
                  <h3>Skill Gaps</h3>
                  {(tailoring.skill_gaps || []).map((gap) => (
                    <p className="packet-warning" key={gap}>{gap}</p>
                  ))}
                </>
              )}
            </section>
            <section className="sheet-preview">
              <h3>Sheet Row Preview</h3>
              {Object.entries(analysis.sheet_preview || {}).map(([key, value]) => (
                <Fact key={key} label={key} value={value || "N/A"} />
              ))}
            </section>
            <div className="confirm-panel">
              <Toggle label="Submitted manually" checked={confirmed} onChange={setConfirmed} />
              <Toggle label="Technical issue" checked={technicalIssue} onChange={setTechnicalIssue} />
              <button className="icon-button primary" onClick={logApplication} disabled={!canLog || busy === "log"}>
                {busy === "log" ? <Loader2 className="spin" size={18} /> : <CheckCircle2 size={18} />}
                Log to Sheet Format
              </button>
            </div>
          </>
        ) : (
          <div className="detail-empty">Paste a JD and run analysis</div>
        )}
      </aside>
    </section>
  );
}

function JobCard({ row, active, action, onSelect, onAlreadyApplied, onPrepare }) {
  const { job, analysis, url } = row;
  const score = Number(analysis.score || 0);
  const verdict = analysis.verdict || "review";
  const riskTone = verdict === "skip" ? "bad" : score >= 78 ? "good" : "warn";
  const isApplied = row.applied || row.hidden_reason === "already_applied";
  const sponsor = sponsorSummary(job);
  const lastVerified = lastVerifiedText(job);
  const whyShown = whyShownText(job, analysis);
  return (
    <article className={`job-card ${active ? "active" : ""}`} onClick={onSelect}>
      <div className="job-main">
        <div>
          <h3>{job.title || "Untitled role"}</h3>
          <p>{job.company || "Unknown company"} - {job.source || "Unknown source"}</p>
        </div>
        <ScoreRing score={score} tone={riskTone} />
      </div>
      <div className="job-facts">
        <Fact label="Location" value={job.location || "Not listed"} />
        <Fact label="Posted" value={job.freshness_label || job.posted_at || "Not listed"} />
        <Fact label="Experience" value={analysis.years_required ? `${analysis.years_required} years` : "Not explicit"} />
        <Fact label="Work Auth" value={analysis.sponsorship_note || "Review"} />
      </div>
      <div className="job-proof-row">
        <Fact label="Last verified active" value={lastVerified} />
        <Fact label="Why shown" value={whyShown} />
      </div>
      <p className="reason">{analysis.one_line_reason || "Needs review."}</p>
      <div className="tag-row">
        <span className={`tag ${riskTone}`}>{analysis.label || verdict}</span>
        {analysis.target_role_key && <span className="tag blue">{analysis.target_role_key}</span>}
        {sponsor && <span className="tag sponsor"><ShieldAlert size={13} />{sponsor}</span>}
        {row.hidden_reason && <span className="tag warn">{row.hidden_reason}</span>}
      </div>
      <div className="card-actions" onClick={(event) => event.stopPropagation()}>
        <button onClick={onSelect}><FileText size={16} />Details</button>
        <button className="strong" onClick={onPrepare} disabled={verdict === "skip" || action === `prepare:${row.key}`}>
          {action === `prepare:${row.key}` ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}Tailor
        </button>
        {url && <a className="button-link" href={url} target="_blank" rel="noreferrer"><ExternalLink size={16} />Open</a>}
        <button onClick={onAlreadyApplied} disabled={isApplied || action === `applied:${row.key}`}>
          {action === `applied:${row.key}` ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
          {isApplied ? "Applied" : "Already Applied"}
        </button>
      </div>
    </article>
  );
}

function JobDetail({ row, prepared, action, onPrepare, onAlreadyApplied }) {
  const { job, analysis, url } = row;
  const risks = analysis.risks || [];
  const gaps = analysis.gaps || [];
  const strengths = analysis.strengths || [];
  const isApplied = row.applied || row.hidden_reason === "already_applied";
  const sponsor = sponsorSummary(job);
  const sponsorEvidence = sponsorEvidenceText(job);
  const lastVerified = lastVerifiedText(job);
  const whyShown = whyShownText(job, analysis);
  return (
    <div>
      <div className="detail-title">
        <div>
          <p>{job.company || "Unknown company"}</p>
          <h2>{job.title || "Untitled role"}</h2>
        </div>
        <ScoreRing score={Number(analysis.score || 0)} tone={analysis.verdict === "skip" ? "bad" : Number(analysis.score || 0) >= 78 ? "good" : "warn"} />
      </div>
      <div className="detail-actions">
        <button className="icon-button primary" onClick={onPrepare} disabled={analysis.verdict === "skip" || action.startsWith("prepare")}>
          {action.startsWith("prepare") ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />}Tailor Resume
        </button>
        {url && <a className="icon-button secondary" href={url} target="_blank" rel="noreferrer"><ExternalLink size={18} />Open Job</a>}
        <button className="icon-button ghost" onClick={onAlreadyApplied} disabled={isApplied || action === `applied:${row.key}`}>
          {action === `applied:${row.key}` ? <Loader2 className="spin" size={18} /> : <CheckCircle2 size={18} />}
          {isApplied ? "Applied" : "Already Applied"}
        </button>
      </div>
      <div className="detail-metrics">
        <Fact label="Verdict" value={analysis.label || analysis.verdict || "Review"} />
        <Fact label="Mode" value={(analysis.scoring_mode || "score").replaceAll("_", " ")} />
        <Fact label="Role" value={analysis.target_role_key || "Inferred"} />
        <Fact label="Years" value={analysis.years_required ? `${analysis.years_required}` : "Not explicit"} />
      </div>
      <div className="detail-source-panel">
        <Fact label="Source" value={job.source || "Not listed"} />
        <Fact label="DOL Sponsor" value={sponsor || "No DOL match"} />
        <Fact label="LCA Evidence" value={sponsorEvidence || "Not listed"} />
      </div>
      <div className="detail-proof-panel">
        <Fact label="Last verified active" value={lastVerified} />
        <Fact label="Why shown" value={whyShown} />
      </div>
      <p className="detail-reason">{analysis.one_line_reason}</p>
      <InsightGrid strengths={strengths} gaps={gaps} risks={risks} />
      {prepared && (
        <section className="packet-panel">
          <h3>Tailored Resume</h3>
          {prepared.pdf_error && <p className="packet-warning">PDF was not created. Use the HTML resume artifact below.</p>}
          <PathLine label="Resume DOCX" value={prepared.prepared_resume_docx_path || (String(prepared.prepared_resume_path || "").endsWith(".docx") ? prepared.prepared_resume_path : "")} />
          <PathLine label="Resume PDF" value={prepared.prepared_resume_pdf_path} />
          <PathLine label="Resume HTML" value={prepared.prepared_resume_html_path} />
          {!prepared.prepared_resume_pdf_path && !prepared.prepared_resume_html_path && <PathLine label="Resume artifact" value={prepared.prepared_resume_path} />}
          {!prepared.prepared_resume_pdf_path && <PathLine label="PDF target" value={prepared.intended_resume_pdf_path} />}
          <PathLine label="Apply plan" value={prepared.prepared_apply_plan_path || prepared.matched_apply_plan_path} />
          <PathLine label="Artifact folder" value={prepared.prepared_packet_folder_path} />
        </section>
      )}
    </div>
  );
}

function InsightGrid({ strengths, gaps, risks }) {
  return (
    <div className="insight-grid">
      <InsightColumn title="Strengths" icon={CheckCircle2} items={strengths} />
      <InsightColumn title="Gaps" icon={AlertTriangle} items={gaps} />
      <InsightColumn title="Risks" icon={ShieldAlert} items={risks} danger />
    </div>
  );
}

function InsightColumn({ title, icon: Icon, items, danger }) {
  return (
    <section className={`insight-column ${danger ? "danger" : ""}`}>
      <h3><Icon size={16} />{title}</h3>
      {items.length ? items.map((item) => <p key={item}>{item}</p>) : <p>None listed.</p>}
    </section>
  );
}

function Fact({ label, value }) {
  return (
    <div className="fact">
      <span>{label}</span>
      <strong>{String(value || "Not listed")}</strong>
    </div>
  );
}

function sponsorSummary(job) {
  if (!job?.is_h1b_sponsor && !job?.h1b_sponsor_employer) return "";
  return job.h1b_sponsor_employer ? `H-1B: ${job.h1b_sponsor_employer}` : "H-1B sponsor history";
}

function sponsorEvidenceText(job) {
  const relevant = Number(job?.h1b_relevant_lca_count || 0);
  const entry = Number(job?.h1b_entry_level_lca_count || 0);
  const year = job?.h1b_fiscal_year;
  const quarter = job?.h1b_quarter;
  const parts = [];
  if (entry) parts.push(`${entry} entry-level relevant LCAs`);
  if (relevant) parts.push(`${relevant} relevant LCAs`);
  if (year && quarter) parts.push(`FY${year} Q${quarter}`);
  return parts.join(" - ");
}

function lastVerifiedText(job) {
  const status = String(job?.availability_status || "").toLowerCase();
  const checkedAt = job?.availability_checked_at || job?.freshness_checked_at || job?.loaded_at || "";
  const formatted = formatDateTime(checkedAt);
  if (status === "active" && formatted) return formatted;
  if (status === "active") return "Active in current source";
  if (formatted) return formatted;
  return "Not listed";
}

function whyShownText(job, analysis) {
  const signals = Array.isArray(job?.quality_signals) ? job.quality_signals.filter(Boolean) : [];
  const reasons = Array.isArray(job?.quality_reasons) ? job.quality_reasons.filter(Boolean) : [];
  const availability = String(job?.availability_reason || "").trim();
  const source = String(job?.source || "").toLowerCase();
  if (availability && signals.length) return `${availability} ${signals[0]}`;
  if (availability) return availability;
  if (signals.length) return signals[0];
  if (reasons.length) return reasons[0];
  if (job?.is_h1b_sponsor) return "DOL sponsor signal and role gate passed.";
  if (source.includes("greenhouse") || source.includes("ashby") || source.includes("lever")) return "Official ATS board and role gate passed.";
  return analysis?.one_line_reason || "Passed current role, location, and work authorization gates.";
}

function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  });
}

function ScoreRing({ score, tone }) {
  return (
    <div className={`score-ring ${tone}`}>
      <strong>{score}%</strong>
    </div>
  );
}

function PathLine({ label, value }) {
  if (!value) return null;
  return (
    <div className="path-line">
      <span>{label}</span>
      <code>{value}</code>
    </div>
  );
}

function EmptyState({ feed }) {
  return (
    <div className="empty-state">
      <BriefcaseBusiness size={28} />
      <h2>{feed === "fresh24" ? "No fresh matches" : feed === "applied" ? "No already-applied jobs" : "No matching jobs"}</h2>
    </div>
  );
}

function SkeletonList() {
  return Array.from({ length: 4 }).map((_, index) => <div className="skeleton-card" key={index} />);
}

async function apiGet(path) {
  const response = await fetch(`${API_BASE}${path}`);
  return readResponse(response);
}

async function apiPost(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  return readResponse(response);
}

async function apiPut(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  return readResponse(response);
}

async function readResponse(response) {
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || response.statusText);
  }
  return payload;
}

createRoot(document.getElementById("root")).render(<App />);
