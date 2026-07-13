import express from "express";
import { startPipelineRun } from "../orchestrator/pipeline.js";
import { startAgenticPipelineRun } from "../orchestrator/langchainOrchestrator.js";
import { getOracleAdapter } from "../adapters/oracle/index.js";
import { getRunHistory } from "../adapters/storage/index.js";

export function pipelineRouter(io) {
  const router = express.Router();

  // List available mock Oracle schemas the user can pick from.
  router.get("/schemas", async (req, res) => {
    try {
      const adapter = getOracleAdapter();
      const schemas = (await adapter.listAvailableSchemas?.()) || [];
      res.json({ schemas });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // Kick off a new pipeline run. approved:false stops before deploy.
  router.post("/runs", async (req, res) => {
    try {
      const { schemaName, approved } = req.body;
      if (!schemaName) return res.status(400).json({ error: "schemaName is required" });

      const { runId, room } = await startPipelineRun({ schemaName, approved: !!approved }, io);
      res.json({ runId, room });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });
  router.post("/agentic-runs", async (req, res) => {
    try {
      const { schemaName, approved } = req.body;
      if (!schemaName) return res.status(400).json({ error: "schemaName is required" });

      const { runId, room } = await startAgenticPipelineRun({ schemaName, approved: !!approved }, io);
      res.json({ runId, room });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // Approve a previously-validated run to proceed to deploy.
  router.post("/runs/:schemaName/approve", async (req, res) => {
    try {
      const { schemaName } = req.params;
      const { runId, room } = await startPipelineRun({ schemaName, approved: true }, io);
      res.json({ runId, room });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  router.get("/runs", async (req, res) => {
    try {
      const runs = await getRunHistory();
      res.json({ runs });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  router.get("/config", (req, res) => {
    res.json({
      oracleMode: process.env.ORACLE_MODE || "mock",
      snowflakeMode: process.env.SNOWFLAKE_MODE || "mock",
      llmProvider: process.env.LLM_PROVIDER || "groq",
      secretsMode: process.env.SECRETS_MODE || "env",
      storageMode: process.env.STORAGE_MODE || "local",
      notifyMode: process.env.NOTIFY_MODE || "console",
    });
  });

  return router;
}