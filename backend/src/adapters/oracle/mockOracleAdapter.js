import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SAMPLES_DIR = path.join(__dirname, "../../data/sampleSchemas");

/**
 * Mock Oracle Adapter — stands in for a live Oracle connection.
 * Reads a sample schema bundled with the repo instead of hitting
 * a real Oracle instance.
 */
export async function extractSchema({ schemaName }) {
  const file = path.join(SAMPLES_DIR, `${schemaName}.json`);
  const raw = await fs.readFile(file, "utf-8");
  return JSON.parse(raw);
}

export async function listAvailableSchemas() {
  const files = await fs.readdir(SAMPLES_DIR);
  return files.filter((f) => f.endsWith(".json")).map((f) => f.replace(".json", ""));
}
