import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

type WorkflowStatus =
  | "INGESTED"
  | "CANDIDATE"
  | "TOPIC_APPROVED"
  | "VERIFIED"
  | "DRAFTED"
  | "ASSETS_READY"
  | "QA_PASSED"
  | "EDITORIAL_APPROVED"
  | "READY_TO_PUBLISH"
  | "PUBLISH_APPROVED"
  | "PUBLISHED"
  | "DISTRIBUTED"
  | "MEASURED"
  | "REJECTED"
  | "BLOCKED"
  | "FAILED_RETRYABLE"
  | "FAILED_TERMINAL";

type RunSummary = {
  id: string;
  vertical_key: string;
  status: WorkflowStatus;
  risk_class: string;
  confidence_class: string;
  state_version: number;
  topic_title: string | null;
  topic_decision: string | null;
  topic_urgency: string | null;
  topic_composite_score?: number | null;
  topic_proposed_angle?: string | null;
  topic_proposed_format?: string | null;
  topic_sources?: string[];
  pending_gate: string | null;
  created_at: string;
  updated_at: string;
};

type GateArtifact = {
  artifact_type: string;
  artifact_id: string;
  artifact_version: number;
};

type Claim = {
  id: string;
  statement: string;
  material: boolean;
  confidence_class: string;
  risk_class: string;
  support_status: string;
  stale: boolean;
  contested: boolean;
};

type Evidence = {
  id: string;
  url: string;
  excerpt: string | null;
  tier: string;
  source_role: string;
  stale: boolean;
  observed_at: string;
};

type Draft = {
  id: string;
  version: number;
  locale: string;
  title: string;
  deck: string | null;
  body: string;
  unsupported_factual_claims: string[];
};

type Asset = {
  id: string;
  version: number;
  slot: string;
  kind: string;
  uri: string | null;
  filename: string | null;
  rights_status: string;
  alt_text: string | null;
  caption: string | null;
};

type GateDecision = {
  id: string;
  gate: string;
  outcome: string;
  artifact_type: string;
  artifact_id: string;
  artifact_version: number;
  actor_id: string;
  reason: string | null;
  decided_at: string;
};

type TimelineEvent = {
  id: string;
  action_key: string;
  action_type: string;
  actor_kind: string;
  actor_id: string;
  from_status: string;
  to_status: string;
  from_state_version: number;
  to_state_version: number;
  created_at: string;
};

type Usage = {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  total_cost_usd: string;
  average_latency_ms: number | null;
};

type Publication = {
  id: string;
  provider: string;
  target: string;
  status: string;
  external_url: string | null;
  scheduled_at: string | null;
  published_at: string | null;
};

type Distribution = {
  id: string;
  provider: string;
  channel: string;
  status: string;
  external_url: string | null;
  created_at: string;
  updated_at: string;
};

type RunDetail = {
  run: RunSummary;
  gate_artifact: GateArtifact | null;
  claims: Claim[];
  evidence: Evidence[];
  draft: Draft | null;
  assets: Asset[];
  gates: GateDecision[];
  timeline: TimelineEvent[];
  usage: Usage;
  publication: Publication | null;
  distributions: Distribution[];
  recovery_action: "RETRY" | "RESUME" | null;
};

type QueueView = "awaiting" | "all" | "watch" | "blocked" | "retryable";

type Filters = {
  vertical: string;
  status: string;
  risk: string;
  topicDecision: string;
  updatedAfter: string;
  updatedBefore: string;
};

const deploymentLabel = import.meta.env.VITE_DEPLOYMENT_LABEL ?? "local";
const initialFilters: Filters = {
  vertical: "",
  status: "",
  risk: "",
  topicDecision: "",
  updatedAfter: "",
  updatedBefore: "",
};

const statusOptions: WorkflowStatus[] = [
  "INGESTED",
  "CANDIDATE",
  "TOPIC_APPROVED",
  "VERIFIED",
  "DRAFTED",
  "ASSETS_READY",
  "QA_PASSED",
  "EDITORIAL_APPROVED",
  "READY_TO_PUBLISH",
  "PUBLISH_APPROVED",
  "PUBLISHED",
  "DISTRIBUTED",
  "MEASURED",
  "BLOCKED",
  "FAILED_RETRYABLE",
  "FAILED_TERMINAL",
  "REJECTED",
];

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function shortId(value: string) {
  return value.slice(0, 8);
}

function humanStatus(value: string) {
  return value.replaceAll("_", " ").toLowerCase().replace(/^./, (letter) => letter.toUpperCase());
}

function safeSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function statusTone(status: string) {
  if (["PUBLISHED", "DISTRIBUTED", "MEASURED", "TOPIC_APPROVED", "EDITORIAL_APPROVED", "PUBLISH_APPROVED"].includes(status)) {
    return "positive";
  }
  if (["FAILED_TERMINAL", "REJECTED"].includes(status)) return "danger";
  if (["FAILED_RETRYABLE", "BLOCKED"].includes(status)) return "warning";
  return "neutral";
}

async function readJson<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new Error(
      response.ok
        ? "The server returned an unexpected response."
        : `Request failed with HTTP ${response.status}.`,
    );
  }

  const payload = (await response.json()) as T | { detail?: string };
  if (!response.ok) {
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : `Request failed with HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}

function App() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [operatorId, setOperatorId] = useState(deploymentLabel === "local" ? "operator" : "");
  const [identityStatus, setIdentityStatus] = useState<"loading" | "verified" | "unavailable">(
    deploymentLabel === "local" ? "verified" : "loading",
  );
  const [reason, setReason] = useState("");
  const [search, setSearch] = useState("");
  const [queueView, setQueueView] = useState<QueueView>("awaiting");
  const [reviewConfirmed, setReviewConfirmed] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const detailRequestId = useRef(0);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Cloudflare Access authenticates the entire Worker before this UI loads.
  // The API uses the Access assertion at the edge; no token belongs in the browser.


  const loadRuns = useCallback(async (activeFilters: Filters) => {
    setLoadingRuns(true);
    setError(null);
    const params = new URLSearchParams();
    if (activeFilters.vertical) params.set("vertical", activeFilters.vertical);
    if (activeFilters.status) params.set("status", activeFilters.status);
    if (activeFilters.risk) params.set("risk", activeFilters.risk);
    if (activeFilters.topicDecision) {
      params.set("topic_decision", activeFilters.topicDecision);
    }
    if (activeFilters.updatedAfter) {
      params.set("updated_after", new Date(`${activeFilters.updatedAfter}T00:00:00`).toISOString());
    }
    if (activeFilters.updatedBefore) {
      params.set("updated_before", new Date(`${activeFilters.updatedBefore}T23:59:59`).toISOString());
    }
    try {
      const response = await fetch(`/api/operator/runs?${params.toString()}`);
      const payload = await readJson<RunSummary[]>(response);
      setRuns(payload);

    } catch (requestError) {
      // Keep the last good data; a failed refresh must not imply zero runs.
      setError(requestError instanceof Error ? requestError.message : "Unable to load runs.");
    } finally {
      setLoadingRuns(false);
    }
  }, []);

  const loadDetail = useCallback(async (runId: string) => {
    const requestId = ++detailRequestId.current;
    setLoadingDetail(true);
    setError(null);
    try {
      const response = await fetch(`/api/operator/runs/${runId}`);
      const payload = await readJson<RunDetail>(response);
      if (requestId === detailRequestId.current) setDetail(payload);
    } catch (requestError) {
      if (requestId === detailRequestId.current) {
        setDetail(null);
        setError(requestError instanceof Error ? requestError.message : "Unable to load run.");
      }
    } finally {
      if (requestId === detailRequestId.current) setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (deploymentLabel === "local") return;
    let active = true;
    void (async () => {
      try {
        const response = await fetch("/api/operator/session");
        const session = await readJson<{ actor_id: string | null }>(response);
        if (active) {
          setOperatorId(session.actor_id ?? "");
          setIdentityStatus(session.actor_id ? "verified" : "unavailable");
        }
      } catch {
        if (active) {
          setOperatorId("");
          setIdentityStatus("unavailable");
        }
      }
    })();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    void loadRuns(initialFilters);
  }, [loadRuns]);

  useEffect(() => {
    setPendingAction(null);
    setReviewConfirmed(false);
    setReason("");
    if (selectedId) {
      setDetail(null);
      void loadDetail(selectedId);
    } else {
      detailRequestId.current += 1;
      setDetail(null);
      setLoadingDetail(false);
    }
  }, [selectedId, loadDetail]);

  const queueCounts = useMemo(() => {
    return {
      waiting: runs.filter((run) => Boolean(run.pending_gate)).length,
      blocked: runs.filter((run) => run.status === "BLOCKED").length,
      retryable: runs.filter((run) => run.status === "FAILED_RETRYABLE").length,
      watch: runs.filter((run) => run.topic_decision === "WATCH").length,
    };
  }, [runs]);

  const visibleRuns = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return runs.filter((run) => {
      if (queueView === "awaiting" && !run.pending_gate) return false;
      if (queueView === "watch" && run.topic_decision !== "WATCH") return false;
      if (queueView === "blocked" && run.status !== "BLOCKED") return false;
      if (queueView === "retryable" && run.status !== "FAILED_RETRYABLE") return false;
      return !query || [
        run.topic_title, run.vertical_key, run.topic_proposed_angle, run.status, run.id,
      ].some((value) => value?.toLocaleLowerCase().includes(query));
    }).sort((a, b) => Number(Boolean(b.pending_gate)) - Number(Boolean(a.pending_gate)) ||
      Date.parse(b.updated_at) - Date.parse(a.updated_at));
  }, [runs, queueView, search]);

  useEffect(() => {
    if (!visibleRuns.some((run) => run.id === selectedId)) {
      setSelectedId(visibleRuns[0]?.id ?? null);
    }
  }, [visibleRuns, selectedId]);

  const decisionRequiresNote = ["REJECTED", "REVISION_REQUESTED", "RECOVER"].includes(pendingAction ?? "");
  const canSubmitAction = reviewConfirmed && Boolean(operatorId.trim()) &&
    (!decisionRequiresNote || reason.trim().length >= 10);

  async function submitGate(outcome: string) {
    if (!detail || !operatorId.trim()) return;
    setActionBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/operator/runs/${detail.run.id}/gate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            outcome,
            actor_id: operatorId.trim(),
            reason: reason.trim() || null,
            details: {},
          }),
        },
      );
      const payload = await readJson<RunDetail>(response);
      setDetail(payload);
      setReason("");
      setReviewConfirmed(false);
      setPendingAction(null);
      setActionSuccess(`Decision recorded: ${humanStatus(outcome)}.`);
      await loadRuns(filters);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Gate action failed.");
    } finally {
      setActionBusy(false);
    }
  }

  async function recoverRun() {
    if (!detail?.recovery_action || !operatorId.trim()) return;
    setActionBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/operator/runs/${detail.run.id}/recover`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            actor_id: operatorId.trim(),
            reason: reason.trim() || null,
          }),
        },
      );
      const payload = await readJson<RunDetail>(response);
      setDetail(payload);
      setReason("");
      setReviewConfirmed(false);
      setPendingAction(null);
      setActionSuccess("Recovery action recorded.");
      await loadRuns(filters);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Recovery failed.");
    } finally {
      setActionBusy(false);
    }
  }

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    void loadRuns(filters);
  }

  function chooseQueue(view: QueueView) {
    setQueueView(view);
    setPendingAction(null);
  }

  function resetFilters() {
    setFilters(initialFilters);
    setQueueView("awaiting");
    setSearch("");
    void loadRuns(initialFilters);
  }

  const gateActions =
    detail?.run.pending_gate === "A"
      ? ["APPROVED", "WATCH", "REJECTED"]
      : detail?.run.pending_gate
        ? ["APPROVED", "REVISION_REQUESTED", "REJECTED"]
        : [];

  return (
    <div className="operator-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">T</div>
          <div>
            <strong>Editorial OS</strong>
            <span>Operator console</span>
          </div>
        </div>

        <nav className="queue-nav" aria-label="Editorial queues">
          {([
            ["awaiting", "Needs review", queueCounts.waiting],
            ["all", "All runs", runs.length],
            ["watch", "Monitoring", queueCounts.watch],
            ["blocked", "Blocked", queueCounts.blocked],
            ["retryable", "Retryable", queueCounts.retryable],
          ] as const).map(([view, label, count]) => (
            <button key={view} type="button" className={queueView === view ? "active" : ""}
              aria-pressed={queueView === view} onClick={() => chooseQueue(view)}>
              <span>{label}</span><b>{count}</b>
            </button>
          ))}
        </nav>

        <div className="operator-identity">
          <div className="operator-auth-note">
            <strong>Cloudflare Access</strong>
            <small>Session secured by email verification.</small>
            <a href="/cdn-cgi/access/logout">Sign out</a>
          </div>

          <label htmlFor={deploymentLabel === "local" ? "operator-id" : undefined}>Operator identity</label>
          {deploymentLabel === "local" ? (
            <input id="operator-id" value={operatorId}
              onChange={(event) => setOperatorId(event.target.value)} placeholder="operator" />
          ) : (
            <div className="verified-identity" role="status">
              {identityStatus === "loading" ? "Verifying signed-in identity…" :
                identityStatus === "verified" ? operatorId : "Identity unavailable — decisions disabled"}
            </div>
          )}
          <small>Recorded on every gate and recovery action.</small>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Trigenys Editorial OS</p>
            <h1>Editorial control room</h1>
            <p className="workspace-subtitle">Review incoming stories, examine context and make informed decisions.</p>
            <span className="deployment-badge">{deploymentLabel}</span>
          </div>
          <button className="ghost-button refresh-button" type="button"
            disabled={loadingRuns} onClick={() => void loadRuns(filters)}>
            {loadingRuns ? "Refreshing…" : "↻ Refresh"}
          </button>
        </header>

        <section className="summary-grid" aria-label="Queue summary">
          {([
            ["awaiting", "Needs your review", queueCounts.waiting, "Decisions pending", "attention"],
            ["watch", "Monitoring", queueCounts.watch, "Topics being watched", ""],
            ["blocked", "Blocked", queueCounts.blocked, queueCounts.blocked ? "Needs intervention" : "No blockers", queueCounts.blocked ? "risk" : ""],
            ["all", "Total runs", runs.length, "In current API results", ""],
          ] as const).map(([view, label, count, description, tone]) => (
            <button key={view} type="button"
              className={`kpi-card ${tone} ${queueView === view ? "selected" : ""}`}
              aria-pressed={queueView === view} onClick={() => chooseQueue(view)}>
              <span className="kpi-label">{label}</span>
              <strong>{loadingRuns && runs.length === 0 ? "—" : count}</strong>
              <span className="kpi-description">{description}</span>
            </button>
          ))}
        </section>

        <div className="filter-surface">
          <div className="search-toolbar">
            <label htmlFor="run-search">Search stories</label>
            <input id="run-search" className="search-input" type="search"
              placeholder="Title, vertical, angle or workflow ID…"
              value={search} onChange={(event) => setSearch(event.target.value)} />
            <span className="result-count" aria-live="polite">{visibleRuns.length} of {runs.length} shown</span>
          </div>
          <details className="advanced-filters">
            <summary>Advanced filters <span>Vertical, status, risk and dates</span></summary>
            <form className="filters" onSubmit={applyFilters}>
              <label>Vertical
                <input value={filters.vertical}
                  onChange={(event) => setFilters({ ...filters, vertical: event.target.value })}
                  placeholder="All verticals" />
              </label>
              <label>Status
                <select value={filters.status}
                  onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
                  <option value="">All statuses</option>
                  {statusOptions.map((status) => <option key={status} value={status}>{humanStatus(status)}</option>)}
                </select>
              </label>
              <label>Risk
                <select value={filters.risk}
                  onChange={(event) => setFilters({ ...filters, risk: event.target.value })}>
                  <option value="">All risks</option>
                  {["R0", "R1", "R2", "R3"].map((risk) => <option key={risk} value={risk}>{risk}</option>)}
                </select>
              </label>
              <label>Topic decision
                <select value={filters.topicDecision}
                  onChange={(event) => setFilters({ ...filters, topicDecision: event.target.value })}>
                  <option value="">All decisions</option>
                  <option value="PROPOSE">Propose</option><option value="WATCH">Watch</option>
                  <option value="IGNORE">Ignore</option>
                </select>
              </label>
              <label>Updated after
                <input type="date" value={filters.updatedAfter}
                  onChange={(event) => setFilters({ ...filters, updatedAfter: event.target.value })} />
              </label>
              <label>Updated before
                <input type="date" value={filters.updatedBefore}
                  onChange={(event) => setFilters({ ...filters, updatedBefore: event.target.value })} />
              </label>
              <div className="filter-actions">
                <button className="primary-button" type="submit">Apply filters</button>
                <button className="text-button" type="button" onClick={resetFilters}>Reset all</button>
              </div>
            </form>
          </details>
        </div>

        {actionSuccess && <div className="success-banner" role="status">
          {actionSuccess}
          <button type="button" className="text-button" onClick={() => setActionSuccess(null)}>Dismiss</button>
        </div>}

        {error && <div className="error-banner" role="alert">{error}</div>}

        <div className="console-grid">
          <section className="run-list-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Editorial queue</p>
                <h2>{queueView === "awaiting" ? "Awaiting a decision" : queueView === "all" ? "All workflow runs" : humanStatus(queueView)}</h2>
                <p className="queue-helper">Actionable stories appear first.</p>
              </div>
              {loadingRuns && <span className="loading-dot" role="status">Loading…</span>}
            </div>

            <div className="run-list">
              {!loadingRuns && !error && visibleRuns.length === 0 && (
                <div className="empty-state">
                  No stories match this view. Try another queue or reset your filters.
                </div>
              )}
              {visibleRuns.map((run) => (
                <button
                  type="button"
                  className={`run-card ${selectedId === run.id ? "selected" : ""} ${run.pending_gate ? "needs-review" : ""}`}
                  key={run.id}
                  aria-pressed={selectedId === run.id}
                  onClick={() => setSelectedId(run.id)}
                >
                  <div className="run-card-top">
                    <span className={`status-pill ${statusTone(run.status)}`}>{humanStatus(run.status)}</span>
                    <span className="risk-meta">Risk {run.risk_class}</span>
                  </div>
                  <strong>{run.topic_title ?? `Run ${shortId(run.id)}`}</strong>
                  <p>{run.vertical_key}{run.topic_urgency ? ` · ${run.topic_urgency} urgency` : ""}</p>
                  <div className="run-card-bottom">
                    <span>{formatDate(run.updated_at)}</span>
                    {run.pending_gate && <b className="needs-decision-tag">Review gate {run.pending_gate} →</b>}
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section className="detail-panel">
            {loadingDetail && <div className="empty-state">Loading run detail…</div>}
            {!loadingDetail && !detail && (
              <div className="empty-state">Select a workflow run to inspect it.</div>
            )}

            {!loadingDetail && detail && (
              <>
                <div className="detail-hero">
                  <div>
                    <div className="detail-meta">
                      <span className={`status-pill ${statusTone(detail.run.status)}`}>
                        {detail.run.status}
                      </span>
                      <span>{detail.run.vertical_key}</span>
                      <span>{detail.run.risk_class}</span>
                      <span>v{detail.run.state_version}</span>
                    </div>
                    <h2>{detail.run.topic_title ?? `Workflow ${shortId(detail.run.id)}`}</h2>
                    <p>Updated {formatDate(detail.run.updated_at)}</p>
                  </div>
                  <code>{shortId(detail.run.id)}</code>
                </div>

                {(detail.run.pending_gate || detail.recovery_action) && (
                  <section className="review-panel" aria-labelledby="decision-heading">
                    <div className="review-heading">
                      <div>
                        <p className="eyebrow">Human decision · {detail.run.pending_gate ? `Gate ${detail.run.pending_gate}` : "Recovery"}</p>
                        <h3 id="decision-heading">{detail.run.pending_gate ? "Review this story before deciding" : "Review before restarting the workflow"}</h3>
                        <p>Decision outcomes are recorded in the audit trail.</p>
                      </div>
                      <span className={`status-pill ${statusTone(detail.run.status)}`}>{humanStatus(detail.run.status)}</span>
                    </div>
                    <div className="review-context">
                      <div className="review-fact"><span>Risk</span><strong>{detail.run.risk_class} · {detail.run.confidence_class} confidence</strong></div>
                      <div className="review-fact"><span>Urgency</span><strong>{detail.run.topic_urgency ?? "Not rated"}</strong></div>
                      <div className="review-fact"><span>Topic score</span><strong>{detail.run.topic_composite_score ?? "Not scored"}</strong></div>
                      <div className="review-fact"><span>Available evidence</span><strong>{(detail.run.topic_sources?.length ?? 0) + detail.evidence.length} source links · {detail.claims.length} claims</strong></div>
                    </div>
                    {detail.run.topic_proposed_angle && (
                      <div className="editorial-angle">
                        <span>Proposed angle{detail.run.topic_proposed_format ? ` · ${detail.run.topic_proposed_format}` : ""}</span>
                        <p>{detail.run.topic_proposed_angle}</p>
                      </div>
                    )}
                    {(detail.run.topic_sources?.length ?? 0) > 0 ? (
                      <div className="topic-sources">
                        <strong>Original topic sources</strong>
                        <ul>{detail.run.topic_sources?.map((source, index) => {
                          const href = safeSourceUrl(source);
                          return <li key={`${source}-${index}`}>{href
                            ? <a href={href} target="_blank" rel="noopener noreferrer">{new URL(href).hostname} ↗</a>
                            : <span>{source}</span>}</li>;
                        })}</ul>
                      </div>
                    ) : (
                      <p className="review-caution">No original topic source links are attached yet. Consider this limitation before approving.</p>
                    )}
                    {detail.claims.some((claim) => claim.contested || claim.stale || claim.support_status !== "SUPPORTED") ||
                      Boolean(detail.draft?.unsupported_factual_claims.length) ? (
                      <p className="review-caution">Some claims may be unsupported, stale or contested. <a href="#evidence-panel">Inspect evidence ↓</a></p>
                    ) : detail.evidence.length > 0 ? (
                      <p className="review-support">Supporting material is available. <a href="#evidence-panel">Review claims and sources ↓</a></p>
                    ) : null}
                    {detail.gate_artifact && (
                      <p className="review-artifact">Artifact: {detail.gate_artifact.artifact_type}, version {detail.gate_artifact.artifact_version} · {shortId(detail.gate_artifact.artifact_id)}</p>
                    )}
                    <div className="review-controls">
                      <label className="review-checkbox">
                        <input type="checkbox" checked={reviewConfirmed}
                          onChange={(event) => { setReviewConfirmed(event.target.checked); setPendingAction(null); }} />
                        <span>I have reviewed the information available for this decision.</span>
                      </label>
                      <label htmlFor="decision-note" className="note-label">Decision note
                        <span>{decisionRequiresNote ? " · Required for rejection or revision (at least 10 characters)" : " · Optional, recommended for audit"}</span>
                      </label>
                      <textarea id="decision-note" value={reason} maxLength={1000}
                        onChange={(event) => setReason(event.target.value)}
                        placeholder="Explain the editorial rationale or missing information…" rows={3} />
                      <div className="action-row" aria-label="Decision outcomes">
                        {gateActions.map((outcome) => (
                          <button key={outcome} type="button"
                            aria-pressed={pendingAction === outcome}
                            className={`${outcome === "APPROVED" ? "primary-button" : "ghost-button"} ${pendingAction === outcome ? "action-selected" : ""}`}
                            disabled={actionBusy || !reviewConfirmed || !operatorId.trim()}
                            onClick={() => setPendingAction(outcome)}>
                            {humanStatus(outcome)}
                          </button>
                        ))}
                        {detail.recovery_action && (
                          <button type="button" className="ghost-button" aria-pressed={pendingAction === "RECOVER"}
                            disabled={actionBusy || !reviewConfirmed || !operatorId.trim()}
                            onClick={() => setPendingAction("RECOVER")}>
                            {humanStatus(detail.recovery_action)} run
                          </button>
                        )}
                      </div>
                      {pendingAction && (
                        <div className="decision-confirm" role="group" aria-label="Confirm your selected action">
                          <div>
                            <strong>Confirm: {pendingAction === "RECOVER" ? "Recover run" : humanStatus(pendingAction)}</strong>
                            <p>This will be recorded for this workflow run. Check the outcome and note before continuing.</p>
                            {decisionRequiresNote && reason.trim().length < 10 &&
                              <p className="required-note">Add a reason of at least 10 characters to proceed.</p>}
                          </div>
                          <div className="confirmation-buttons">
                            <button className="text-button" type="button" disabled={actionBusy}
                              onClick={() => setPendingAction(null)}>Cancel</button>
                            <button className="primary-button" type="button" disabled={actionBusy || !canSubmitAction}
                              onClick={() => pendingAction === "RECOVER"
                                ? void recoverRun() : void submitGate(pendingAction)}>
                              {actionBusy ? "Saving…" : "Confirm decision"}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </section>
                )}

                <section className="metric-strip">
                  <article><span>Model calls</span><strong>{detail.usage.calls}</strong></article>
                  <article><span>Tokens</span><strong>{(detail.usage.input_tokens + detail.usage.output_tokens).toLocaleString()}</strong></article>
                  <article><span>Cost</span><strong>${Number(detail.usage.total_cost_usd).toFixed(4)}</strong></article>
                  <article><span>Avg latency</span><strong>{detail.usage.average_latency_ms ? `${Math.round(detail.usage.average_latency_ms)} ms` : "—"}</strong></article>
                </section>

                <div className="detail-sections">
                  <section className="card-section">
                    <div className="section-heading">
                      <div><p className="eyebrow">Editorial</p><h3>Draft preview</h3></div>
                      {detail.draft && <span>{detail.draft.locale} · v{detail.draft.version}</span>}
                    </div>
                    {detail.draft ? (
                      <article className="draft-preview">
                        <h4>{detail.draft.title}</h4>
                        {detail.draft.deck && <p className="draft-deck">{detail.draft.deck}</p>}
                        <div className="draft-body">{detail.draft.body}</div>
                        {detail.draft.unsupported_factual_claims.length > 0 && (
                          <div className="warning-box">
                            <strong>Unsupported factual claims</strong>
                            <ul>
                              {detail.draft.unsupported_factual_claims.map((claim) => <li key={claim}>{claim}</li>)}
                            </ul>
                          </div>
                        )}
                      </article>
                    ) : <div className="empty-inline">No draft yet.</div>}
                  </section>

                  <section className="card-section" id="evidence-panel">
                    <div className="section-heading">
                      <div><p className="eyebrow">Evidence</p><h3>Claims & sources</h3></div>
                      <span>{detail.claims.length} claims · {detail.evidence.length} sources</span>
                    </div>
                    <div className="stack-list">
                      {detail.claims.map((claim) => (
                        <article className="evidence-row" key={claim.id}>
                          <div>
                            <strong>{claim.statement}</strong>
                            <p>{claim.support_status} · {claim.confidence_class} · {claim.risk_class}</p>
                          </div>
                          <div className="tag-row">
                            {claim.material && <span>material</span>}
                            {claim.contested && <span className="warning-tag">contested</span>}
                            {claim.stale && <span className="warning-tag">stale</span>}
                          </div>
                        </article>
                      ))}
                      {detail.evidence.map((item) => (
                        <a className="source-row" href={item.url} target="_blank" rel="noreferrer" key={item.id}>
                          <div>
                            <strong>{item.tier} · {item.source_role}</strong>
                            <p>{item.excerpt ?? item.url}</p>
                          </div>
                          <span>↗</span>
                        </a>
                      ))}
                      {detail.claims.length === 0 && detail.evidence.length === 0 && (
                        <div className="empty-inline">No evidence package yet.</div>
                      )}
                    </div>
                  </section>

                  <section className="card-section">
                    <div className="section-heading">
                      <div><p className="eyebrow">Creative</p><h3>Assets</h3></div>
                      <span>{detail.assets.length}</span>
                    </div>
                    <div className="asset-grid">
                      {detail.assets.map((asset) => (
                        <article className="asset-card" key={asset.id}>
                          {asset.uri ? (
                            <img src={asset.uri} alt={asset.alt_text ?? asset.slot} />
                          ) : <div className="asset-placeholder">{asset.kind}</div>}
                          <div>
                            <strong>{asset.slot}</strong>
                            <p>{asset.rights_status} · v{asset.version}</p>
                            {asset.caption && <span>{asset.caption}</span>}
                          </div>
                        </article>
                      ))}
                      {detail.assets.length === 0 && <div className="empty-inline">No assets yet.</div>}
                    </div>
                  </section>

                  <section className="card-section">
                    <div className="section-heading">
                      <div><p className="eyebrow">Delivery</p><h3>Publication & distribution</h3></div>
                    </div>
                    {detail.publication ? (
                      <div className="delivery-card">
                        <div>
                          <strong>{detail.publication.provider} → {detail.publication.target}</strong>
                          <p>{detail.publication.status} · {formatDate(detail.publication.published_at ?? detail.publication.scheduled_at)}</p>
                        </div>
                        {detail.publication.external_url && (
                          <a href={detail.publication.external_url} target="_blank" rel="noreferrer">Open ↗</a>
                        )}
                      </div>
                    ) : <div className="empty-inline">Not published yet.</div>}
                    <div className="distribution-grid">
                      {detail.distributions.map((item) => (
                        <article key={item.id}>
                          <strong>{item.channel}</strong>
                          <span>{item.provider}</span>
                          <b className={`status-pill ${statusTone(item.status)}`}>{item.status}</b>
                        </article>
                      ))}
                    </div>
                  </section>

                  <section className="card-section timeline-section">
                    <div className="section-heading">
                      <div><p className="eyebrow">Audit</p><h3>Run timeline</h3></div>
                      <span>{detail.timeline.length} actions · {detail.gates.length} gate decisions</span>
                    </div>
                    <div className="timeline">
                      {detail.timeline.map((item) => (
                        <article key={item.id}>
                          <div className="timeline-marker" />
                          <div>
                            <strong>{item.action_type.replaceAll("_", " ")}</strong>
                            <p>{item.from_status} → {item.to_status}</p>
                            <span>{item.actor_id} · {formatDate(item.created_at)}</span>
                          </div>
                        </article>
                      ))}
                      {detail.timeline.length === 0 && <div className="empty-inline">No workflow actions recorded yet.</div>}
                    </div>
                  </section>
                </div>
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

export default App;
