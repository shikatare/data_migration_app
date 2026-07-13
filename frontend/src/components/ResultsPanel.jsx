export default function ResultsPanel({ record }) {
    if (!record) {
      return (
        <div className="results-panel results-empty">
          <p>No completed run yet. Results — extracted schema, converted DDL, validation diffs, deploy status — will appear here.</p>
        </div>
      );
    }
  
    const { extract, convert, validateDeploy, overallStatus } = record;
  
    return (
      <div className="results-panel">
        <div className="results-status">
          <span className="mono">RUN {record.runId}</span>
          <span className={`status-pill status-${overallStatus}`}>{overallStatus.replace("_", " ")}</span>
        </div>
  
        {extract && (
          <section className="results-section">
            <h4>Extract — {extract.tableCount} table(s)</h4>
            {extract.flags.length === 0 ? (
              <p className="results-muted">No unmapped constructs flagged.</p>
            ) : (
              <ul className="results-list">
                {extract.flags.map((f, i) => (
                  <li key={i}>
                    <span className="mono results-tag" style={{ color: "var(--oracle)" }}>{f.table}{f.column ? `.${f.column}` : ""}</span>
                    {f.reason}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
  
        {convert && (
          <section className="results-section">
            <h4>Convert — {convert.tableCount} table(s) converted</h4>
            {convert.warnings.length === 0 ? (
              <p className="results-muted">No conversion warnings.</p>
            ) : (
              <ul className="results-list">
                {convert.warnings.map((w, i) => (
                  <li key={i}>
                    <span className="mono results-tag" style={{ color: "var(--amber)" }}>{w.table}</span>
                    {w.message}
                  </li>
                ))}
              </ul>
            )}
            {convert.convertedTables?.length > 0 && (
              <details className="results-ddl">
                <summary>View converted Snowflake DDL</summary>
                {convert.convertedTables.map((t, i) => (
                  <pre key={i} className="mono ddl-block">{t.ddl}</pre>
                ))}
              </details>
            )}
          </section>
        )}
  
        {validateDeploy && (
          <section className="results-section">
            <h4>Validate / Deploy</h4>
            <p className="results-muted">
              Validation: {validateDeploy.validationPassed ? "passed" : "failed"} · Deploy: {validateDeploy.deployStatus}
            </p>
            {validateDeploy.diffIssues?.length > 0 && (
              <ul className="results-list">
                {validateDeploy.diffIssues.map((d, i) => (
                  <li key={i}><span className="mono results-tag" style={{ color: "var(--fail)" }}>{d.table}</span>{d.issue}</li>
                ))}
              </ul>
            )}
            {validateDeploy.objectsCreated?.length > 0 && (
              <p className="results-muted">
                Deployed: <span className="mono">{validateDeploy.objectsCreated.join(", ")}</span>
              </p>
            )}
          </section>
        )}
      </div>
    );
  }