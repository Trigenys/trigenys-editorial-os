import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

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

type Filters = {
  vertical: string;
  status: string;
  risk: string;
  topicDecision: string;
  updatedAfter: string;
  updatedBefore: string;
};

const deploymentLabel = import.meta.env.VITE_DEPLOYMENT_LABEL ?? "local";
const requiresOperatorAuth = deploymentLabel !== "local";
const operatorSessionKey = "trigenys-editorial-os.operator-token";

function withOperatorAuthorization(token: string, init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return { ...init, headers };
}

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

function statusTone(status: string) {
  if (["PUBLISHED", "DISTRIBUTED", "MEASURED", "TOPIC_APPROVED", "EDITORIAL_APPROVED", "PUBLISH_APPROVED"].includes(status)) {
    return "positive";
  }
  if (["FAILED_TERMINAL", "REJECTED"].includes(status)) return "danger";
  if (["FAILED_RETRYABLE", "BLOCKED"].includes(status)) return "warning";
  return "neutral";
}

async function readJson<T>(response: Response): Promise<T> {
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
  const [operatorId, setOperatorId] = useState("operator");
  const [operatorTokenInput, setOperatorTokenInput] = useState("");
  const [operatorToken, setOperatorToken] = useState(() => {
    try {
      return window.sessionStorage.getItem(operatorSessionKey) ?? "";
    } catch {
      return "";
    }
  });
  const [reason, setReason] = useState("");
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      const response = await fetch(
        `/api/operator/runs?${params.toString()}`,
        withOperatorAuthorization(operatorToken),
      );
      const payload = await readJson<RunSummary[]>(response);
      setRuns(payload);
      setSelectedId((current) => {
        if (current && payload.some((run) => run.id === current)) return current;
        return payload[0]?.id ?? null;
      });
    } catch (requestError) {
      setRuns([]);
      setSelectedId(null);
      setDetail(null);
      setError(requestError instanceof Error ? requestError.message : "Unable to load runs.");
    } finally {
      setLoadingRuns(false);
    }
  }, [operatorToken]);

  const loadDetail = useCallback(async (runId: string) => {
    setLoadingDetail(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/operator/runs/${runId}`,
        withOperatorAuthorization(operatorToken),
      );
      const payload = await readJson<RunDetail>(response);
      setDetail(payload);
    } catch (requestError) {
      setDetail(null);
      setError(requestError instanceof Error ? requestError.message : "Unable to load run.");
    } finally {
      setLoadingDetail(false);
    }
  }, [operatorToken]);

  useEffect(() => {
    if (requiresOperatorAuth && !operatorToken) {
      setLoadingRuns(false);
      return;
    }
    void loadRuns(initialFilters);
  }, [loadRuns, operatorToken]);

  useEffect(() => {
    if (selectedId) {
      void loadDetail(selectedId);
    } else {
      setDetail(null);
    }
  }, [selectedId, loadDetail]);

  const queueCounts = useMemo(() => {
    return {
      waiting: runs.filter((run) => run.pending_gate !== null).length,
      blocked: runs.filter((run) => run.status === "BLOCKED").length,
      retryable: runs.filter((run) => run.status === "FAILED_RETRYABLE").length,
      watch: runs.filter((run) => run.topic_decision === "WATCH").length,
    };
  }, [runs]);

  async function submitGate(outcome: string) {
    if (!detail || !operatorId.trim()) return;
    setActionBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/operator/runs/${detail.run.id}/gate`,
        withOperatorAuthorization(operatorToken, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
          outcome,
          actor_id: operatorId.trim(),
          reason: reason.trim() || null,
            details: {},
          }),
        }),
      );
      const payload = await readJson<RunDetail>(response);
      setDetail(payload);
      setReason("");
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
        withOperatorAuthorization(operatorToken, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
          actor_id: operatorId.trim(),
            reason: reason.trim() || null,
          }),
        }),
      );
      const payload = await readJson<RunDetail>(response);
      setDetail(payload);
      setReason("");
      await loadRuns(filters);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Recovery failed.");
    } finally {
      setActionBusy(false);
    }
  }

  function unlockOperatorConsole() {
    const token = operatorTokenInput.trim();
    if (!token) return;
    try {
      window.sessionStorage.setItem(operatorSessionKey, token);
    } catch {
      // The console can still work for this render when storage is unavailable.
    }
    setOperatorToken(token);
    setOperatorTokenInput("");
    setError(null);
  }

  function lockOperatorConsole() {
    try {
      window.sessionStorage.removeItem(operatorSessionKey);
    } catch {
      // Ignore storage failures and clear the in-memory credential.
    }
    setOperatorToken("");
    setOperatorTokenInput("");
    setRuns([]);
    setSelectedId(null);
    setDetail(null);
    setError(null);
  }

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    void loadRuns(filters);
  }

  function setQueueFilter(decision: string, status: string = "") {
    const next = {
      ...filters,
      topicDecision: decision,
      status,
    };
    setFilters(next);
    void loadRuns(next);
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

        <nav className="queue-nav" aria-label="Queues">
          <button type="button" onClick={() => setQueueFilter("", "")}>
            <span>All runs</span><b>{runs.length}</b>
          </button>
          <button type="button" onClick={() => setQueueFilter("PROPOSE")}>
            <span>Propose</span><b>{runs.filter((run) => run.topic_decision === "PROPOSE").length}</b>
          </button>
          <button type="button" onClick={() => setQueueFilter("WATCH")}>
            <span>Watch</span><b>{queueCounts.watch}</b>
          </button>
          <button type="button" onClick={() => setQueueFilter("", "BLOCKED")}>
            <span>Blocked</span><b>{queueCounts.blocked}</b>
          </button>
          <button type="button" onClick={() => setQueueFilter("", "FAILED_RETRYABLE")}>
            <span>Retryable</span><b>{queueCounts.retryable}</b>
          </button>
        </nav>

        <div className="operator-identity">
          {requiresOperatorAuth && (
            <>
              <label htmlFor="operator-token">Staging access token</label>
              <input
                id="operator-token"
                type="password"
                autoComplete="off"
                value={operatorTokenInput}
                onChange={(event) => setOperatorTokenInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") unlockOperatorConsole();
                }}
                placeholder={operatorToken ? "Authenticated for this tab" : "Paste access token"}
              />
              <div className="operator-auth-actions">
                <button
                  className="primary-button"
                  type="button"
                  disabled={!operatorTokenInput.trim()}
                  onClick={unlockOperatorConsole}
                >
                  Unlock
                </button>
                {operatorToken && (
                  <button className="ghost-button" type="button" onClick={lockOperatorConsole}>
                    Lock
                  </button>
                )}
              </div>
              <small>
                {operatorToken
                  ? "Credential kept in session storage for this tab only."
                  : "Required in staging. It is never bundled into the frontend."}
              </small>
            </>
          )}

          <label htmlFor="operator-id">Operator identity</label>
          <input
            id="operator-id"
            value={operatorId}
            onChange={(event) => setOperatorId(event.target.value)}
            placeholder="operator"
          />
          <small>Recorded on every gate and recovery action.</small>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Trigenys Editorial OS</p>
            <h1>Control room</h1>
            <span className="deployment-badge">{deploymentLabel}</span>
          </div>
          <button
            className="ghost-button"
            type="button"
            disabled={requiresOperatorAuth && !operatorToken}
            onClick={() => void loadRuns(filters)}
          >
            Refresh
          </button>
        </header>

        <section className="summary-grid" aria-label="Queue summary">
          <article><span>Visible runs</span><strong>{runs.length}</strong></article>
          <article><span>Awaiting gate</span><strong>{queueCounts.waiting}</strong></article>
          <article><span>Blocked</span><strong>{queueCounts.blocked}</strong></article>
          <article><span>Retryable</span><strong>{queueCounts.retryable}</strong></article>
        </section>

        <form className="filters" onSubmit={applyFilters}>
          <input
            value={filters.vertical}
            onChange={(event) => setFilters({ ...filters, vertical: event.target.value })}
            placeholder="Vertical"
            aria-label="Vertical"
          />
          <select
            value={filters.status}
            onChange={(event) => setFilters({ ...filters, status: event.target.value })}
            aria-label="Workflow status"
          >
            <option value="">All statuses</option>
            {statusOptions.map((status) => <option key={status} value={status}>{status}</option>)}
          </select>
          <select
            value={filters.risk}
            onChange={(event) => setFilters({ ...filters, risk: event.target.value })}
            aria-label="Risk class"
          >
            <option value="">All risks</option>
            {["R0", "R1", "R2", "R3"].map((risk) => <option key={risk} value={risk}>{risk}</option>)}
          </select>
          <select
            value={filters.topicDecision}
            onChange={(event) => setFilters({ ...filters, topicDecision: event.target.value })}
            aria-label="Topic decision"
          >
            <option value="">All topic decisions</option>
            <option value="PROPOSE">PROPOSE</option>
            <option value="WATCH">WATCH</option>
            <option value="IGNORE">IGNORE</option>
          </select>
          <input
            type="date"
            value={filters.updatedAfter}
            onChange={(event) => setFilters({ ...filters, updatedAfter: event.target.value })}
            aria-label="Updated after"
          />
          <input
            type="date"
            value={filters.updatedBefore}
            onChange={(event) => setFilters({ ...filters, updatedBefore: event.target.value })}
            aria-label="Updated before"
          />
          <button className="primary-button" type="submit">Apply</button>
          <button
            className="text-button"
            type="button"
            onClick={() => {
              setFilters(initialFilters);
              void loadRuns(initialFilters);
            }}
          >
            Reset
          </button>
        </form>

        {error && <div className="error-banner" role="alert">{error}</div>}

        <div className="console-grid">
          <section className="run-list-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Queue</p>
                <h2>Workflow runs</h2>
              </div>
              {loadingRuns && <span className="loading-dot">Loading</span>}
            </div>

            <div className="run-list">
              {!loadingRuns && runs.length === 0 && (
                <div className="empty-state">
                  {requiresOperatorAuth && !operatorToken
                    ? "Unlock the staging console from the sidebar."
                    : "No runs match these filters."}
                </div>
              )}
              {runs.map((run) => (
                <button
                  type="button"
                  className={`run-card ${selectedId === run.id ? "selected" : ""}`}
                  key={run.id}
                  onClick={() => setSelectedId(run.id)}
                >
                  <div className="run-card-top">
                    <span className={`status-pill ${statusTone(run.status)}`}>{run.status}</span>
                    <span>{run.risk_class} · {run.confidence_class}</span>
                  </div>
                  <strong>{run.topic_title ?? `Run ${shortId(run.id)}`}</strong>
                  <p>{run.vertical_key} · {run.topic_decision ?? "No topic decision"}</p>
                  <div className="run-card-bottom">
                    <span>{formatDate(run.updated_at)}</span>
                    {run.pending_gate && <b>Gate {run.pending_gate}</b>}
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
                  <section className="action-panel">
                    <div>
                      <p className="eyebrow">Human control</p>
                      <h3>
                        {detail.run.pending_gate
                          ? `Gate ${detail.run.pending_gate} requires a decision`
                          : `${detail.recovery_action} is available`}
                      </h3>
                      {detail.gate_artifact && (
                        <p className="muted">
                          {detail.gate_artifact.artifact_type} · v{detail.gate_artifact.artifact_version} · {shortId(detail.gate_artifact.artifact_id)}
                        </p>
                      )}
                    </div>
                    <textarea
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                      placeholder="Reason or operator note"
                      rows={3}
                    />
                    <div className="action-row">
                      {gateActions.map((outcome) => (
                        <button
                          key={outcome}
                          type="button"
                          className={outcome === "APPROVED" ? "primary-button" : "ghost-button"}
                          disabled={actionBusy || !operatorId.trim()}
                          onClick={() => void submitGate(outcome)}
                        >
                          {outcome.replace("_", " ")}
                        </button>
                      ))}
                      {detail.recovery_action && (
                        <button
                          type="button"
                          className="primary-button"
                          disabled={actionBusy || !operatorId.trim()}
                          onClick={() => void recoverRun()}
                        >
                          {detail.recovery_action}
                        </button>
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

                  <section className="card-section">
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
