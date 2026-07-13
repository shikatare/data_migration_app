import { getLlmAdapter } from "../adapters/llm/index.js";

const TYPE_MAP_RULES = `
Oracle -> Snowflake type mapping rules (apply exactly):
- VARCHAR2(n) -> VARCHAR(n)
- NUMBER(p,s) -> NUMBER(p,s)  (Snowflake supports NUMBER natively)
- NUMBER(p) with no scale, used as an integer id -> NUMBER(p,0)
- DATE -> TIMESTAMP_NTZ
- CLOB -> VARCHAR (Snowflake VARCHAR supports up to 16MB, no separate CLOB type)
- LONG -> VARCHAR with a warning (deprecated Oracle type, no direct equivalent)
- XMLTYPE -> VARIANT with a warning (semi-structured, needs review)
- BLOB -> BINARY
- CHAR(n) -> CHAR(n)
`;

const FEW_SHOT_EXAMPLES = `
Example 1:
Oracle: CREATE TABLE ACCOUNTS (ACCOUNT_ID NUMBER(10) NOT NULL, OPENED_ON DATE NOT NULL, BALANCE NUMBER(14,2));
Snowflake: CREATE TABLE ACCOUNTS (ACCOUNT_ID NUMBER(10,0) NOT NULL, OPENED_ON TIMESTAMP_NTZ NOT NULL, BALANCE NUMBER(14,2));

Example 2:
Oracle: CREATE TABLE DOCS (DOC_ID NUMBER(10) NOT NULL, BODY CLOB, TAGS XMLTYPE);
Snowflake: CREATE TABLE DOCS (DOC_ID NUMBER(10,0) NOT NULL, BODY VARCHAR, TAGS VARIANT);
-- warning: TAGS converted from XMLTYPE to VARIANT; verify downstream parsing logic
`;

const SYSTEM_PROMPT = `You are the Convert Agent in an Oracle-to-Snowflake migration pipeline.
You translate Oracle DDL into Snowflake-compatible DDL.

${TYPE_MAP_RULES}

${FEW_SHOT_EXAMPLES}

Respond with ONLY a JSON object matching this exact shape, no prose, no markdown fences:
{
  "converted_tables": [
    { "name": "TABLE_NAME", "columns": ["COL1", "COL2"], "ddl": "CREATE TABLE ... ;" }
  ],
  "warnings": [ { "table": "TABLE_NAME", "message": "..." } ],
  "unmapped_types": [ { "table": "TABLE_NAME", "column": "COL", "oracleType": "XMLTYPE" } ]
}`;

function buildUserPrompt(schema, feedback) {
    const tableDdls = schema.tables.map((t) => t.rawDdl).join("\n\n");
    const feedbackBlock = feedback
      ? `\n\nIMPORTANT — a previous attempt at this conversion failed validation. Fix these specific issues:\n${feedback}\n`
      : "";
    return `Convert the following Oracle DDL to Snowflake DDL. Preserve all tables and columns; apply the type-mapping rules exactly; flag anything without a clean mapping in "warnings" and "unmapped_types".${feedbackBlock}\n\n${tableDdls}`;
  }


  export async function runConvertAgent({ schema, runId, emit, feedback }) {
    emit(
      "convert",
      "running",
      feedback
        ? "Re-converting with validation feedback..."
        : "Building conversion prompt with type-mapping rules and few-shot examples..."
    );
  
    const llm = getLlmAdapter();
    const raw = await llm.complete({
      systemPrompt: SYSTEM_PROMPT,
      userPrompt: buildUserPrompt(schema, feedback),
    });

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    throw new Error(`Convert Agent: LLM did not return valid JSON — ${e.message}`);
  }

  const convertedTables = parsed.converted_tables || [];
  const warnings = parsed.warnings || [];
  const unmappedTypes = parsed.unmapped_types || [];

  emit(
    "convert",
    "success",
    `Converted ${convertedTables.length} table(s). ${warnings.length} warning(s), ${unmappedTypes.length} unmapped type(s).`
  );

  return { convertedTables, warnings, unmappedTypes };
}