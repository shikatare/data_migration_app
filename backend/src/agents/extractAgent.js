import { getOracleAdapter } from "../adapters/oracle/index.js";

const UNMAPPED_ORACLE_TYPES = ["LONG", "XMLTYPE"];

/**
 * Extract Agent — pulls schema definitions out of Oracle into a
 * structured, comparable format. Flags constructs with no clean
 * Snowflake equivalent for review.
 */
export async function runExtractAgent({ schemaName, runId, emit }) {
  emit("extract", "running", "Connecting to Oracle and retrieving credentials...");

  const adapter = getOracleAdapter();
  const schema = await adapter.extractSchema({ schemaName });

  const flags = [];
  for (const table of schema.tables) {
    for (const col of table.columns) {
      if (UNMAPPED_ORACLE_TYPES.includes(col.type)) {
        flags.push({
          table: table.name,
          column: col.name,
          type: col.type,
          reason: `${col.type} has no clean Snowflake equivalent — review required`,
        });
      }
    }
    if (table.rawDdl && /PARTITION\s+BY/i.test(table.rawDdl)) {
      flags.push({ table: table.name, reason: "Table appears to use Oracle partitioning — review required" });
    }
  }

  emit(
    "extract",
    "success",
    `Extracted ${schema.tables.length} table(s) from ${schemaName}. ${flags.length} construct(s) flagged for review.`
  );

  return {
    schema,
    flags,
  };
}