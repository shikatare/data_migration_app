const STAGES = [
  { key: "extract", label: "Extract", sub: "MySQL DDL pull", tint: "oracle" },
    { key: "convert", label: "Convert", sub: "Cortex-style LLM", tint: "amber" },
    { key: "validate", label: "Validate", sub: "Syntax + diff", tint: "amber" },
    { key: "deploy", label: "Deploy", sub: "Snowflake apply", tint: "snowflake" },
  ];
  
  const STATUS_LABEL_COLOR = {
    idle: "var(--text-faint)",
    running: "var(--amber)",
    waiting: "var(--waiting)",
    success: "var(--success)",
    failed: "var(--fail)",
  };
  
  export default function PipelineRail({ statuses }) {
    return (
      <div className="rail perspective-scene">
        <div className="rail-track" />
        {STAGES.map((stage) => {
          const status = statuses[stage.key] || "idle";
          return (
            <div className="rail-stage" key={stage.key}>
              <div
                className={`rail-card rail-tint-${stage.tint} rail-status-${status}`}
              >
                <span className={`rail-dot rail-dot-${status}`} />
                <span className="rail-card-label">{stage.label}</span>
                <span className="rail-card-sub mono">{stage.sub}</span>
                <span className="rail-card-status mono" style={{ color: STATUS_LABEL_COLOR[status] }}>
                  {status}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    );
  }