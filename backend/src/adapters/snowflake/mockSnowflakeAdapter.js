/**
 * Mock Snowflake Adapter — simulates DDL execution without a live
 * account. Applies simple sanity checks and "deploys" by recording
 * the statement, so the rest of the pipeline (Validate/Deploy +
 * Log & Notify) behaves exactly as it would in real mode.
 */
const deployedObjects = [];

export async function dryRun({ ddlStatements }) {
  return ddlStatements.map((stmt) => ({
    statement: stmt.slice(0, 80) + (stmt.length > 80 ? "..." : ""),
    dryRunStatus: "ok",
  }));
}

export async function deploy({ ddlStatements, runId }) {
  const created = [];
  for (const stmt of ddlStatements) {
    const match = stmt.match(/CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+"?(\w+)"?/i);
    const objectName = match ? match[1] : "UNKNOWN_OBJECT";
    deployedObjects.push({ runId, objectName, deployedAt: new Date().toISOString() });
    created.push(objectName);
  }
  return { status: "success", objectsCreated: created };
}

export async function getployHistory() {
  return deployedObjects;
}
