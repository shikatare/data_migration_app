import { useEffect, useMemo, useState, useCallback } from "react";
import PipelineRail from "./components/PipelineRail.jsx";
import EventLog from "./components/EventLog.jsx";
import RunControls from "./components/RunControls.jsx";
import ResultsPanel from "./components/ResultsPanel.jsx";
import RunHistory from "./components/RunHistory.jsx";
import { usePipelineSocket } from "./hooks/usePipelineSocket.js";

export default function App() {
  const [schemas, setSchemas] = useState([]);
  const [selectedSchema, setSelectedSchema] = useState("");
  const [config, setConfig] = useState(null);
  const [runs, setRuns] = useState([]);
  const [activeRunId, setActiveRunId] = useState(null);

  const { events, runComplete, runSummary, joinRun } = usePipelineSocket();

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

  const isRunning = activeRunId && !runComplete;

  const startRun = async () => {
    const res = await fetch("/api/pipeline/agentic-runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ schemaName: selectedSchema, approved: true }),
    });
    const data = await res.json();
    setActiveRunId(data.runId);
    joinRun(data.runId);
  };

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-title">
          <span className="topbar-mark">
          <span style={{ color: "var(--oracle)" }}>MySQL</span>
            <span className="topbar-arrow">→</span>
            <span style={{ color: "var(--snowflake)" }}>Snowflake</span>
          </span>
          <span className="topbar-sub">Migration Agent Console</span>
        </div>
        {config && (
          <div className="topbar-modes mono">
            <ModePill label="mysql" value={config.mysqlMode} />
            <ModePill label="snowflake" value={config.snowflakeMode} />
            <ModePill label="llm" value={config.llmProvider} />
          </div>
        )}
      </header>

      <main className="scene-wrap perspective-scene">
        <div className="scene-tilt">
          <div className="main-grid">
            <section className="panel rail-panel">
              <PipelineRail statuses={statuses} />
              <RunControls
                schemas={schemas}
                selectedSchema={selectedSchema}
                onSelectSchema={setSelectedSchema}
                onStartRun={startRun}
                isRunning={isRunning}
              />
            </section>

            <section className="panel">
              <EventLog events={events} />
            </section>

            <section className="panel">
              <ResultsPanel record={runComplete} />
            </section>

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