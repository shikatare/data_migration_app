import { nanoid } from "nanoid";
import { ChatGroq } from "@langchain/groq";
import { createReactAgent } from "@langchain/langgraph/prebuilt";
import { HumanMessage } from "@langchain/core/messages";
import { createPipelineTools } from "./langchainTools.js";

const SYSTEM_PROMPT = `You are the orchestrator for an Oracle-to-Snowflake migration pipeline.
You have four tools: extract_oracle_schema, convert_to_snowflake_ddl, validate_and_deploy, log_and_notify.

Your job:
1. Call extract_oracle_schema first.
2. Call convert_to_snowflake_ddl to produce Snowflake DDL.
3. Call validate_and_deploy to check it.
4. If validate_and_deploy reports validationPassed: false, do NOT stop — call
   convert_to_snowflake_ddl again, passing the diffIssues/ruleViolations as the
   "feedback" argument so it can fix the specific problems, then call
   validate_and_deploy again. You may retry this loop up to 2 times.
5. Whatever happens — success, repeated validation failure, or any tool error —
   you MUST call log_and_notify exactly once as your final action. Never skip it
   and never call it more than once.
6. After calling log_and_notify, stop and give a short plain-text summary of what
   happened (tables migrated, retries needed, final status).

Do not call deploy logic yourself — validate_and_deploy is the only tool that can
deploy, and it only actually deploys if the run was pre-approved (a factor outside
your control). Your job is sequencing and deciding when to retry, not approving deploys.`;

/**
 * Runs the pipeline as a genuine LangChain/LangGraph agent: the LLM sees
 * each tool's result and decides the next call, including whether to
 * retry Convert with Validate's feedback. Emits the same agent_event
 * socket events as the deterministic orchestrator, so the existing
 * frontend works unchanged against either one.
 */
export async function startAgenticPipelineRun({ schemaName, approved }, io) {
  const runId = `run_${nanoid(10)}`;
  const room = `run:${runId}`;

  const emit = (agent, status, message) => {
    io.to(room).emit("agent_event", {
      runId,
      agent,
      status,
      message,
      timestamp: new Date().toISOString(),
    });
  };

  (async () => {
    try {
      emit("pipeline", "running", "LangChain agent starting — deciding its own sequence of tool calls...");

      const { tools } = createPipelineTools({ runId, schemaName, approved, emit });

      const baseLlm = new ChatGroq({
        apiKey: process.env.GROQ_API_KEY,
        model: "llama-3.3-70b-versatile",
        temperature: 0,
      });

      const llm = baseLlm.bindTools(tools, { parallel_tool_calls: false });

      const agent = createReactAgent({
        llm,
        tools,
        messageModifier: SYSTEM_PROMPT,
      });
      const result = await agent.invoke({
        messages: [new HumanMessage(`Migrate the Oracle schema named ${schemaName} to Snowflake.`)],
      });

      console.log("=== FULL MESSAGE TRACE ===");
      for (const m of result.messages) {
        console.log(`[${m._getType?.() || m.constructor.name}]`, JSON.stringify(m.tool_calls || m.content).slice(0, 300));
      }
      console.log("=== END TRACE ===");

      const lastMessage = result.messages[result.messages.length - 1];
      const summary = typeof lastMessage.content === "string" ? lastMessage.content : JSON.stringify(lastMessage.content);

      io.to(room).emit("run_complete_summary", { runId, summary });
    } catch (err) {
      emit("pipeline", "failed", `Agentic pipeline error: ${err.message}`);
    }
  })();

  return { runId, room };
}