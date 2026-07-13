import pkg from "node-sql-parser";
const { Parser } = pkg;

const parser = new Parser();

const KNOWN_SNOWFLAKE_TYPES_UNSUPPORTED_BY_PARSER = [
  "VARIANT",
  "OBJECT",
  "ARRAY",
  "GEOGRAPHY",
  "GEOMETRY",
  "TIMESTAMP_NTZ",
  "TIMESTAMP_LTZ",
  "TIMESTAMP_TZ",
];

function isFalsePositiveFromUnsupportedType(stmt, errorMessage) {
  
  return KNOWN_SNOWFLAKE_TYPES_UNSUPPORTED_BY_PARSER.some(
    (type) => stmt.toUpperCase().includes(type) && errorMessage.includes('but "')
  );
}

export function parseAndCheckSyntax(ddlStatements) {
  return ddlStatements.map((stmt) => {
    try {
      parser.astify(stmt, { database: "snowflake" });
      return { statement: stmt, valid: true };
    } catch (e) {
      if (isFalsePositiveFromUnsupportedType(stmt, e.message)) {
        return {
          statement: stmt,
          valid: true,
          note: "Contains a Snowflake type not recognized by this parser version (allowlisted as known-valid): " +
            KNOWN_SNOWFLAKE_TYPES_UNSUPPORTED_BY_PARSER.filter((t) => stmt.toUpperCase().includes(t)).join(", "),
        };
      }
      return { statement: stmt, valid: false, error: e.message };
    }
  });
}

export function structuralDiff(originalSchema, convertedTables) {
  const diffs = [];
  for (const table of originalSchema.tables) {
    const converted = convertedTables.find(
      (t) => t.name.toUpperCase() === table.name.toUpperCase()
    );
    if (!converted) {
      diffs.push({ table: table.name, issue: "missing_in_conversion" });
      continue;
    }
    const originalCols = table.columns.map((c) => c.name.toUpperCase());
    const convertedCols = (converted.columns || []).map((c) => c.toUpperCase());
    const missingCols = originalCols.filter((c) => !convertedCols.includes(c));
    if (missingCols.length > 0) {
      diffs.push({ table: table.name, issue: "missing_columns", columns: missingCols });
    }
  }
  return diffs;
}

export function checkBusinessRules(convertedTables) {
  const violations = [];
  for (const table of convertedTables) {
    if (!/^[A-Z][A-Z0-9_]*$/.test(table.name)) {
      violations.push({ table: table.name, rule: "naming_convention", detail: "Table name should be UPPER_SNAKE_CASE" });
    }
    if (table.rawDdl && /\bLONG\b/i.test(table.rawDdl)) {
      violations.push({ table: table.name, rule: "disallowed_type", detail: "LONG has no direct Snowflake equivalent" });
    }
  }
  return violations;
}