export default function RunHistory({ runs }) {
    return (
      <div className="history-panel">
        <div className="log-header">
          <span>Audit trail</span>
          <span className="mono log-header-count">{runs.length} run{runs.length === 1 ? "" : "s"}</span>
        </div>
        {runs.length === 0 ? (
          <div className="log-empty">No runs recorded yet.</div>
        ) : (
          <table className="history-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Schema</th>
                <th>Status</th>
                <th>Finished</th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, 12).map((r) => (
                <tr key={r.runId}>
                  <td className="mono">{r.runId}</td>
                  <td>{r.schemaName}</td>
                  <td><span className={`status-pill status-${r.overallStatus}`}>{r.overallStatus.replace("_", " ")}</span></td>
                  <td className="mono results-muted">{new Date(r.finishedAt).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    );
  }