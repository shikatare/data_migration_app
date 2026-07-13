import * as groq from "./groqAdapter.js";
import * as cortex from "./cortexAdapter.js";

export function getLlmAdapter() {
  const provider = process.env.LLM_PROVIDER || "groq";
  return provider === "cortex" ? cortex : groq;
}
