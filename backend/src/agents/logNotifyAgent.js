import { putRunRecord } from "../adapters/storage/index.js";
import { publishNotification } from "../adapters/notify/index.js";

/**
 * Log & Notify Agent — always runs, whatever stage the pipeline reached.
 * Writes one record per run ID and publishes a summary alert.
 */
export async function runLogNotifyAgent({ runId, schemaName, startedAt, stageOutcome, emit }) {
  emit("log_notify", "running", "Recording run metadata and publishing summary...");

  const finishedAt = new Date().toISOString();
  const overallStatus = deriveOverallStatus(stageOutcome);

  const record = {
    runId,
    schemaName,
    startedAt,
    finishedAt,
    overallStatus,
    extract: stageOutcome.extract || null,
    convert: stageOutcome.convert || null,
    validateDeploy: stageOutcome.validateDeploy || null,
  };

  let storageOk = true;
  try {
    await putRunRecord(record);
  } catch (e) {
    storageOk = false;
    emit("log_notify", "running", `Warning: failed to write run record — ${e.message}`);
  }

  const notifyResults = await publishNotification({
    runId,
    status: overallStatus,
    message: summarize(record),
  });

  emit(
    "log_notify",
    "success",
    `Run recorded (storage ${storageOk ? "ok" : "failed"}). Notified via: ${notifyResults.map((r) => r.channel).join(", ")}.`
  );

  return { record, notifyResults };
}

function deriveOverallStatus(stageOutcome) {
  if (stageOutcome.validateDeploy?.deployStatus === "success") return "success";
  if (stageOutcome.validateDeploy?.deployStatus === "awaiting_approval") return "awaiting_approval";
  if (stageOutcome.validateDeploy && !stageOutcome.validateDeploy.validationPassed) return "validation_failed";
  if (stageOutcome.validateDeploy?.deployStatus === "failed") return "deploy_failed";
  if (stageOutcome.error) return "error";
  return "partial";
}

function summarize(record) {
  const parts = [`Schema: ${record.schemaName}`, `Status: ${record.overallStatus}`];
  if (record.extract) parts.push(`Extracted ${record.extract.tableCount} table(s), ${record.extract.flagCount} flagged`);
  if (record.convert) parts.push(`Converted ${record.convert.tableCount} table(s), ${record.convert.warningCount} warning(s)`);
  if (record.validateDeploy) parts.push(`Deploy: ${record.validateDeploy.deployStatus}`);
  return parts.join(" | ");
}