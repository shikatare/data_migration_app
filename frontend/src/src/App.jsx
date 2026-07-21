import { useEffect, useMemo, useState, useCallback } from "react";
import PipelineRail from "./components/PipelineRail.jsx";
import EventLog from "./components/EventLog.jsx";
import RunControls from "./components/RunControls.jsx";
import ResultsPanel from "./components/ResultsPanel.jsx";
import RunHistory from "./components/RunHistory.jsx";
import ReviewEditor from "./components/ReviewEditor.jsx";
import { usePipelineSocket } from "./hooks/usePipelineSocket.js";

const DOCS_URL = "https://github.com/shikatare/data_migration_app/tree/main/docs";

export default function App() {
  const [schemas, setSchemas] = useState([]);
  const [selectedSchema, setSelectedSchema] = useState("");
  const [config, setConfig] = useState(null);
  const [runs, setRuns] = useState([]);
  const [activeRunId, setActiveRunId] = useState(null);
  const [reviewMode, setReviewMode] = useState(false);
  const [isContinuing, setIsContinuing] = useState(false);

  const { events, runComplete, runSummary, awaitingReview, clearAwaitingReview, joinRun } = usePipelineSocket();

  const refreshRuns = useCallback(async () => {
    const res = await fetch("/api/pipeline/runs");
    const data = await res.json();
    setRuns(data.runs || []);
  }, []);

  useEffect(() => {
    fetch("/api/pipeline/schemas")
      .then((r) => r.json())
      .then((d) => {
        setSchemas(d.schemas || []);
        if (d.schemas?.length) setSelectedSchema(d.schemas[0]);
      });
    fetch("/api/pipeline/config").then((r) => r.json()).then(setConfig);
    refreshRuns();
  }, [refreshRuns]);

  useEffect(() => {
    if (runComplete) refreshRuns();
  }, [runComplete, refreshRuns]);

  useEffect(() => {
    if (awaitingReview) setIsContinuing(false);
  }, [awaitingReview]);

  const statuses = useMemo(() => {
    const s = { extract: "idle", convert: "idle", validate: "idle", deploy: "idle" };
    for (const evt of events) {
      if (evt.agent === "extract") s.extract = evt.status;
      if (evt.agent === "convert") s.convert = evt.status;
      if (evt.agent === "validate") s.validate = evt.status;
      if (evt.agent === "deploy") s.deploy = evt.status;
    }
    return s;
  }, [events]);

  const isRunning = activeRunId && !runComplete && !awaitingReview;

  const startAutoRun = async () => {
    const res = await fetch("/api/pipeline/agentic-runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ schemaName: selectedSchema, approved: true }),
    });
    const data = await res.json();
    setActiveRunId(data.runId);
    joinRun(data.runId);
  };

  const startReviewRun = async () => {
    const res = await fetch("/api/pipeline/review-runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ schemaName: selectedSchema }),
    });
    const data = await res.json();
    setActiveRunId(data.runId);
    joinRun(data.runId);
  };

  const startRun = () => (reviewMode ? startReviewRun() : startAutoRun());

  const continueReviewRun = async (editedTables) => {
    setIsContinuing(true);
    const res = await fetch(`/api/pipeline/review-runs/${activeRunId}/continue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved: true, editedTables }),
    });
    await res.json();
    clearAwaitingReview();
  };

  const stats = useMemo(() => {
    const total = runs.length;
    const ok = runs.filter((r) => (r.status || "").toLowerCase() === "success").length;
    const rate = total ? Math.round((ok / total) * 100) : null;
    return { total, ok, rate };
  }, [runs]);

  return (
    <div className="shell">
      {/* ---------- Sticky nav ---------- */}
      <nav className="nav">
        <div className="nav-left">
          <span className="nav-brand">
            <span style={{ color: "var(--oracle)" }}>MySQL</span>
            <span className="nav-brand-arrow">→</span>
            <span style={{ color: "var(--snowflake)" }}>Snowflake</span>
          </span>
          <div className="nav-links">
            <a href="#pipeline">Pipeline</a>
            <a href="#activity">Activity</a>
            <a href="#history">Runs</a>
            <a href={DOCS_URL} target="_blank" rel="noreferrer">Docs</a>
          </div>
        </div>
      </nav>

      {/* ---------- Hero ---------- */}
      <header className="hero">
        <div className="hero-gradient" aria-hidden="true" />
        <div className="hero-inner">
          <p className="hero-eyebrow">Schemas migrating on autopilot</p>
          <h1 className="hero-title">
            <span style={{ color: "var(--oracle)" }}>MySQL</span>
            <span className="hero-title-arrow">→</span>
            <em>Snowflake</em>
          </h1>
          <p className="hero-sub">
            Extract, convert, validate and deploy your schema from MySQL to Snowflake — from your
            first table to your last, with an AI agent watching every step.
          </p>
          <div className="hero-cta">
            <RunControls
              schemas={schemas}
              selectedSchema={selectedSchema}
              onSelectSchema={setSelectedSchema}
              onStartRun={startRun}
              isRunning={isRunning}
              reviewMode={reviewMode}
              onToggleReviewMode={setReviewMode}
            />
          </div>
        </div>
      </header>

      <main className="site-main">
        {/* ---------- Pipeline stages ---------- */}
        <section className="section" id="pipeline">
          <div className="section-head">
            <h2>Every stage in one pipeline.</h2>
            <p>Four autonomous agents hand off the migration, start to finish.</p>
          </div>
          <div className="panel rail-panel">
            <PipelineRail statuses={statuses} />
          </div>
        </section>

        {/* ---------- Stats band ---------- */}
        <section className="stat-band">
          <div className="stat">
            <div className="stat-num">{stats.total}</div>
            <div className="stat-label">migrations run</div>
          </div>
          <div className="stat">
            <div className="stat-num">{stats.rate === null ? "—" : `${stats.rate}%`}</div>
            <div className="stat-label">completed successfully</div>
          </div>
          <div className="stat">
            <div className="stat-num">{schemas.length}</div>
            <div className="stat-label">schemas available</div>
          </div>
          <div className="stat">
            <div className="stat-num">4</div>
            <div className="stat-label">automated stages</div>
          </div>
        </section>

        {/* ---------- Live console ---------- */}
        <section className="section" id="activity">
          <div className="section-head">
            <h2>Watch it happen, live.</h2>
            <p>Every conversion streams in as the agent works — review before deploy when you want control.</p>
          </div>

          {awaitingReview ? (
            <div className="panel">
              <ReviewEditor
                awaitingReview={awaitingReview}
                onContinue={continueReviewRun}
                isSubmitting={isContinuing}
              />
            </div>
          ) : (
            <div className="console-grid">
              <div className="panel">
                <EventLog events={events} />
              </div>
              <div className="panel">
                <ResultsPanel record={runComplete} summary={runSummary} />
              </div>
            </div>
          )}
        </section>

        {/* ---------- Run history ---------- */}
        <section className="section" id="history">
          <div className="section-head">
            <h2>Your migration history.</h2>
            <p>Every run, its schema, and how it landed.</p>
          </div>
          <div className="panel">
            <RunHistory runs={runs} />
          </div>
        </section>
      </main>

      {/* ---------- Footer ---------- */}
      <footer className="site-footer">
        <div className="footer-grid">
          <div className="footer-brand">
            <span className="nav-brand">
              <span style={{ color: "var(--oracle)" }}>MySQL</span>
              <span className="nav-brand-arrow">→</span>
              <span style={{ color: "var(--snowflake)" }}>Snowflake</span>
            </span>
            <p className="footer-tag">Migration Agent Console</p>
          </div>
          <div className="footer-col">
            <h4>Sections</h4>
            <a href="#pipeline">Pipeline</a>
            <a href="#activity">Activity</a>
            <a href="#history">Runs</a>
            <a href={DOCS_URL} target="_blank" rel="noreferrer">Docs</a>
          </div>
        </div>
        <div className="footer-base">
          <span className="mono">© {new Date().getFullYear()} Migration Agent</span>
          <span className="mono">Built for MySQL → Snowflake</span>
        </div>
      </footer>
    </div>
  );
}


