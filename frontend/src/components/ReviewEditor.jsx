import { useState, useEffect } from "react";

export default function ReviewEditor({ awaitingReview, onContinue, isSubmitting }) {
  const [ddlByTable, setDdlByTable] = useState({});

  useEffect(() => {
    const initial = {};
    for (const t of awaitingReview.convertedTables || []) {
      initial[t.name] = t.ddl;
    }
    setDdlByTable(initial);
  }, [awaitingReview]);

  const handleContinue = () => {
    const edited = (awaitingReview.convertedTables || [])
      .map((t) => ({ name: t.name, ddl: ddlByTable[t.name] }))
      .filter((t) => t.ddl !== undefined);
    onContinue(edited);
  };

  return (
    <div className="review-editor">
      <div className="review-editor-header">
        <h4>{awaitingReview.validationFailed ? "Validation failed — review and fix" : "Review before deploy"}</h4>
        <p className="results-muted">
          {awaitingReview.validationFailed
            ? "Your last edit didn't pass validation. Fix the DDL below and continue, or leave it as-is to see the same error again."
            : "The agent has converted the schema. Review or edit any table's DDL below, then continue to validate and deploy."}
        </p>
      </div>

      {awaitingReview.validationFailed && (
        <div className="review-editor-errors">
          {awaitingReview.diffIssues?.map((d, i) => (
            <p key={`d${i}`} className="review-editor-error">
              <span className="mono results-tag" style={{ color: "var(--fail)" }}>{d.table}</span>
              {d.issue === "missing_columns"
                ? `missing column(s): ${d.columns.join(", ")}`
                : d.issue}
            </p>
          ))}
          {awaitingReview.ruleViolations?.map((r, i) => (
            <p key={`r${i}`} className="review-editor-error">
              <span className="mono results-tag" style={{ color: "var(--fail)" }}>{r.table}</span>
              {r.detail}
            </p>
          ))}
          {awaitingReview.syntaxErrors?.map((s, i) => (
            <p key={`s${i}`} className="review-editor-error">
              <span className="mono results-tag" style={{ color: "var(--fail)" }}>syntax</span>
              {s.error}
            </p>
          ))}
        </div>
      )}

      {(awaitingReview.warnings?.length > 0) && (
        <div className="review-editor-warnings">
          {awaitingReview.warnings.map((w, i) => (
            <p key={i} className="results-muted">
              <span className="mono results-tag" style={{ color: "var(--amber)" }}>{w.table}</span>
              {w.message}
            </p>
          ))}
        </div>
      )}

      <div className="review-editor-tables">
        {(awaitingReview.convertedTables || []).map((t) => (
          <div key={t.name} className="review-editor-table">
            <label className="controls-label mono">{t.name}</label>
            <textarea
              className="review-editor-textarea mono"
              value={ddlByTable[t.name] ?? ""}
              onChange={(e) => setDdlByTable((prev) => ({ ...prev, [t.name]: e.target.value }))}
              spellCheck={false}
            />
          </div>
        ))}
      </div>

      <div className="review-editor-actions">
        <button className="btn btn-primary" onClick={handleContinue} disabled={isSubmitting}>
          {isSubmitting ? "Validating…" : "Approve & Continue"}
        </button>
      </div>
    </div>
  );
}