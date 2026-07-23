export default function ResultsPanel({ record, summary }) {
  if (!record) {
    return (
      <div className="results-panel results-empty">
        {summary ? (
          <section className="results-section">
            <h4>Agent summary</h4>
            <p className="results-muted">{summary}</p>
          </section>
        ) : (
          <p>No completed run yet. Results — extracted schema, converted DDL, validation diffs, deploy status — will appear here.</p>
        )}
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

      {summary && (
        <section className="results-section">
          <h4>Agent summary</h4>
          <p className="results-muted">{summary}</p>
        </section>
      )}

      {record.confidence != null && (
        <section className="results-section">
          <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
            <div style={{ fontSize: 30, fontWeight: 700, fontFamily: "var(--font-display)" }}>
              {Math.round(record.confidence * 100)}%
            </div>
            <div style={{ flex: 1, minWidth: 160 }}>
              <div style={{ fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-faint)" }}>
                Conversion confidence
              </div>
              <div className="results-muted">{validateDeploy?.scoring?.recommendation}</div>
            </div>
            <a className="btn btn-primary"
               href={`/api/pipeline/runs/${record.runId}/report`}
               style={{ textDecoration: "none", display: "inline-block" }}>
              Download review report
            </a>
          </div>
          {validateDeploy?.scoring?.reviewItems?.length > 0 && (
            <ul className="results-list" style={{ marginTop: 12 }}>
              {validateDeploy.scoring.reviewItems.map((r, i) => (
                <li key={i}>
                  <span className="mono results-tag">{r.table}.{r.column}</span>
                  {r.sourceType} → {r.targetType} ({Math.round(r.confidence * 100)}%) — {r.note}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
  
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
                <summary>View converted target DDL</summary>
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