"""Confidence scoring for a conversion, for human review.

Assigns a confidence score to every column, table, and the run overall,
based on how clean each MySQL->Snowflake type mapping is and whether any
validation check flagged a problem. Produces a review checklist that a human
can work through — the basis of the downloadable report.
"""

# Per-mapping base confidence. Clean 1:1 maps score high; semantic/lossy or
# deprecated maps score low and get surfaced for review.
TYPE_CONFIDENCE = {
    "VARCHAR":    (0.98, "VARCHAR", "Direct 1:1 mapping"),
    "CHAR":       (0.98, "CHAR", "Direct 1:1 mapping"),
    "TEXT":       (0.95, "VARCHAR", "Direct mapping; Snowflake VARCHAR supports up to 16MB"),
    "MEDIUMTEXT": (0.95, "VARCHAR", "Direct mapping; Snowflake VARCHAR supports up to 16MB"),
    "LONGTEXT":   (0.90, "VARCHAR", "Verify max data length fits Snowflake's 16MB VARCHAR limit"),
    "TINYTEXT":   (0.98, "VARCHAR", "Direct mapping"),
    "INT":        (0.97, "NUMBER(10,0)", "Direct mapping"),
    "INTEGER":    (0.97, "NUMBER(10,0)", "Direct mapping"),
    "BIGINT":     (0.97, "NUMBER(19,0)", "Direct mapping"),
    "SMALLINT":   (0.97, "NUMBER(5,0)", "Direct mapping"),
    "TINYINT":    (0.85, "NUMBER(3,0)", "Confirm whether this is a numeric column or a boolean flag (TINYINT(1))"),
    "DECIMAL":    (0.97, "NUMBER", "Direct mapping; precision/scale preserved"),
    "NUMERIC":    (0.97, "NUMBER", "Direct mapping; precision/scale preserved"),
    "FLOAT":      (0.93, "FLOAT", "Direct mapping; confirm precision requirements"),
    "DOUBLE":     (0.93, "FLOAT", "Direct mapping; confirm precision requirements"),
    "DATE":       (0.98, "DATE", "Direct mapping"),
    "DATETIME":   (0.90, "TIMESTAMP_NTZ", "Confirm timezone handling — MySQL DATETIME has no timezone"),
    "TIMESTAMP":  (0.85, "TIMESTAMP_NTZ", "MySQL TIMESTAMP is UTC-normalized; confirm timezone semantics"),
    "BOOLEAN":    (0.97, "BOOLEAN", "Direct mapping"),
    "BOOL":       (0.97, "BOOLEAN", "Direct mapping"),
    "BLOB":       (0.85, "BINARY", "Binary mapping — verify size limits and encoding"),
    "TINYBLOB":   (0.85, "BINARY", "Binary mapping — verify size limits and encoding"),
    "MEDIUMBLOB": (0.85, "BINARY", "Binary mapping — verify size limits and encoding"),
    "LONGBLOB":   (0.80, "BINARY", "Verify max data length fits Snowflake's BINARY limit"),
    "JSON":       (0.55, "VARIANT", "Semi-structured JSON mapped to VARIANT — downstream JSON access patterns must be rewritten"),
    "ENUM":       (0.45, "VARCHAR", "Snowflake has no ENUM type; the allowed-value check is dropped — needs a CHECK constraint or app-level validation"),
    "SET":        (0.40, "VARCHAR", "MySQL SET (multi-value) has no Snowflake equivalent; manual review of stored values required"),
    "YEAR":       (0.60, "NUMBER(4,0)", "Confirm downstream usage expects a 4-digit year, not a date"),
}

REVIEW_THRESHOLD = 0.70   # below this: human review required
VERIFY_THRESHOLD = 0.90   # below this: verify recommended


def _column_score(col: dict) -> dict:
    t = (col.get("type") or "").upper()
    base, target, note = TYPE_CONFIDENCE.get(t, (0.30, "VARCHAR", f"Unrecognized type '{t}' — manual mapping required"))
    return {
        "column": col["name"],
        "sourceType": t,
        "snowflakeType": target,
        "confidence": base,
        "note": note,
    }


def _level(conf: float) -> str:
    if conf < REVIEW_THRESHOLD:
        return "review"        # human review required
    if conf < VERIFY_THRESHOLD:
        return "verify"        # spot-check recommended
    return "auto"              # high confidence


def score_conversion(original_schema: dict, converted_tables: list, validation: dict) -> dict:
    """Return a full scoring object: per-table, per-column, overall + review list."""
    diff_by_table = {}
    for d in validation.get("diffIssues", []):
        diff_by_table.setdefault(d["table"].upper(), []).append(d)
    rule_by_table = {}
    for r in validation.get("ruleViolations", []):
        rule_by_table.setdefault(r["table"].upper(), []).append(r)
    syntax_bad = {
        (s.get("statement") or "")[:40].upper()
        for s in validation.get("syntaxErrors", [])
    }

    tables_out = []
    review_items = []
    weighted_sum = 0.0
    total_cols = 0

    for table in original_schema["tables"]:
        cols = [_column_score(c) for c in table["columns"]]
        col_confs = [c["confidence"] for c in cols] or [1.0]
        table_conf = sum(col_confs) / len(col_confs)

        reasons = []
        # Structural problems are severe — a dropped column can mean silent data loss.
        if diff_by_table.get(table["name"].upper()):
            table_conf = min(table_conf, 0.20)
            reasons.append("Structural diff found missing column(s) vs the source schema")
        # Business-rule violations cap confidence.
        if rule_by_table.get(table["name"].upper()):
            table_conf = min(table_conf, 0.55)
            reasons.append("Business-rule violation on this table")
        # Syntax failure zeroes it out until fixed.
        if any(table["name"].upper() in bad for bad in syntax_bad):
            table_conf = 0.0
            reasons.append("Converted DDL failed syntax validation")

        table_conf = round(table_conf, 2)
        # Conservative level: a high average must not hide a weak column. If any
        # column falls below a threshold, the table inherits that lower level.
        level = _level(table_conf)
        worst_col = min(col_confs)
        if worst_col < REVIEW_THRESHOLD or reasons:
            level = "review"
        elif worst_col < VERIFY_THRESHOLD and level == "auto":
            level = "verify"

        # Collect per-column review items for anything not high-confidence.
        for c in cols:
            if c["confidence"] < VERIFY_THRESHOLD:
                review_items.append({
                    "table": table["name"],
                    "column": c["column"],
                    "sourceType": c["sourceType"],
                    "snowflakeType": c["snowflakeType"],
                    "confidence": c["confidence"],
                    "level": _level(c["confidence"]),
                    "note": c["note"],
                })

        tables_out.append({
            "table": table["name"],
            "columnCount": len(cols),
            "confidence": table_conf,
            "level": level,
            "reasons": reasons,
            "columns": cols,
        })
        weighted_sum += table_conf * len(cols)
        total_cols += len(cols)

    overall = round(weighted_sum / total_cols, 2) if total_cols else 0.0
    review_items.sort(key=lambda x: x["confidence"])

    review_required = sum(1 for r in review_items if r["level"] == "review")
    # Top-line level is conservative: any item needing review makes the whole run "review".
    overall_level = _level(overall)
    if review_required > 0:
        overall_level = "review"
    elif review_items and overall_level == "auto":
        overall_level = "verify"

    return {
        "overallConfidence": overall,
        "overallLevel": overall_level,
        "recommendation": _recommendation(overall, review_items),
        "tables": tables_out,
        "reviewItems": review_items,
        "reviewRequiredCount": review_required,
        "thresholds": {"review": REVIEW_THRESHOLD, "verify": VERIFY_THRESHOLD},
    }


def _recommendation(overall: float, review_items: list) -> str:
    hard = [r for r in review_items if r["level"] == "review"]
    if overall >= VERIFY_THRESHOLD and not hard:
        return "Approve — high confidence, no items require manual review."
    if hard:
        return f"Manual review required — {len(hard)} item(s) below the review threshold."
    return "Review recommended — spot-check the flagged items before approving."