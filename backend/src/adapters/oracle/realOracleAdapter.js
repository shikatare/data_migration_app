/**
 * Real Oracle Adapter — activated when ORACLE_MODE=real.
 * Uses `oracledb` with credentials from the secrets adapter.
 * NOT wired to a live DB by default. Install `oracledb` and set
 * ORACLE_MODE=real + ORACLE_* secrets to activate.
 */
import { getSecret } from "../secrets/index.js";

export async function extractSchema({ schemaName }) {
  const creds = await getSecret("oracle");
  if (!creds.connectString) {
    throw new Error(
      "ORACLE_MODE=real but no Oracle credentials found. Set ORACLE_USER / " +
        "ORACLE_PASSWORD / ORACLE_CONNECT_STRING (or configure AWS Secrets Manager)."
    );
  }

  const oracledb = (await import("oracledb")).default;

  const connection = await oracledb.getConnection({
    user: creds.user,
    password: creds.password,
    connectString: creds.connectString,
  });

  try {
    const tables = await connection.execute(
      `SELECT table_name FROM all_tables WHERE owner = :schemaName`,
      { semaName }
    );

    const schema = { schemaName, tables: [] };

    for (const row of tables.rows) {
      const tableName = row[0];

      const columns = await connection.execute(
        `SELECT column_name, data_type, data_length, nullable
         FROM all_tab_columns
         WHERE owner = :schemaName AND table_name = :tableName
         ORDER BY column_id`,
        { schemaName, tableName }
      );

      const constraints = await connection.execute(
        `SELECT constraint_name, constraint_type, search_condition
         FROM all_constraints
         WHERE owner = :schemaName AND table_name = :tableName`,
        { schemaName, tableName }
      );

      const ddlResult = await connection.execute(
        `SELECT DBMS_METADATA.GET_DDL('TABLE', :tableName, :schemaName) FROM dual`,
        { tableName, schemaName }
      );

      schema.tables.push({
        name: tableName,
        columns: columns.rows.map(([name, type, length, nullable]) => ({
          name,
          type,
          length,
          nullable: nullable === "Y",
        })),
        constraints: constraints.rows.map(([name, type, condition]) => ({
          name,
          type,
          condition,
        })),
        rawDdl: ddlResult.rows[0]?.[0]?.toString() ?? "",
      });
    }

    return schema;
  } finally {
    await connection.close();
  }
}

export async function listAvailableSchemas() {
  throw new Error("listAvailableSchemas is a mock-mode convenience only; pass a schemaName directly in real mode.");
}
