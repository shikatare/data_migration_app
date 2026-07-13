import * as mock from "./mockSnowflakeAdapter.js";
import * as real from "./realSnowflakeAdapter.js";

export function getSnowflakeAdapter() {
  const mode = process.env.SNOWFLAKE_MODE || "mock";
  return mode === "real" ? real : mock;
}
