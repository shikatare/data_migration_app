import { getSnowflakeAdapter } from "../adapters/snowflake/index.js";
import { parseAndCheckSyntax, structuralDiff, checkBusinessRules } from "../validators/sqlValidator.js";

/**
 * Validate/Deploy Agent — confirms the converted DDL is correct and safe,
 * then applies it to Snowflake. Deploy only runs if validation passes.
 * `approved` stands in for a manual-approval gate — the orchestrator
 * won't call deploy() until the frontend confirms it.
 */
export async function runValidateDeployAgent({ schema, convertedTables, runId, approved, emit }) {
  emit("validate", "running", "Parsing DDL syntax and running structural diff...");

  const ddlStatements = convertedTables.map((t) => t.ddl);

  const syntaxResults = parseAndCheckSyntax(ddlStatements);
  const syntaxErrors = syntaxResults.filter((r) => !r.valid);

  const diffIssues = structuralDiff(schema, convertedTables);
  const ruleViolations = checkBusinessRules(convertedTables);

  const validationPassed = syntaxErrors.length === 0 && diffIssues.length === 0;

  if (!validationPassed) {
    emit(
      "validate",
      "failed",
      `Validation failed: ${syntaxErrors.length} syntax error(s), ${diffIssues.length} structural diff issue(s).`
    );
    return {
      validationPassed: false,
      syntaxErrors,
      diffIssues,
      ruleViolations,
      deployStatus: "not_attempted",
      objectsCreated: [],
    };
  }

  emit("validate", "success", `Validation passed. ${ruleViolations.length} business-rule warning(s).`);

  if (!approved) {
    emit("deploy", "waiting", "Validation passed — waiting for manual approval before deploying to Snowflake.");
    return {
      validationPassed: true,
      syntaxErrors,
      diffIssues,
      ruleViolations,
      deployStatus: "awaiting_approval",
      objectsCreated: [],
    };
  }

  emit("deploy", "running", "Dry-running DDL against Snowflake sandbox...");
  const snowflake = getSnowflakeAdapter();
  const dryRunResults = await snowflake.dryRun({ ddlStatements });
  const dryRunFailed = dryRunResults.some((r) => r.dryRunStatus === "failed");

  if (dryRunFailed) {
    emit("deploy", "failed", "Dry-run failed — deployment aborted.");
    return {
      validationPassed: true,
      syntaxErrors,
      diffIssues,
      ruleViolations,
      deployStatus: "failed",
      dryRunResults,
      objectsCreated: [],
    };
  }

  emit("deploy", "running", "Deploying DDL to Snowflake (tables before views/FKs)...");
  const deployResult = await snowflake.deploy({ ddlStatements, runId });

  emit("deploy", "success", `Deployed ${deployResult.objectsCreated.length} object(s) to Snowflake.`);

  return {
    validationPassed: true,
    syntaxErrors,
    diffIssues,
    ruleViolations,
    deployStatus: deployResult.status,
    dryRunResults,
    objectsCreated: deployResult.objectsCreated,
  };
}