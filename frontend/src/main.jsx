import React from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  BarChart3,
  Bot,
  BriefcaseBusiness,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  Clock3,
  Copy,
  Download,
  ExternalLink,
  Eye,
  FilePenLine,
  FileText,
  FolderOpen,
  Gauge,
  Inbox,
  Link2,
  Loader2,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Timer,
  Trash2,
  TrendingUp,
  Upload,
  Users,
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
  const standaloneWorkspace = feed === "manual" || feed === "batch" || feed === "metrics";
  const feedTitle =
    feed === "manual"
      ? "Manual JD Review"
      : feed === "batch"
        ? "Ten-Job Batch Inbox"
        : feed === "metrics"
          ? "Loop Metrics"
        : feed === "fresh24"
          ? "Fresh 24h Jobs"
          : feed === "applied"
            ? "Already Applied"
            : "Recommended Jobs";

  const loadDashboard = React.useCallback(async () => {
    if (feed === "manual" || feed === "batch" || feed === "metrics") {
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
          <RailButton active={feed === "metrics"} icon={BarChart3} label="Loop Metrics" onClick={() => setFeed("metrics")} />
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
              <StatusPill tone="neutral" icon={Bot} text={feed === "manual" ? "Paste JD analysis" : feed === "batch" ? "Deterministic intake" : feed === "metrics" ? "Local loop history" : filters.useLlm ? "LLM scoring" : "Deterministic scoring"} />
              <StatusPill tone="neutral" icon={Eye} text={feed === "metrics" ? "Zero model calls" : standaloneWorkspace ? "Human review" : "Browser watcher fills"} />
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
        ) : feed === "metrics" ? (
          <LoopMetricsDashboard />
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

function Toggle({ label, checked, onChange, disabled = false }) {
  return (
    <label className={`toggle-control ${disabled ? "disabled" : ""}`}>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} disabled={disabled} />
      <span />
      <strong>{label}</strong>
    </label>
  );
}

const METRICS_WINDOWS = [
  ["today", "Today"],
  ["7d", "7 days"],
  ["30d", "30 days"],
  ["all", "All time"]
];

function LoopMetricsDashboard() {
  const [windowKey, setWindowKey] = React.useState("7d");
  const [metrics, setMetrics] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const loadMetrics = React.useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setMetrics(await apiGet(`/application-loop/metrics?window=${windowKey}`));
    } catch (err) {
      setError(err.message || "Could not load loop metrics.");
    } finally {
      setLoading(false);
    }
  }, [windowKey]);

  React.useEffect(() => {
    loadMetrics();
  }, [loadMetrics]);

  const summary = metrics?.summary;
  return (
    <section className="metrics-workspace" aria-label="Application loop metrics">
      <div className="metrics-controls">
        <div className="metrics-window-control" aria-label="Metrics time window">
          {METRICS_WINDOWS.map(([value, label]) => (
            <button className={windowKey === value ? "active" : ""} onClick={() => setWindowKey(value)} key={value}>
              {label}
            </button>
          ))}
        </div>
        <div className="metrics-refresh">
          {metrics?.generated_at && <span>Updated {formatDateTime(metrics.generated_at)}</span>}
          <button className="icon-button ghost compact-icon" title="Refresh metrics" onClick={loadMetrics} disabled={loading}>
            {loading ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
          </button>
        </div>
      </div>

      {error && (
        <div className="notice notice-bad">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}

      {loading && !metrics ? (
        <div className="metrics-loading">
          <Loader2 className="spin" size={24} />
          <span>Calculating loop history</span>
        </div>
      ) : summary ? (
        <>
          <section className="metrics-kpi-strip" aria-label="Loop summary">
            <MetricKpi label="Applications" value={summary.total_applications} />
            <MetricKpi label="Submitted" value={summary.submitted} tone="good" />
            <MetricKpi label="Skipped" value={summary.skipped} tone="warn" />
            <MetricKpi label="Portal issues" value={summary.portal_issues} tone="bad" />
            <MetricKpi label="Avg revisions" value={summary.average_revisions_per_tailored.toFixed(1)} />
            <MetricKpi label="Avg score lift" value={`+${summary.average_tailoring_score_lift.toFixed(1)}`} suffix="pts" tone="blue" />
          </section>

          <section className="metrics-bottleneck" aria-label="Current loop bottleneck">
            <Timer size={22} />
            <div>
              <span>Slowest completed stage</span>
              <strong>{metrics.bottleneck.label}</strong>
            </div>
            <div className="metrics-bottleneck-value">
              <strong>{formatMetricDuration(metrics.bottleneck.average_minutes)}</strong>
              <span>{metrics.bottleneck.sample_count} sample{metrics.bottleneck.sample_count === 1 ? "" : "s"}</span>
            </div>
          </section>

          <div className="metrics-main-grid">
            <section className="metrics-band" aria-label="Application funnel">
              <MetricsSectionHeader icon={TrendingUp} title="Milestone funnel" meta={`${metrics.window_label} / reached at least once`} />
              <div className="metrics-funnel">
                {metrics.funnel.map((stage) => (
                  <div className={`metrics-funnel-row ${stage.kind === "exit" ? "exit" : ""}`} key={stage.state}>
                    <span>{stage.label}</span>
                    <div className="metrics-funnel-track">
                      <i style={{ width: `${stage.percent_of_imported}%` }} />
                    </div>
                    <strong>{stage.count}</strong>
                    <small>{stage.percent_of_imported.toFixed(1)}%</small>
                  </div>
                ))}
              </div>
            </section>

            <section className="metrics-band" aria-label="Stage timing">
              <MetricsSectionHeader icon={Timer} title="Stage timing" meta="Completed transitions only" />
              <div className="metrics-timing-list">
                {metrics.stage_timings.map((timing) => (
                  <div className="metrics-timing-row" key={timing.key}>
                    <span>{timing.label}</span>
                    <strong>{timing.sample_count ? formatMetricDuration(timing.average_minutes) : "--"}</strong>
                    <small>median {timing.sample_count ? formatMetricDuration(timing.median_minutes) : "--"}</small>
                    <small>{timing.sample_count} sample{timing.sample_count === 1 ? "" : "s"}</small>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <section className="metrics-rate-strip" aria-label="Loop completion rates">
            <MetricRate label="Application submission" value={summary.submission_rate} />
            <MetricRate label="Sheets logging after submit" value={summary.sheet_logging_rate} />
            <MetricRate label="Recruiter outreach after submit" value={summary.outreach_completion_rate} />
            <div className="metrics-time-to-submit">
              <span>Average intake to submission</span>
              <strong>{formatMetricDuration(summary.average_minutes_to_submission)}</strong>
            </div>
          </section>

          <div className="metrics-reasons-grid">
            <MetricReasonList title="Skip reasons" rows={metrics.skip_reasons} empty="No skips in this window" tone="warn" />
            <MetricReasonList title="Portal failure reasons" rows={metrics.portal_failure_reasons} empty="No portal failures in this window" tone="bad" />
            <section className="metrics-band metrics-state-band" aria-label="Current state distribution">
              <MetricsSectionHeader icon={BarChart3} title="Current states" meta={`${summary.total_applications} active records`} />
              <div className="metrics-state-list">
                {Object.entries(metrics.current_state_counts).length ? Object.entries(metrics.current_state_counts).map(([state, count]) => (
                  <div key={state}>
                    <span>{state.replaceAll("_", " ")}</span>
                    <strong>{count}</strong>
                  </div>
                )) : <p>No application records in this window</p>}
              </div>
            </section>
          </div>
        </>
      ) : null}
    </section>
  );
}

function MetricKpi({ label, value, suffix = "", tone = "neutral" }) {
  return (
    <div className={`metrics-kpi ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {suffix && <small>{suffix}</small>}
    </div>
  );
}

function MetricsSectionHeader({ icon: Icon, title, meta }) {
  return (
    <header className="metrics-section-header">
      <Icon size={18} />
      <div>
        <h2>{title}</h2>
        <span>{meta}</span>
      </div>
    </header>
  );
}

function MetricRate({ label, value }) {
  return (
    <div className="metrics-rate">
      <div><span>{label}</span><strong>{value.toFixed(1)}%</strong></div>
      <div className="metrics-rate-track"><i style={{ width: `${value}%` }} /></div>
    </div>
  );
}

function MetricReasonList({ title, rows, empty, tone }) {
  return (
    <section className={`metrics-band metrics-reason-band ${tone}`}>
      <header><h2>{title}</h2><span>{rows.length} grouped reason{rows.length === 1 ? "" : "s"}</span></header>
      {rows.length ? rows.map((row) => (
        <div className="metrics-reason-row" key={row.reason}>
          <p>{row.reason}</p>
          <strong>{row.count}</strong>
        </div>
      )) : <p className="metrics-empty-copy">{empty}</p>}
    </section>
  );
}

function formatMetricDuration(minutes) {
  const value = Number(minutes || 0);
  if (!value) return "0m";
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)}m`;
  if (value < 1440) {
    const hours = Math.floor(value / 60);
    const remaining = Math.round(value % 60);
    return remaining ? `${hours}h ${remaining}m` : `${hours}h`;
  }
  const days = Math.floor(value / 1440);
  const hours = Math.round((value % 1440) / 60);
  return hours ? `${days}d ${hours}h` : `${days}d`;
}

const BATCH_SOURCES = ["Jobright AI", "LinkedIn", "Referral", "Company Website", "Simplify", "TikTok", "Cognizant", "Unknown"];
const TAILORING_EMPHASIS = [
  ["summary", "Summary"],
  ["experience", "Experience"],
  ["projects", "Projects"],
  ["skills", "Skills"],
  ["research_papers", "Research papers"]
];
let batchEntrySequence = 0;

function newTailoringPreferences(source = {}) {
  const counts = source.bullet_counts || {};
  return {
    preset: source.preset || "balanced",
    rewrite_intensity: source.rewrite_intensity || "balanced",
    emphasis: Array.isArray(source.emphasis) ? [...source.emphasis] : ["summary", "experience", "projects", "skills"],
    custom_instructions: source.custom_instructions || "",
    include_connection_note: Boolean(source.include_connection_note),
    include_cover_letter: Boolean(source.include_cover_letter),
    bullet_counts: {
      experience_per_role: Number(counts.experience_per_role ?? 3),
      projects_per_project: Number(counts.projects_per_project ?? 2),
      research_per_paper: Number(counts.research_per_paper ?? 2)
    }
  };
}

function reviewSelectionFromDraft(draft) {
  return {
    draft_id: draft.draft_id,
    summary_accepted: true,
    summary_text: draft.summary_proposed || draft.summary_original || "",
    bullets: (draft.bullets || []).map((bullet) => ({
      bullet_id: bullet.bullet_id,
      accepted: true,
      text: bullet.proposed || bullet.original || ""
    })),
    project_ids: (draft.projects || []).filter((project) => project.selected !== false).map((project) => project.project_id),
    publication_ids: (draft.publications || []).filter((paper) => paper.selected !== false).map((paper) => paper.publication_id),
    bullet_counts: { ...newTailoringPreferences(draft.preferences).bullet_counts },
    connection_note: draft.connection_note || "",
    cover_letter_accepted: true,
    cover_letter_text: draft.cover_letter_text || ""
  };
}

function tailoringEngineLabel(value) {
  if (value?.engine === "TailoringService" && value?.claude_call_consumed && value?.model) {
    return `Rule-based fallback after ${value.model}`;
  }
  if (value?.engine === "TailoringService") return "Rule-based";
  return value?.model || value?.engine || "Local";
}

function atsStatusLabel(value) {
  return {
    armed: "Waiting for Third Eye",
    safe_fields_filled: "Safe fields filled",
    review_required: "Manual review needed",
    technical_issue: "Portal issue",
    submitted_confirmed: "Submitted manually"
  }[value] || "Not started";
}

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
  const [tailoringItemId, setTailoringItemId] = React.useState("");
  const [tailoringPreferences, setTailoringPreferences] = React.useState(() => newTailoringPreferences());
  const [revisionReason, setRevisionReason] = React.useState("");
  const [draftReview, setDraftReview] = React.useState(null);
  const [reviewSelection, setReviewSelection] = React.useState(null);
  const [approvalNote, setApprovalNote] = React.useState("");
  const [exportRoot, setExportRoot] = React.useState("");
  const [renderExportPdf, setRenderExportPdf] = React.useState(true);
  const [atsPanelId, setAtsPanelId] = React.useState("");
  const [atsNotes, setAtsNotes] = React.useState({});
  const [submissionConfirmations, setSubmissionConfirmations] = React.useState({});
  const [outreachPanelId, setOutreachPanelId] = React.useState("");
  const [outreachDrafts, setOutreachDrafts] = React.useState({});
  const [outreachConfirmations, setOutreachConfirmations] = React.useState({});
  const [outreachOutcomeNotes, setOutreachOutcomeNotes] = React.useState({});
  const [outreachResult, setOutreachResult] = React.useState(null);

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

  function openTailoringOptions(item) {
    const opening = tailoringItemId !== item.loop_id;
    setTailoringItemId(opening ? item.loop_id : "");
    setTailoringPreferences(newTailoringPreferences());
    setRevisionReason("");
    setReviewItemId("");
    setOverrideNote("");
  }

  function showDraftReview(result) {
    setDraftReview(result);
    setReviewSelection(
      result.loop_item?.tailoring_approval?.review
        ? structuredClone(result.loop_item.tailoring_approval.review)
        : reviewSelectionFromDraft(result.draft)
    );
    setTailoringPreferences(newTailoringPreferences(result.draft.preferences));
    setRevisionReason("");
    setApprovalNote(result.loop_item?.tailoring_approval?.note || "");
    setExportRoot(result.loop_item?.export_handoff?.output_root_override || "");
    setRenderExportPdf(result.loop_item?.export_handoff?.render_pdf_requested ?? true);
  }

  async function createTailoringDraft(item) {
    const isRevision = Boolean(item.tailoring_draft);
    if (isRevision && revisionReason.trim().length < 3) {
      setError("Record what Claude should change before regenerating the draft.");
      return;
    }
    setBusy(`tailor:${item.loop_id}`);
    setError("");
    setMessage("");
    try {
      const result = await apiPost(`/application-loop/items/${item.loop_id}/tailoring/drafts`, {
        preferences: tailoringPreferences,
        revision_reason: revisionReason.trim()
      });
      showDraftReview(result);
      setTailoringItemId("");
      setMessage(isRevision ? `Draft v${result.loop_item.tailoring_draft.version} is ready for review.` : "Tailored draft is ready for review.");
      await loadInbox();
    } catch (err) {
      setError(err.message || "Could not create the tailoring draft.");
    } finally {
      setBusy("");
    }
  }

  async function openTailoringDraft(item) {
    setBusy(`draft:${item.loop_id}`);
    setError("");
    try {
      const result = await apiGet(`/application-loop/items/${item.loop_id}/tailoring/draft`);
      showDraftReview(result);
    } catch (err) {
      setError(err.message || "Could not reopen the tailoring draft.");
    } finally {
      setBusy("");
    }
  }

  async function refreshTailoringPreview() {
    if (!draftReview || !reviewSelection) return;
    setBusy(`preview:${draftReview.loop_item.loop_id}`);
    setError("");
    try {
      const result = await apiPost(
        `/application-loop/items/${draftReview.loop_item.loop_id}/tailoring/preview`,
        reviewSelection
      );
      setDraftReview((current) => ({
        ...current,
        draft: { ...current.draft, resume_preview_html: result.resume_preview_html }
      }));
      setMessage("Preview refreshed locally.");
    } catch (err) {
      setError(err.message || "Could not refresh the resume preview.");
    } finally {
      setBusy("");
    }
  }

  async function approveTailoringDraft() {
    if (!draftReview || !reviewSelection) return;
    if (approvalNote.trim().length < 3) {
      setError("Add a short approval note before accepting the draft.");
      return;
    }
    const loopId = draftReview.loop_item.loop_id;
    setBusy(`approve:${loopId}`);
    setError("");
    try {
      const result = await apiPost(`/application-loop/items/${loopId}/tailoring/approve`, {
        ...reviewSelection,
        approval_note: approvalNote.trim()
      });
      setDraftReview((current) => ({
        ...current,
        loop_item: result.loop_item,
        draft: { ...current.draft, resume_preview_html: result.resume_preview_html }
      }));
      setMessage(result.message);
      await loadInbox();
    } catch (err) {
      setError(err.message || "Could not approve this tailoring draft.");
    } finally {
      setBusy("");
    }
  }

  async function exportApprovedTailoring() {
    if (!draftReview?.loop_item?.tailoring_approval) return;
    const loopId = draftReview.loop_item.loop_id;
    setBusy(`export:${loopId}`);
    setError("");
    try {
      const result = await apiPost(`/application-loop/items/${loopId}/tailoring/export`, {
        output_root_override: exportRoot.trim(),
        render_pdf: renderExportPdf,
        human_confirmed_export: true
      });
      setDraftReview((current) => ({ ...current, loop_item: result.loop_item }));
      setMessage(result.message);
      await loadInbox();
    } catch (err) {
      setError(err.message || "Could not generate the approved resume files.");
    } finally {
      setBusy("");
    }
  }

  function replaceLoopItem(loopItem) {
    if (!loopItem) return;
    setInbox((current) => current.map((item) => item.loop_id === loopItem.loop_id ? loopItem : item));
    setDraftReview((current) => (
      current?.loop_item?.loop_id === loopItem.loop_id
        ? { ...current, loop_item: loopItem }
        : current
    ));
  }

  async function armAtsAssist(item) {
    const pendingWindow = window.open("about:blank", "_blank");
    setBusy(`ats-arm:${item.loop_id}`);
    setError("");
    setMessage("");
    try {
      const result = await apiPost(`/application-loop/items/${item.loop_id}/ats-assist/arm`, {
        expires_minutes: 30,
        quality_review_note: item.export_handoff?.quality_passed ? "" : String(atsNotes[item.loop_id] || "").trim()
      });
      replaceLoopItem(result.loop_item);
      setAtsPanelId(item.loop_id);
      setAtsNotes((current) => ({ ...current, [item.loop_id]: "" }));
      setMessage(result.message);
      if (pendingWindow) pendingWindow.location.replace(result.assist.target_url);
      else window.open(result.assist.target_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      pendingWindow?.close();
      setError(err.message || "Could not open ATS Apply Assist.");
    } finally {
      setBusy("");
    }
  }

  async function syncAtsAssist(item) {
    setBusy(`ats-sync:${item.loop_id}`);
    setError("");
    try {
      const result = await apiGet(`/application-loop/items/${item.loop_id}/ats-assist`);
      replaceLoopItem(result.loop_item);
      setMessage(result.message);
    } catch (err) {
      setError(err.message || "Could not refresh the ATS result.");
    } finally {
      setBusy("");
    }
  }

  async function toggleAtsPanel(item) {
    if (atsPanelId === item.loop_id) {
      setAtsPanelId("");
      return;
    }
    setAtsPanelId(item.loop_id);
    if (item.ats_assist) await syncAtsAssist(item);
  }

  async function recordAtsOutcome(item, outcome) {
    const note = String(atsNotes[item.loop_id] || "").trim();
    if (note.length < 3) {
      setError("Add a short outcome note first.");
      return;
    }
    const confirmed = Boolean(submissionConfirmations[item.loop_id]);
    if (outcome === "submitted_confirmed" && !confirmed) {
      setError("Confirm that you manually submitted the application first.");
      return;
    }
    setBusy(`ats-outcome:${item.loop_id}`);
    setError("");
    setMessage("");
    try {
      const result = await apiPost(`/application-loop/items/${item.loop_id}/ats-assist/outcome`, {
        outcome,
        note,
        human_confirmed_submission: outcome === "submitted_confirmed" && confirmed
      });
      replaceLoopItem(result.loop_item);
      setMessage(result.message);
    } catch (err) {
      setError(err.message || "Could not record the ATS outcome.");
    } finally {
      setBusy("");
    }
  }

  function outreachDraftFor(item) {
    return outreachDrafts[item.loop_id] || {
      recruiter_name: item.recruiter_outreach?.recruiter_name || "",
      connection_note: item.recruiter_outreach?.connection_note || ""
    };
  }

  function setOutreachDraft(loopId, field, value) {
    setOutreachDrafts((current) => ({
      ...current,
      [loopId]: { ...(current[loopId] || {}), [field]: value }
    }));
  }

  async function prepareRecruiterOutreach(loopIds, forceRefresh = false) {
    if (!loopIds.length) return;
    const busyKey = loopIds.length === 1 && forceRefresh ? `outreach-regenerate:${loopIds[0]}` : "outreach-batch";
    setBusy(busyKey);
    setError("");
    setMessage("");
    try {
      const result = await apiPost("/application-loop/recruiter-outreach/batches", {
        loop_ids: loopIds,
        use_llm: useClaude,
        force_refresh: forceRefresh
      });
      setOutreachResult(result);
      result.outcomes.forEach((outcome) => {
        replaceLoopItem(outcome.loop_item);
        if (outcome.outreach) {
          setOutreachDrafts((current) => ({
            ...current,
            [outcome.loop_id]: {
              recruiter_name: outcome.outreach.recruiter_name || "",
              connection_note: outcome.outreach.connection_note || ""
            }
          }));
        }
      });
      setMessage(
        `${result.summary.ready} note${result.summary.ready === 1 ? "" : "s"} prepared, ` +
        `${result.summary.cached} cached, ${result.summary.llm_calls} Claude call${result.summary.llm_calls === 1 ? "" : "s"}.`
      );
      await loadInbox();
    } catch (err) {
      setError(err.message || "Could not prepare recruiter outreach.");
    } finally {
      setBusy("");
    }
  }

  function toggleOutreachPanel(item) {
    if (outreachPanelId === item.loop_id) {
      setOutreachPanelId("");
      return;
    }
    setOutreachPanelId(item.loop_id);
    setOutreachDrafts((current) => ({
      ...current,
      [item.loop_id]: {
        recruiter_name: item.recruiter_outreach?.recruiter_name || "",
        connection_note: item.recruiter_outreach?.connection_note || ""
      }
    }));
  }

  async function saveRecruiterOutreach(item) {
    const draft = outreachDraftFor(item);
    const note = String(draft.connection_note || "").trim();
    if (note.length < 20 || note.length > 300) {
      setError("The connection note must be between 20 and 300 characters.");
      return;
    }
    setBusy(`outreach-save:${item.loop_id}`);
    setError("");
    try {
      const result = await apiPut(`/application-loop/items/${item.loop_id}/recruiter-outreach`, {
        recruiter_name: String(draft.recruiter_name || "").trim(),
        connection_note: note
      });
      replaceLoopItem(result.loop_item);
      setOutreachDrafts((current) => ({
        ...current,
        [item.loop_id]: {
          recruiter_name: result.outreach.recruiter_name || "",
          connection_note: result.outreach.connection_note
        }
      }));
      setMessage(result.message);
    } catch (err) {
      setError(err.message || "Could not save the recruiter note.");
    } finally {
      setBusy("");
    }
  }

  async function copyRecruiterNote(item) {
    const note = String(outreachDraftFor(item).connection_note || "").trim();
    if (!note) return;
    try {
      await navigator.clipboard.writeText(note);
      setMessage("Connection note copied.");
      setError("");
    } catch {
      setError("The browser could not copy the note. Select the text and copy it manually.");
    }
  }

  async function markRecruiterOutreachSent(item) {
    const note = String(outreachOutcomeNotes[item.loop_id] || "").trim();
    if (note.length < 3 || !outreachConfirmations[item.loop_id]) {
      setError("Confirm the manual LinkedIn send and add a short outcome note.");
      return;
    }
    setBusy(`outreach-sent:${item.loop_id}`);
    setError("");
    try {
      const result = await apiPost(`/application-loop/items/${item.loop_id}/recruiter-outreach/sent`, {
        note,
        human_confirmed_sent: true
      });
      replaceLoopItem(result.loop_item);
      setMessage(result.message);
    } catch (err) {
      setError(err.message || "Could not record recruiter outreach.");
    } finally {
      setBusy("");
    }
  }

  const outcomes = new Map((batchResult?.outcomes || []).map((outcome) => [outcome.entry_id, outcome]));
  const readyCount = entries.filter((entry) => entry.job_url.trim() || entry.jd_text.trim()).length;
  const pendingFitIds = inbox.filter((item) => item.state === "imported").map((item) => item.loop_id);
  const pendingOutreachIds = inbox
    .filter((item) => ["submitted_confirmed", "sheet_logged"].includes(item.state))
    .map((item) => item.loop_id);
  const outreachBatchIds = pendingOutreachIds.slice(0, 10);
  const outreachReadyCount = inbox.filter((item) => item.state === "recruiter_note_ready").length;
  const outreachDoneCount = inbox.filter((item) => item.state === "outreach_done").length;

  return (
    <>
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

        <div className="recruiter-outreach-toolbar">
          <div className="fit-gate-heading">
            <Users size={20} />
            <div>
              <h3>Recruiter outreach</h3>
              <span>{pendingOutreachIds.length} pending / {outreachReadyCount} ready / {outreachDoneCount} sent</span>
            </div>
          </div>
          <Toggle label="Use Claude" checked={useClaude} onChange={setUseClaude} />
          <button className="icon-button primary" onClick={() => prepareRecruiterOutreach(outreachBatchIds)} disabled={!outreachBatchIds.length || Boolean(busy)}>
            {busy === "outreach-batch" ? <Loader2 className="spin" size={17} /> : <Users size={17} />}
            <span>Prepare {outreachBatchIds.length || ""} note{outreachBatchIds.length === 1 ? "" : "s"}</span>
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

        {outreachResult && (
          <div className="outreach-summary" aria-label="Latest recruiter outreach batch summary">
            <BatchStat label="Companies" value={outreachResult.summary.companies} />
            <BatchStat label="Ready" value={outreachResult.summary.ready} tone="good" />
            <BatchStat label="Cached" value={outreachResult.summary.cached} />
            <BatchStat label="Claude calls" value={outreachResult.summary.llm_calls} />
          </div>
        )}

        <div className="batch-inbox-list">
          {inbox.length ? inbox.map((item) => {
            const fit = item.fit_gate;
            const hasCompleteFit = fit?.evaluation_status === "complete";
            const needsJd = !item.jd_text || item.jd_text.trim().length < 80 || fit?.evaluation_status === "needs_jd";
            const jdEditorOpen = Object.prototype.hasOwnProperty.call(jdEditors, item.loop_id);
            const reviewOpen = reviewItemId === item.loop_id;
            const tailoringOpen = tailoringItemId === item.loop_id;
            const atsPanelOpen = atsPanelId === item.loop_id;
            const outreachPanelOpen = outreachPanelId === item.loop_id;
            const outreachDraft = outreachDraftFor(item);
            const hasTailoringDraft = Boolean(item.tailoring_draft);
            const canStartTailoring = item.state === "fit_checked" && fit?.decision === "apply";
            const canArmAts = Boolean(item.export_handoff) && ["approved_for_apply", "ats_opened"].includes(item.state);
            const decisionTone = fit?.decision === "apply" ? "good" : fit?.decision === "skip" ? "bad" : "warn";
            const atsTone = item.ats_assist?.status === "submitted_confirmed" || item.ats_assist?.status === "safe_fields_filled"
              ? "good"
              : item.ats_assist?.status === "armed" ? "blue" : "warn";
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
                  {item.tailoring_draft && <span>Draft v{item.tailoring_draft.version}</span>}
                  {item.revision_count > 0 && <span>{item.revision_count} revision{item.revision_count === 1 ? "" : "s"}</span>}
                  {item.export_handoff && <span>Export v{item.export_handoff.version}</span>}
                  {item.ats_assist && <span>ATS assist v{item.ats_assist.version}</span>}
                  {item.recruiter_outreach && <span>Outreach v{item.recruiter_outreach.version}</span>}
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
                {item.tailoring_draft && (
                  <div className="tailoring-draft-strip">
                    <span>Resume {item.tailoring_draft.base_score} to {item.tailoring_draft.tailored_score}</span>
                    <span>{tailoringEngineLabel(item.tailoring_draft)}</span>
                    {item.tailoring_draft.llm_usage?.output_tokens > 0 && <span>{item.tailoring_draft.llm_usage.output_tokens} output tokens</span>}
                    {["approved_for_apply", "ats_opened"].includes(item.state) && <span className="tag good">Approved</span>}
                    {item.export_handoff && <span className={`tag ${item.export_handoff.quality_passed ? "good" : "warn"}`}>{item.export_handoff.quality_passed ? "Files ready" : "Check files"}</span>}
                    {item.ats_assist && <span className={`tag ${atsTone}`}>{atsStatusLabel(item.ats_assist.status)}</span>}
                  </div>
                )}
                {canArmAts && !item.ats_assist && !item.export_handoff.quality_passed && (
                  <label className="ats-quality-gate">
                    <span>Quality review note</span>
                    <textarea
                      value={atsNotes[item.loop_id] || ""}
                      onChange={(event) => setAtsNotes((current) => ({ ...current, [item.loop_id]: event.target.value }))}
                      placeholder="Review the failed checks and record why this export is still appropriate to use."
                      maxLength={1000}
                    />
                  </label>
                )}

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
                      <span>{reviewOpen ? "Close decision" : "Fit decision"}</span>
                    </button>
                  )}
                  {canStartTailoring && !hasTailoringDraft && (
                    <button className="icon-button primary" onClick={() => openTailoringOptions(item)} disabled={Boolean(busy)}>
                      <Sparkles size={16} />
                      <span>{tailoringOpen ? "Close tailoring" : "Tailor resume"}</span>
                    </button>
                  )}
                  {hasTailoringDraft && (
                    <button className="icon-button primary" onClick={() => openTailoringDraft(item)} disabled={Boolean(busy)}>
                      {busy === `draft:${item.loop_id}` ? <Loader2 className="spin" size={16} /> : <FileText size={16} />}
                      <span>{item.export_handoff ? "Open handoff" : item.state === "approved_for_apply" ? "Review & export" : "Review resume"}</span>
                    </button>
                  )}
                  {item.export_handoff?.docx_ready && (
                    <a className="icon-button secondary" href={`${API_BASE}${item.export_handoff.docx_download_path}`} download>
                      <Download size={16} />
                      <span>DOCX</span>
                    </a>
                  )}
                  {item.export_handoff?.pdf_ready && (
                    <a className="icon-button secondary" href={`${API_BASE}${item.export_handoff.pdf_download_path}`} download>
                      <Download size={16} />
                      <span>PDF</span>
                    </a>
                  )}
                  {canArmAts && !item.ats_assist && (
                    <button className="icon-button primary" onClick={() => armAtsAssist(item)} disabled={Boolean(busy) || (!item.export_handoff.quality_passed && String(atsNotes[item.loop_id] || "").trim().length < 3)}>
                      {busy === `ats-arm:${item.loop_id}` ? <Loader2 className="spin" size={16} /> : <ShieldCheck size={16} />}
                      <span>Open ATS assist</span>
                    </button>
                  )}
                  {item.ats_assist && (
                    <button className="icon-button secondary" onClick={() => toggleAtsPanel(item)} disabled={Boolean(busy)}>
                      {busy === `ats-sync:${item.loop_id}` ? <Loader2 className="spin" size={16} /> : <ShieldCheck size={16} />}
                      <span>{atsPanelOpen ? "Close ATS status" : "ATS status"}</span>
                    </button>
                  )}
                  {item.recruiter_outreach && (
                    <a className="icon-button secondary" href={item.recruiter_outreach.linkedin_search_url} target="_blank" rel="noreferrer">
                      <Search size={16} />
                      <span>Find recruiters</span>
                    </a>
                  )}
                  {item.recruiter_outreach && (
                    <button className="icon-button secondary" onClick={() => toggleOutreachPanel(item)} disabled={Boolean(busy)}>
                      <Users size={16} />
                      <span>{outreachPanelOpen ? "Close outreach" : "Outreach note"}</span>
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

                {tailoringOpen && (
                  <div className="tailoring-inline-panel">
                    <TailoringPreferencesEditor value={tailoringPreferences} onChange={setTailoringPreferences} />
                    <button className="icon-button primary" onClick={() => createTailoringDraft(item)} disabled={Boolean(busy)}>
                      {busy === `tailor:${item.loop_id}` ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
                      <span>Create Claude draft</span>
                    </button>
                  </div>
                )}

                {atsPanelOpen && item.ats_assist && (
                  <section className="ats-assist-panel" aria-label="ATS Apply Assist status">
                    <header className="ats-assist-header">
                      <div>
                        <ShieldCheck size={18} />
                        <div>
                          <h4>ATS Apply Assist</h4>
                          <span>{atsStatusLabel(item.ats_assist.status)}</span>
                        </div>
                      </div>
                      <button className="icon-button ghost compact-icon" title="Refresh ATS result" onClick={() => syncAtsAssist(item)} disabled={Boolean(busy)}>
                        {busy === `ats-sync:${item.loop_id}` ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
                      </button>
                    </header>

                    <div className="ats-assist-stats">
                      <div><strong>{item.ats_assist.filled_count}</strong><span>safe filled</span></div>
                      <div><strong>{item.ats_assist.manual_count}</strong><span>manual</span></div>
                      <div><strong>{item.ats_assist.skipped_count}</strong><span>protected</span></div>
                    </div>

                    <p className="ats-resume-file" title={item.ats_assist.preferred_resume_path}>
                      <FileText size={15} />
                      <span>{item.ats_assist.preferred_resume_format.toUpperCase()} resume: {item.ats_assist.preferred_resume_path.split(/[\\/]/).pop()}</span>
                    </p>

                    {(item.ats_assist.review_items || []).length > 0 && (
                      <div className="ats-review-checklist">
                        <h5>Review before submit</h5>
                        {item.ats_assist.review_items.map((review) => (
                          <label key={`${review.field_id}-${review.label}`}>
                            <input type="checkbox" />
                            <span>
                              <strong>{review.label}</strong>
                              <small>{review.sensitive ? "Protected field left blank" : review.reason || "Answer manually"}</small>
                            </span>
                          </label>
                        ))}
                      </div>
                    )}

                    <p className="ats-hard-stop"><ShieldAlert size={15} /> Resume upload, sensitive answers, final review, and submit stay with you.</p>

                    {item.ats_assist.sheets_status_proposal && (
                      <p className="ats-sheet-proposal"><strong>Sheets proposal:</strong> {item.ats_assist.sheets_status_proposal}</p>
                    )}

                    {item.state === "ats_opened" && (
                      <div className="ats-outcome-controls">
                        <label>
                          <span>Outcome note</span>
                          <textarea
                            value={atsNotes[item.loop_id] || ""}
                            onChange={(event) => setAtsNotes((current) => ({ ...current, [item.loop_id]: event.target.value }))}
                            placeholder={item.export_handoff?.quality_passed ? "What happened in the portal?" : "Review the failed export checks before opening the ATS."}
                            maxLength={1000}
                          />
                        </label>
                        <div className="ats-outcome-actions">
                          <button className="icon-button secondary" onClick={() => recordAtsOutcome(item, "technical_issue")} disabled={String(atsNotes[item.loop_id] || "").trim().length < 3 || Boolean(busy)}>
                            <AlertTriangle size={16} />
                            <span>Portal issue</span>
                          </button>
                          <button className="icon-button ghost" onClick={() => armAtsAssist(item)} disabled={Boolean(busy) || (!item.export_handoff?.quality_passed && String(atsNotes[item.loop_id] || "").trim().length < 3)}>
                            <ExternalLink size={16} />
                            <span>Reopen application</span>
                          </button>
                        </div>
                        <label className="ats-submit-confirmation">
                          <input
                            type="checkbox"
                            checked={Boolean(submissionConfirmations[item.loop_id])}
                            onChange={(event) => setSubmissionConfirmations((current) => ({ ...current, [item.loop_id]: event.target.checked }))}
                          />
                          <span>I manually submitted this application and saw the portal confirmation.</span>
                        </label>
                        <button className="icon-button primary ats-submit-button" onClick={() => recordAtsOutcome(item, "submitted_confirmed")} disabled={!submissionConfirmations[item.loop_id] || String(atsNotes[item.loop_id] || "").trim().length < 3 || Boolean(busy)}>
                          {busy === `ats-outcome:${item.loop_id}` ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
                          <span>Confirm manual submission</span>
                        </button>
                      </div>
                    )}
                  </section>
                )}

                {outreachPanelOpen && item.recruiter_outreach && (
                  <section className="recruiter-outreach-panel" aria-label="Recruiter outreach review">
                    <header className="recruiter-outreach-header">
                      <div>
                        <Users size={18} />
                        <div>
                          <h4>Connection request</h4>
                          <span>
                            {item.recruiter_outreach.engine === "claude"
                              ? item.recruiter_outreach.model || "Claude"
                              : "Deterministic fallback"}
                          </span>
                        </div>
                      </div>
                      <span className={`tag ${item.recruiter_outreach.status === "sent" ? "good" : "blue"}`}>
                        {item.recruiter_outreach.status}
                      </span>
                    </header>

                    <label>
                      <span>Recruiter name</span>
                      <input
                        value={outreachDraft.recruiter_name || ""}
                        onChange={(event) => setOutreachDraft(item.loop_id, "recruiter_name", event.target.value)}
                        placeholder="Optional after LinkedIn search"
                        disabled={item.state === "outreach_done"}
                        maxLength={200}
                      />
                    </label>
                    <label>
                      <span>Connection note</span>
                      <textarea
                        value={outreachDraft.connection_note || ""}
                        onChange={(event) => setOutreachDraft(item.loop_id, "connection_note", event.target.value)}
                        disabled={item.state === "outreach_done"}
                        maxLength={300}
                      />
                      <small>{String(outreachDraft.connection_note || "").length} / 300</small>
                    </label>

                    <div className="recruiter-outreach-actions">
                      <button className="icon-button secondary" onClick={() => copyRecruiterNote(item)} disabled={!String(outreachDraft.connection_note || "").trim()}>
                        <Copy size={16} />
                        <span>Copy</span>
                      </button>
                      {item.state === "recruiter_note_ready" && (
                        <button className="icon-button secondary" onClick={() => saveRecruiterOutreach(item)} disabled={String(outreachDraft.connection_note || "").trim().length < 20 || Boolean(busy)}>
                          {busy === `outreach-save:${item.loop_id}` ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
                          <span>Save note</span>
                        </button>
                      )}
                      {item.state === "recruiter_note_ready" && (
                        <button className="icon-button ghost compact-icon" title="Regenerate this note; may use one Claude call" onClick={() => prepareRecruiterOutreach([item.loop_id], true)} disabled={Boolean(busy)}>
                          {busy === `outreach-regenerate:${item.loop_id}` ? <Loader2 className="spin" size={16} /> : <RotateCcw size={16} />}
                        </button>
                      )}
                    </div>

                    {item.state === "recruiter_note_ready" && (
                      <div className="recruiter-send-confirmation">
                        <label>
                          <span>Outcome note</span>
                          <textarea
                            value={outreachOutcomeNotes[item.loop_id] || ""}
                            onChange={(event) => setOutreachOutcomeNotes((current) => ({ ...current, [item.loop_id]: event.target.value }))}
                            placeholder="Connection request sent to recruiter name"
                            maxLength={1000}
                          />
                        </label>
                        <label className="ats-submit-confirmation">
                          <input
                            type="checkbox"
                            checked={Boolean(outreachConfirmations[item.loop_id])}
                            onChange={(event) => setOutreachConfirmations((current) => ({ ...current, [item.loop_id]: event.target.checked }))}
                          />
                          <span>I manually sent this connection request on LinkedIn.</span>
                        </label>
                        <button className="icon-button primary" onClick={() => markRecruiterOutreachSent(item)} disabled={!outreachConfirmations[item.loop_id] || String(outreachOutcomeNotes[item.loop_id] || "").trim().length < 3 || Boolean(busy)}>
                          {busy === `outreach-sent:${item.loop_id}` ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
                          <span>Mark sent</span>
                        </button>
                      </div>
                    )}

                    {item.state === "outreach_done" && (
                      <p className="recruiter-sent-note">
                        Sent {formatDateTime(item.recruiter_outreach.sent_at)}. {item.recruiter_outreach.sent_note}
                      </p>
                    )}
                  </section>
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
      {draftReview && reviewSelection && (
        <TailoringReviewModal
          result={draftReview}
          selection={reviewSelection}
          onSelectionChange={setReviewSelection}
          preferences={tailoringPreferences}
          onPreferencesChange={setTailoringPreferences}
          revisionReason={revisionReason}
          onRevisionReasonChange={setRevisionReason}
          approvalNote={approvalNote}
          onApprovalNoteChange={setApprovalNote}
          busy={busy}
          onRefresh={refreshTailoringPreview}
          onApprove={approveTailoringDraft}
          exportRoot={exportRoot}
          onExportRootChange={setExportRoot}
          renderExportPdf={renderExportPdf}
          onRenderExportPdfChange={setRenderExportPdf}
          onExport={exportApprovedTailoring}
          onOpenAts={() => armAtsAssist(draftReview.loop_item)}
          atsNote={atsNotes[draftReview.loop_item.loop_id] || ""}
          onAtsNoteChange={(value) => setAtsNotes((current) => ({ ...current, [draftReview.loop_item.loop_id]: value }))}
          onRegenerate={() => createTailoringDraft(draftReview.loop_item)}
          onClose={() => setDraftReview(null)}
        />
      )}
    </>
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

function TailoringPreferencesEditor({ value, onChange }) {
  function update(field, nextValue) {
    onChange({ ...value, [field]: nextValue });
  }

  function toggleEmphasis(key, checked) {
    const current = new Set(value.emphasis || []);
    if (checked) current.add(key);
    else current.delete(key);
    update("emphasis", TAILORING_EMPHASIS.map(([candidate]) => candidate).filter((candidate) => current.has(candidate)));
  }

  function updateCount(field, rawValue) {
    const parsed = Number.parseInt(rawValue, 10);
    const count = Number.isFinite(parsed) ? Math.max(0, Math.min(50, parsed)) : 0;
    update("bullet_counts", { ...value.bullet_counts, [field]: count });
  }

  return (
    <div className="tailoring-preferences">
      <div className="tailoring-select-grid">
        <label>
          <span>Style</span>
          <select value={value.preset} onChange={(event) => update("preset", event.target.value)}>
            <option value="balanced">Balanced</option>
            <option value="technical_depth">Technical depth</option>
            <option value="business_impact">Business impact</option>
            <option value="projects_first">Projects first</option>
            <option value="experience_first">Experience first</option>
            <option value="minimal_edits">Minimal edits</option>
          </select>
        </label>
        <label>
          <span>Rewrite strength</span>
          <select value={value.rewrite_intensity} onChange={(event) => update("rewrite_intensity", event.target.value)}>
            <option value="light">Light</option>
            <option value="balanced">Balanced</option>
            <option value="strong">Strong alignment</option>
          </select>
        </label>
      </div>

      <fieldset className="tailoring-emphasis">
        <legend>Emphasize</legend>
        {TAILORING_EMPHASIS.map(([key, label]) => (
          <label key={key}>
            <input
              type="checkbox"
              checked={(value.emphasis || []).includes(key)}
              onChange={(event) => toggleEmphasis(key, event.target.checked)}
            />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>

      <div className="tailoring-count-grid">
        <label>
          <span>Per experience role</span>
          <input type="number" min="0" max="50" value={value.bullet_counts.experience_per_role} onChange={(event) => updateCount("experience_per_role", event.target.value)} />
        </label>
        <label>
          <span>Per project</span>
          <input type="number" min="0" max="50" value={value.bullet_counts.projects_per_project} onChange={(event) => updateCount("projects_per_project", event.target.value)} />
        </label>
        <label>
          <span>Per paper</span>
          <input type="number" min="0" max="50" value={value.bullet_counts.research_per_paper} onChange={(event) => updateCount("research_per_paper", event.target.value)} />
        </label>
      </div>

      <div className="tailoring-toggle-row">
        <Toggle label="Recruiter note" checked={value.include_connection_note} onChange={(checked) => update("include_connection_note", checked)} />
        <Toggle label="Cover letter" checked={value.include_cover_letter} onChange={(checked) => update("include_cover_letter", checked)} />
      </div>

      <label className="tailoring-direction">
        <span>Additional direction</span>
        <textarea
          value={value.custom_instructions}
          onChange={(event) => update("custom_instructions", event.target.value)}
          placeholder="Prioritize the strongest honest evidence for this role."
          maxLength={600}
        />
      </label>
    </div>
  );
}

function TailoringReviewModal({
  result,
  selection,
  onSelectionChange,
  preferences,
  onPreferencesChange,
  revisionReason,
  onRevisionReasonChange,
  approvalNote,
  onApprovalNoteChange,
  busy,
  onRefresh,
  onApprove,
  exportRoot,
  onExportRootChange,
  renderExportPdf,
  onRenderExportPdfChange,
  onExport,
  onOpenAts,
  atsNote,
  onAtsNoteChange,
  onRegenerate,
  onClose
}) {
  const { draft, loop_item: loopItem } = result;
  const approved = Boolean(
    loopItem.tailoring_approval
    && loopItem.tailoring_approval.draft_id === loopItem.tailoring_draft?.draft_id
  );
  const handoff = loopItem.export_handoff;
  const usage = draft.llm_usage || {};

  React.useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  function updateSelection(field, value) {
    onSelectionChange({ ...selection, [field]: value });
  }

  function updateBullet(index, changes) {
    updateSelection("bullets", selection.bullets.map((bullet, bulletIndex) => bulletIndex === index ? { ...bullet, ...changes } : bullet));
  }

  function toggleSelected(field, id, checked, max) {
    const current = new Set(selection[field] || []);
    if (checked && current.size < max) current.add(id);
    if (!checked) current.delete(id);
    updateSelection(field, [...current]);
  }

  return (
    <div className="tailoring-modal-backdrop" role="presentation">
      <section className="tailoring-modal" role="dialog" aria-modal="true" aria-label={`${draft.role} tailored resume review`}>
        <header className="tailoring-modal-header">
          <div>
            <span>{draft.company}</span>
            <h2>{draft.role}</h2>
          </div>
          <div className="tailoring-modal-status">
            <span className={`tag ${approved ? "good" : "blue"}`}>{approved ? "Approved" : `Draft v${loopItem.tailoring_draft?.version || 1}`}</span>
            <span>{draft.base_score} to {draft.tailored_score}</span>
            <button className="icon-button ghost compact-icon" title="Close review" onClick={onClose}>
              <XCircle size={20} />
            </button>
          </div>
        </header>

        <div className="tailoring-modal-body">
          <div className="resume-preview-stage">
            <iframe title={`${draft.role} resume preview`} srcDoc={draft.resume_preview_html} sandbox="" />
          </div>

          <aside className="tailoring-review-sidebar">
            <section className="tailoring-review-meta">
              <div><span>Engine</span><strong>{tailoringEngineLabel(draft)}</strong></div>
              <div><span>Input</span><strong>{Number(usage.input_tokens || 0).toLocaleString()}</strong></div>
              <div><span>Output</span><strong>{Number(usage.output_tokens || 0).toLocaleString()}</strong></div>
              <div><span>Cache read</span><strong>{Number(usage.cache_read_input_tokens || 0).toLocaleString()}</strong></div>
            </section>

            <section className="tailoring-review-section">
              <div className="tailoring-review-heading">
                <h3>Summary</h3>
                <Toggle label="Use" checked={selection.summary_accepted} onChange={(checked) => updateSelection("summary_accepted", checked)} disabled={approved} />
              </div>
              <textarea value={selection.summary_text} onChange={(event) => updateSelection("summary_text", event.target.value)} maxLength={1400} readOnly={approved} />
            </section>

            {(draft.bullets || []).length > 0 && (
              <section className="tailoring-review-section">
                <h3>Grounded rewrites</h3>
                <div className="tailoring-bullet-review-list">
                  {draft.bullets.map((bullet, index) => (
                    <label className="tailoring-bullet-review" key={bullet.bullet_id}>
                      <span className="tailoring-bullet-label">
                        <input type="checkbox" checked={selection.bullets[index]?.accepted ?? true} onChange={(event) => updateBullet(index, { accepted: event.target.checked })} disabled={approved} />
                        <strong>{bullet.item_label || bullet.section}</strong>
                        <em>{bullet.section}</em>
                      </span>
                      <textarea value={selection.bullets[index]?.text || ""} onChange={(event) => updateBullet(index, { text: event.target.value })} maxLength={700} readOnly={approved} />
                    </label>
                  ))}
                </div>
              </section>
            )}

            {(draft.projects || []).length > 0 && (
              <section className="tailoring-review-section">
                <h3>Projects</h3>
                <div className="tailoring-choice-list">
                  {draft.projects.map((project) => (
                    <label key={project.project_id}>
                      <input type="checkbox" checked={(selection.project_ids || []).includes(project.project_id)} onChange={(event) => toggleSelected("project_ids", project.project_id, event.target.checked, 3)} disabled={approved} />
                      <span>{project.name}</span>
                    </label>
                  ))}
                </div>
              </section>
            )}

            {(draft.publications || []).length > 0 && (
              <section className="tailoring-review-section">
                <h3>Research papers</h3>
                <div className="tailoring-choice-list">
                  {draft.publications.map((paper) => (
                    <label key={paper.publication_id}>
                      <input type="checkbox" checked={(selection.publication_ids || []).includes(paper.publication_id)} onChange={(event) => toggleSelected("publication_ids", paper.publication_id, event.target.checked, 2)} disabled={approved} />
                      <span>{paper.title}</span>
                    </label>
                  ))}
                </div>
              </section>
            )}

            <section className="tailoring-review-section">
              <h3>Bullets per subsection</h3>
              <div className="tailoring-count-grid">
                <label><span>Experience</span><input type="number" min="0" max="50" value={selection.bullet_counts.experience_per_role} onChange={(event) => updateSelection("bullet_counts", { ...selection.bullet_counts, experience_per_role: Number(event.target.value) })} disabled={approved} /></label>
                <label><span>Projects</span><input type="number" min="0" max="50" value={selection.bullet_counts.projects_per_project} onChange={(event) => updateSelection("bullet_counts", { ...selection.bullet_counts, projects_per_project: Number(event.target.value) })} disabled={approved} /></label>
                <label><span>Research</span><input type="number" min="0" max="50" value={selection.bullet_counts.research_per_paper} onChange={(event) => updateSelection("bullet_counts", { ...selection.bullet_counts, research_per_paper: Number(event.target.value) })} disabled={approved} /></label>
              </div>
            </section>

            {draft.connection_note && (
              <section className="tailoring-review-section">
                <h3>Recruiter note</h3>
                <textarea value={selection.connection_note} onChange={(event) => updateSelection("connection_note", event.target.value)} maxLength={299} readOnly={approved} />
              </section>
            )}

            {draft.cover_letter_text && (
              <section className="tailoring-review-section">
                <div className="tailoring-review-heading">
                  <h3>Cover letter</h3>
                  <Toggle label="Use" checked={selection.cover_letter_accepted} onChange={(checked) => updateSelection("cover_letter_accepted", checked)} disabled={approved} />
                </div>
                <textarea className="cover-letter-editor" value={selection.cover_letter_text} onChange={(event) => updateSelection("cover_letter_text", event.target.value)} maxLength={4000} readOnly={approved} />
              </section>
            )}

            <div className="tailoring-review-actions">
              <button className="icon-button secondary" onClick={onRefresh} disabled={approved || Boolean(busy)}>
                {String(busy).startsWith("preview:") ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
                <span>Refresh preview</span>
              </button>
              {!approved && (
                <>
                  <label className="tailoring-approval-note">
                    <span>Approval note</span>
                    <textarea value={approvalNote} onChange={(event) => onApprovalNoteChange(event.target.value)} placeholder="Record why this draft is ready." maxLength={1000} />
                  </label>
                  <button className="icon-button primary" onClick={onApprove} disabled={approvalNote.trim().length < 3 || Boolean(busy)}>
                    {String(busy).startsWith("approve:") ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
                    <span>Approve draft</span>
                  </button>
                </>
              )}
            </div>

            {approved && (
              <section className="tailoring-export-section">
                <div className="tailoring-review-heading">
                  <div>
                    <span>Approved handoff</span>
                    <h3>Resume files</h3>
                  </div>
                  {handoff && <span className={`tag ${handoff.quality_passed ? "good" : "warn"}`}>{handoff.quality_passed ? "Quality passed" : "Review checks"}</span>}
                </div>
                <label className="tailoring-output-root">
                  <span>Output root</span>
                  <input
                    value={exportRoot}
                    onChange={(event) => onExportRootChange(event.target.value)}
                    placeholder="Default resume folder"
                    maxLength={4000}
                  />
                </label>
                <div className="tailoring-export-command">
                  <Toggle label="Render PDF" checked={renderExportPdf} onChange={onRenderExportPdfChange} />
                  <button className="icon-button primary" onClick={onExport} disabled={Boolean(busy)}>
                    {String(busy).startsWith("export:") ? <Loader2 className="spin" size={16} /> : <FolderOpen size={16} />}
                    <span>{handoff ? "Regenerate files" : renderExportPdf ? "Generate DOCX + PDF" : "Generate DOCX"}</span>
                  </button>
                </div>

                {handoff && (
                  <div className="tailoring-export-result">
                    {!handoff.quality_passed && (
                      <label className="ats-quality-gate">
                        <span>Quality review note</span>
                        <textarea value={atsNote} onChange={(event) => onAtsNoteChange(event.target.value)} placeholder="Review the failed checks and record why this export is still appropriate to use." maxLength={1000} />
                      </label>
                    )}
                    <div className="tailoring-download-actions">
                      {handoff.docx_ready && (
                        <a className="icon-button secondary" href={`${API_BASE}${handoff.docx_download_path}`} download>
                          <Download size={16} />
                          <span>Download DOCX</span>
                        </a>
                      )}
                      {handoff.pdf_ready && (
                        <a className="icon-button secondary" href={`${API_BASE}${handoff.pdf_download_path}`} download>
                          <Download size={16} />
                          <span>Download PDF</span>
                        </a>
                      )}
                      {loopItem.job_url && (
                        <button className="icon-button ghost" onClick={onOpenAts} disabled={Boolean(busy) || (!handoff.quality_passed && atsNote.trim().length < 3)}>
                          <ShieldCheck size={16} />
                          <span>{loopItem.ats_assist ? "Reopen ATS assist" : "Open with ATS assist"}</span>
                        </button>
                      )}
                    </div>
                    <div className="tailoring-export-path" title={handoff.packet_folder_path || handoff.prepared_resume_docx_path}>
                      <FolderOpen size={15} />
                      <span>{handoff.packet_folder_path || handoff.prepared_resume_docx_path}</span>
                    </div>
                    {handoff.pdf_error && <p className="tailoring-export-error">{handoff.pdf_error}</p>}
                    {(handoff.quality_checks || []).some((check) => check.passed === false) && (
                      <details className="tailoring-quality-checks">
                        <summary>Quality checks</summary>
                        {(handoff.quality_checks || []).map((check, index) => (
                          <p key={`${check.name || check.check || "check"}-${index}`} className={check.passed === false ? "failed" : "passed"}>
                            {check.name || check.check || `Check ${index + 1}`}
                          </p>
                        ))}
                      </details>
                    )}
                  </div>
                )}
              </section>
            )}

            <details className="tailoring-revision-panel">
              <summary>Revise with Claude</summary>
              <TailoringPreferencesEditor value={preferences} onChange={onPreferencesChange} />
              <label>
                <span>Revision reason</span>
                <textarea value={revisionReason} onChange={(event) => onRevisionReasonChange(event.target.value)} placeholder="What should be stronger, shorter, or differently emphasized?" maxLength={1000} />
              </label>
              <button className="icon-button primary" onClick={onRegenerate} disabled={revisionReason.trim().length < 3 || Boolean(busy)}>
                {String(busy).startsWith("tailor:") ? <Loader2 className="spin" size={16} /> : <RotateCcw size={16} />}
                <span>Regenerate draft</span>
              </button>
            </details>
          </aside>
        </div>
      </section>
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
