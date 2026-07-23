from app.pipelines import get_pipeline
from app.validators.sql_validator import (
    parse_and_check_syntax, structural_diff, check_business_rules,
)
from app.scoring.confidence import score_conversion


def _target_adapter(pipeline: str):
    if pipeline == "mysql_snowflake":
        from app.adapters import snowflake
        return snowflake
    from app.adapters import databricks
    return databricks


def run_validate_deploy_agent(schema, converted_tables, pipeline, run_id, approved, emit) -> dict:
    p = get_pipeline(pipeline)
    target = _target_adapter(pipeline)
    emit("validate", "running", "Parsing DDL syntax and running structural diff...")
    ddl_statements = [t["ddl"] for t in converted_tables]

    syntax_results = parse_and_check_syntax(ddl_statements, p["sqlDialect"])
    syntax_errors = [r for r in syntax_results if not r["valid"]]
    diff_issues = structural_diff(schema, converted_tables)
    rule_violations = check_business_rules(converted_tables, pipeline)
    validation_passed = len(syntax_errors) == 0 and len(diff_issues) == 0

    base = {
        "validationPassed": validation_passed,
        "syntaxErrors": syntax_errors,
        "diffIssues": diff_issues,
        "ruleViolations": rule_violations,
    }
    base["scoring"] = score_conversion(schema, converted_tables, base, pipeline)

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
             f"Validation passed — waiting for manual approval before deploying to {p['targetLabel']}.")
        return {**base, "deployStatus": "awaiting_approval", "objectsCreated": []}

    emit("deploy", "running", f"Dry-running DDL against {p['targetLabel']}...")
    dry = target.dry_run(ddl_statements)
    if any(r.get("dryRunStatus") == "failed" for r in dry):
        emit("deploy", "failed", "Dry-run failed — deployment aborted.")
        return {**base, "deployStatus": "failed", "dryRunResults": dry, "objectsCreated": []}

    emit("deploy", "running", f"Deploying DDL to {p['targetLabel']} (tables before views/FKs)...")
    result = target.deploy(ddl_statements, run_id)
    emit("deploy", "success", f"Deployed {len(result['objectsCreated'])} object(s) to {p['targetLabel']}.")
    return {**base, "deployStatus": result["status"],
            "dryRunResults": dry, "objectsCreated": result["objectsCreated"]}