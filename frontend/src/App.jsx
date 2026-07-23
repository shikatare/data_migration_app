import { useEffect, useMemo, useState, useCallback } from "react";
import PipelineRail from "./components/PipelineRail.jsx";
import EventLog from "./components/EventLog.jsx";
import RunControls from "./components/RunControls.jsx";
import ResultsPanel from "./components/ResultsPanel.jsx";
import RunHistory from "./components/RunHistory.jsx";
import ReviewEditor from "./components/ReviewEditor.jsx";
import { usePipelineSocket } from "./hooks/usePipelineSocket.js";

export default function App() {
  const [pipelines, setPipelines] = useState([]);
  const [selectedPipeline, setSelectedPipeline] = useState("");
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
    fetch("/api/pipeline/pipelines")
      .then((r) => r.json())
      .then((d) => {
        setPipelines(d.pipelines || []);
        setSelectedPipeline(d.default || d.pipelines?.[0]?.key || "");
      });
    fetch("/api/pipeline/config").then((r) => r.json()).then(setConfig);
    refreshRuns();
  }, [refreshRuns]);

  useEffect(() => {
    if (!selectedPipeline) return;
    fetch(`/api/pipeline/schemas?pipeline=${encodeURIComponent(selectedPipeline)}`)
      .then((r) => r.json())
      .then((d) => {
        setSchemas(d.schemas || []);
        setSelectedSchema(d.schemas?.[0] || "");
      });
  }, [selectedPipeline]);

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
  const currentPipeline = pipelines.find((p) => p.key === selectedPipeline);

  const startAutoRun = async () => {
    const res = await fetch("/api/pipeline/agentic-runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ schemaName: selectedSchema, pipeline: selectedPipeline, approved: true }),
    });
    const data = await res.json();
    setActiveRunId(data.runId);
    joinRun(data.runId);
  };

  const startReviewRun = async () => {
    const res = await fetch("/api/pipeline/review-runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ schemaName: selectedSchema, pipeline: selectedPipeline }),
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

  const sourceModeKey = currentPipeline ? `${currentPipeline.key.split("_")[0]}Mode` : null;
  const targetModeKey = selectedPipeline === "mysql_snowflake" ? "snowflakeMode" : "databricksMode";

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-title">
          <span className="topbar-mark">
            <span style={{ color: "var(--oracle)" }}>{currentPipeline?.sourceLabel || "Source"}</span>
            <span className="topbar-arrow">→</span>
            <span style={{ color: "var(--snowflake)" }}>{currentPipeline?.targetLabel || "Target"}</span>
          </span>
          <span className="topbar-sub">Migration Agent Console</span>
        </div>
        {config && currentPipeline && (
          <div className="topbar-modes mono">
            <ModePill label={currentPipeline.sourceLabel.toLowerCase()} value={config[sourceModeKey]} />
            <ModePill label={currentPipeline.targetLabel.toLowerCase()} value={config[targetModeKey]} />
            <ModePill label="llm" value={config.llmProvider} />
          </div>
        )}
      </header>

      <main className="scene-wrap perspective-scene">
        <div className="scene-tilt">
          <div className="main-grid">
            <section className="panel rail-panel">
              <PipelineRail statuses={statuses} sourceLabel={currentPipeline?.sourceLabel} targetLabel={currentPipeline?.targetLabel} />
              <RunControls
                pipelines={pipelines}
                selectedPipeline={selectedPipeline}
                onSelectPipeline={setSelectedPipeline}
                schemas={schemas}
                selectedSchema={selectedSchema}
                onSelectSchema={setSelectedSchema}
                onStartRun={startRun}
                isRunning={isRunning}
                reviewMode={reviewMode}
                onToggleReviewMode={setReviewMode}
              />
            </section>

            {awaitingReview ? (
              <section className="panel" style={{ gridColumn: "1 / -1" }}>
                <ReviewEditor
                  awaitingReview={awaitingReview}
                  onContinue={continueReviewRun}
                  isSubmitting={isContinuing}
                />
              </section>
            ) : (
              <>
                <section className="panel">
                  <EventLog events={events} />
                </section>

                <section className="panel">
                  <ResultsPanel record={runComplete} summary={runSummary} />
                </section>
              </>
            )}

            <section className="panel">
              <RunHistory runs={runs} />
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}

function ModePill({ label, value }) {
  return (
    <span className="mode-pill">
      <span className="mode-pill-label">{label}</span>
      <span className={`mode-pill-value ${value === "mock" ? "mode-mock" : "mode-real"}`}>{value}</span>
    </span>
  );
}