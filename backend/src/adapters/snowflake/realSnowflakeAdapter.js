import { getSecret } from "../secrets/index.js";

async function getConnection() {
  const creds = await getSecret("snowflake");
  if (!creds.account) {
    throw new Error(
      "SNOWFLAKE_MODE=real but no Snowflake credentials found. Set SNOWFLAKE_* " +
        "env vars (or configure AWS Secrets Manager)."
    );
  }
  const snowflake = (await import("snowflake-sdk")).default;
  const connection = snowflake.createConnection({
    account: creds.account,
    username: creds.user,
    password: creds.password,
    warehouse: creds.warehouse,
    database: creds.database,
    schema: creds.schema,
    role: creds.role,
  });

  return new Promise((resolve, reject) => {
    connection.connect((err, conn) => (err ? reject(err) : resolve(conn)));
  });
}

function execute(connection, sqlText) {
  return new Promise((resolve, reject) => {
    connection.execute({
      sqlText,
      complete: (err, stmt, rows) => (err ? reject(err) : resolve(rows)),
    });
  });
}

export async function dryRun({ ddlStatements }) {
  const connection = await getConnection();
  const results = [];
  for (const stmt of ddlStatements) {
    try {
      await execute(connection, `EXPLAIN ${stmt}`);
      results.push({ statement: stmt.slice(0, 80), dryRunStatus: "ok" });
    } catch (e) {
      results.push({ statement: stmt.slice(0, 80), dryRunStatus: "failed", error: e.message });
    }
  }
  return results;
}

export async function deploy({ ddlStatements }) {
  const connection = await getConnection();
  const created = [];
  for (const stmt of ddlStatements) {
    await execute(connection, stmt);
    const match = stmt.match(/CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+"?(\w+)"?/i);
    if (match) created.push(match[1]);
  }
  return { status: "success", objectsCreated: created };
}

export async function getDeployHistory() {
  throw new Error("getDeployHistory in real mode should query SNOWFLAKE.ACCOUNT_USAGE — not yet implemented.");
}
