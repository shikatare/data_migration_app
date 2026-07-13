const AGENT_COLOR = {
    extract: "var(--oracle)",
    convert: "var(--amber)",
    validate: "var(--amber)",
    deploy: "var(--snowflake)",
    log_notify: "var(--text-muted)",
    pipeline: "var(--fail)",
  };
  
  export default function EventLog({ events }) {
    return (
      <div className="log-panel">
        <div className="log-header">
          <span>Run log</span>
          <span className="mono log-header-count">{events.length} event{events.length === 1 ? "" : "s"}</span>
        </div>
        <div className="log-body">
          {events.length === 0 && <div className="log-empty">Start a run to see live agent activity here.</div>}
          {events.map((evt, i) => (
            <div className="log-line" key={i}>
              <span className="log-time mono">{new Date(evt.timestamp).toLocaleTimeString()}</span>
              <span className="log-agent mono" style={{ color: AGENT_COLOR[evt.agent] || "var(--text-muted)" }}>
                [{evt.agent}]
              </span>
              <span className="log-status mono">{evt.status}</span>
              <span className="log-message">{evt.message}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }