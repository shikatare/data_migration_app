import * as mock from "./mockOracleAdapter.js";
import * as real from "./realOracleAdapter.js";

export function getOracleAdapter() {
  const mode = process.env.ORACLE_MODE || "mock";
  return mode === "real" ? real : mock;
}
