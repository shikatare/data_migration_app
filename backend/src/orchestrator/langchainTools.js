import { tool } from "@langchain/core/tools";
import { z } from "zod";
import { runExtractAgent } from "../agents/extractAgent.js";
import { runConvertAgent } from "../agents/convertAgent.js";
import { runValidateDeployAgent } from "../agents/validateDeployAgent.js";
import { runLogNotifyAgent } from "../agents/logNotifyAgent.js";


export function createPipelineTools({ runId, schemaName, approved, emit }) {
    const state = {
      schemaName,
      schema: null,
      convertedTables: null,
      stageOutcome: {},
      logNotifyCalled: false,
      startedAt: new Date().toISOString(),
    };

  const extractTool = tool(
    async () => {
      const { schema, flags } = await runExtractAgent({ schemaName: state.schemaName, runId, emit });
      state.schema = schema;
      state.stageOutcome.extract = { tableCount: schema.tables.length, flagCount: flags.length, flags };
      return JSON.stringify({
        tableCount: schema.tables.length,
        tables: schema.tables.map((t) => t.name),
        flags,
      });
    },
    {
      name: "extract_oracle_schema",
      description:
        "Extracts the Oracle schema definition (tables, columns, DDL). Must be called first, before convert or validate.",
      schema: z.object({}),
    }
  );

  const convertTool = tool(
    async ({ feedback }) => {
      if (!state.schema) {
        return "ERROR: schema not extracted yet. Call extract_oracle_schema first.";
      }
      const { convertedTables, warnings, unmappedTypes } = await runConvertAgent({
        schema: state.schema,
        runId,
        emit,
        feedback,
      });
      state.convertedTables = convertedTables;
      state.stageOutcome.convert = {
        tableCount: convertedTables.length,
        warningCount: warnings.length,
        warnings,
        unmappedTypes,
        convertedTables,
      };
      return JSON.stringify({
        tableCount: convertedTables.length,
        warnings,
        unmappedTypes,
      });
    },
    {
      name: "convert_to_snowflake_ddl",
      description:
        "Converts the extracted Oracle DDL to Snowflake DDL using an LLM. Requires extract_oracle_schema to have run first. " +
        "If a previous validate_and_deploy call failed, pass its issues as `feedback` to fix them on this attempt.",
      schema: z.object({
        feedback: z.string().optional().describe("Specific validation issues to fix, from a prior failed validate_and_deploy call."),
      }),
    }
  );

  const validateTool = tool(
    async () => {
      if (!state.convertedTables) {
        return "ERROR: no converted DDL yet. Call convert_to_snowflake_ddl first.";
      }
      if (process.env.FORCE_VALIDATION_FAIL_ONCE === "true" && !state.forcedFailureUsed) {
        state.forcedFailureUsed = true;
        return JSON.stringify({
          validationPassed: false,
          syntaxErrorCount: 0,
          diffIssues: [{ table: "CUSTOMERS", issue: "missing_columns", columns: ["LOYALTY_TIER"] }],
          ruleViolations: [],
          deployStatus: "not_attempted",
        });
      }

      const result = await runValidateDeployAgent({
        schema: state.schema,
        convertedTables: state.convertedTables,
        runId,
        approved,
        emit,
      });
      state.stageOutcome.validateDeploy = result;
      return JSON.stringify({
        validationPassed: result.validationPassed,
        syntaxErrorCount: result.syntaxErrors?.length || 0,
        diffIssues: result.diffIssues,
        ruleViolations: result.ruleViolations,
        deployStatus: result.deployStatus,
      });
    },
    {
      name: "validate_and_deploy",
      description:
        "Validates the converted DDL (syntax, structural diff vs original schema, business rules). " +
        "If validation fails, do NOT give up immediately — call convert_to_snowflake_ddl again with the " +
        "diffIssues/ruleViolations as feedback, then validate again. Only deploys to Snowflake if validation " +
        "passes AND the run was pre-approved by the user (outside your control).",
      schema: z.object({}),
    }
  );

  const logNotifyTool = tool(
    async () => {
      if (state.logNotifyCalled) {
        return "ERROR: log_and_notify was already called for this run. Do not call it again — you're done, stop here.";
      }
      const { record } = await runLogNotifyAgent({
        runId,
        schemaName: state.schemaName,
        startedAt: state.startedAt || new Date().toISOString(),
        stageOutcome: state.stageOutcome,
        emit,
      });
      state.logNotifyCalled = true;
      return JSON.stringify({ overallStatus: record.overallStatus });
    },
    {
      name: "log_and_notify",
      description:
        "Records the run outcome and sends notifications. MUST be called exactly once, as the final action, " +
        "no matter how the run went — including if extraction, conversion, or validation failed or you gave up retrying.",
      schema: z.object({}),
    }
  );

  return { tools: [extractTool, convertTool, validateTool, logNotifyTool], state };
}