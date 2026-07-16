export default function RunControls({
  schemas,
  selectedSchema,
  onSelectSchema,
  onStartRun,
  isRunning,
  reviewMode,
  onToggleReviewMode,
}) {
  return (
    <div className="controls">
      <div className="controls-field">
        <label className="controls-label mono">SCHEMA</label>
        <select
          className="controls-select"
          value={selectedSchema}
          onChange={(e) => onSelectSchema(e.target.value)}
          disabled={isRunning}
        >
          {schemas.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      <label className="controls-checkbox mono">
        <input
          type="checkbox"
          checked={reviewMode}
          onChange={(e) => onToggleReviewMode(e.target.checked)}
          disabled={isRunning}
        />
        Review DDL before deploy
      </label>

      <button
        className="btn btn-primary"
        onClick={onStartRun}
        disabled={isRunning || !selectedSchema}
      >
        {isRunning ? "Agent running…" : "Run migration"}
      </button>
    </div>
  );
}