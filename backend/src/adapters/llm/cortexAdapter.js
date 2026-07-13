/**
 * Snowflake Cortex Adapter — activated when LLM_PROVIDER=cortex.
 * Calls SNOWFLAKE.CORTEX.COMPLETE via SQL. Requires SNOWFLAKE_MODE=real
 * (or at least valid Snowflake credentials) since Cortex runs inside
 * a Snowflake warehouse.
 *
 * Same complete({ systemPrompt, userPrompt }) -> string interface as the
 * Groq adapter, so convertAgent.js never needs to know which one is active.
 */
import { getSecret } from "../secrets/index.js";

export async function complete({ systemPrompt, userPrompt }) {
  const creds = await getSecret("snowflake");
  if (!creds.account) {
    throw new Error(
      "LLM_PROVIDER=cortex but no Snowflake credentials found. Set SNOWFLAKE_* env vars."
    );
  }

  const snowflake = (await import("snowflake-sdk")).default;
  const connection = snowflake.createConnection({
    account: creds.account,
    username: creds.user,
    password: creds.password,
    warehouse: creds.warehouse,
    database: creds.database,
    sema: creds.schema,
    role: creds.role,
  });

  await new Promise((resolve, reject) => {
    connection.connect((err, conn) => (err ? reject(err) : resolve(conn)));
  });

  const combinedPrompt = `${systemPrompt}\n\n${userPrompt}`;

  return new Promise((resolve, reject) => {
    connection.execute({
      sqlText: `SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?) AS RESPONSE`,
      binds: ["llama3.1-70b", combinedPrompt],
      complete: (err, stmt, rows) => {
        if (err) reject(err);
        else resolve(rows[0].RESPONSE);
      },
    });
  });
}
