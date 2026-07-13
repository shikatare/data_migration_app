import { nanoid } from "nanoid";
import { runExtractAgent } from "../agents/extractAgent.js";
import { runConvertAgent } from "../agents/convertAgent.js";
import { runValidateDeployAgent } from "../agents/validateDeployAgent.js";
import { runLogNotifyAgent } from "../agents/logNotifyAgent.js";

/**
 * Orchestrator — sequences the four agents. A failure at Extract,
 * Convert, or Validate/Deploy still routes directly to Log & Notify —
 * every run is recorded no matter where it stops.
 *
 * `io` is a socket.io server; each run streams events on room `run:<runId>`.
 */
export async function startPipelineRun({ schemaName, approved }, io) {
  const runId = `run_${nanoid(10)}`;
  const startedAt = new Date().toISOString();
  const room = `run:${runId}`;

  const emit = (agent, status, message) => {
    io.to(room).emit("agent_event", {
      runId,
      agent,
      status, // running | success | failed | waiting
      message,
      timestamp: new Date().toISOString(),
    });
  };

  // Run asynchronously; caller gets runId immediately to subscribe to the room.
  (async () => {
    const stageOutcome = {};
    try {
      const { schema, flags } = await runExtractAgent({ schemaName, runId, emit });
      stageOutcome.extract = { tableCount: schema.tables.length, flagCount: flags.length, flags };

      const { convertedTables, warnings, unmappedTypes } = await runConvertAgent({ schema, runId, emit });
      stageOutcome.convert = {
        tableCount: convertedTables.length,
        warningCount: warnings.length,
        warnings,
        unmappedTypes,
        convertedTables,
      };

      const validateResult = await runValidateDeployAgent({
        schema,
        convertedTables,
        runId,
        approved,
        emit,
      });
      stageOutcome.validateDeploy = validateResult;
    } catch (err) {
      stageOutcome.error = err.message;
      emit("pipeline", "failed", `Pipeline error: ${err.message}`);
    } finally {
      // Log & Notify always runs, whatever stage was reached.
      const { record } = await runLogNotifyAgent({
        runId,
        schemaName,
        startedAt,
        stageOutcome,
        emit,
      });
      io.to(room).emit("run_complete", record);
    }
  })();

  return { runId, room };
}