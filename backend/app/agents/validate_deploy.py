"""Validate/Deploy Agent — runs the three validation checks, computes a
confidence score for human review, then deploys if validation passes and the
run is approved."""
from app.adapters import snowflake
from app.validators.sql_validator import (
    parse_and_check_syntax, structural_diff, check_business_rules,
)
from app.scoring.confidence import score_conversion


def run_validate_deploy_agent(schema, converted_tables, run_id, approved, emit) -> dict:
    emit("validate", "running", "Parsing DDL syntax and running structural diff...")
    ddl_statements = [t["ddl"] for t in converted_tables]

    syntax_results = parse_and_check_syntax(ddl_statements)
    syntax_errors = [r for r in syntax_results if not r["valid"]]
    diff_issues = structural_diff(schema, converted_tables)
    rule_violations = check_business_rules(converted_tables)
    validation_passed = len(syntax_errors) == 0 and len(diff_issues) == 0

    base = {
        "validationPassed": validation_passed,
        "syntaxErrors": syntax_errors,
        "diffIssues": diff_issues,
        "ruleViolations": rule_violations,
    }
    # Confidence scoring runs regardless of pass/fail — the report reflects reality.
    base["scoring"] = score_conversion(schema, converted_tables, base)

    if not validation_passed:
        emit("validate", "failed",
             f"Validation failed: {len(syntax_errors)} syntax error(s), "
             f"{len(diff_issues)} structural diff issue(s).")
        return {**base, "deployStatus": "not_attempted", "objectsCreated": []}

    emit("validate", "success",
         f"Validation passed. {len(rule_violations)} business-rule warning(s). "
         f"Confidence {int(base['scoring']['overallConfidence'] * 100)}%.")

    if not approved:
        emit("deploy", "waiting",
             "Validation passed — waiting for manual approval before deploying to Snowflake.")
        return {**base, "deployStatus": "awaiting_approval", "objectsCreated": []}

    emit("deploy", "running", "Dry-running DDL against Snowflake sandbox...")
    dry = snowflake.dry_run(ddl_statements)
    if any(r["dryRunStatus"] == "failed" for r in dry):
        emit("deploy", "failed", "Dry-run failed — deployment aborted.")
        return {**base, "deployStatus": "failed", "dryRunResults": dry, "objectsCreated": []}

    emit("deploy", "running", "Deploying DDL to Snowflake (tables before views/FKs)...")
    result = snowflake.deploy(ddl_statements, run_id)
    emit("deploy", "success", f"Deployed {len(result['objectsCreated'])} object(s) to Snowflake.")
    return {**base, "deployStatus": result["status"],
            "dryRunResults": dry, "objectsCreated": result["objectsCreated"]}