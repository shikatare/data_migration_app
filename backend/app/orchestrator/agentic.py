"""Agentic orchestrator.

Runs the pipeline as a genuine LangChain/LangGraph ReAct agent when a Groq key
is present (the LLM decides the tool sequence and when to retry), and as a
deterministic driver over the SAME tools when offline. Emits identical socket
events either way, so the frontend works unchanged against both.
"""
import os
import json
import asyncio
from uuid import uuid4
from datetime import datetime, timezone

from app import config
from app.orchestrator.tools import create_pipeline_tools

SYSTEM_PROMPT = """You are the orchestrator for a MySQL-to-Snowflake migration pipeline.
You have four tools: extract_mysql_schema, convert_to_snowflake_ddl, validate_and_deploy, log_and_notify.

Your job:
1. Call extract_mysql_schema first.
2. Call convert_to_snowflake_ddl to produce Snowflake DDL.
3. Call validate_and_deploy to check it.
4. If validate_and_deploy reports validationPassed: false, do NOT stop — call
   convert_to_snowflake_ddl again, passing the diffIssues/ruleViolations as the
   "feedback" argument, then call validate_and_deploy again. Up to 2 retries.
5. Whatever happens, you MUST call log_and_notify exactly once as your final action.
6. After log_and_notify, stop and give a short plain-text summary.

validate_and_deploy is the only tool that can deploy, and only if the run was pre-approved."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _run_real_agent(tools_list, schema_name):
    from langchain_groq import ChatGroq
    from langgraph.prebuilt import create_react_agent
    llm = ChatGroq(api_key=os.getenv("GROQ_API_KEY"),
                   model="llama-3.3-70b-versatile", temperature=0,
                   model_kwargs={"parallel_tool_calls": False})
    agent = create_react_agent(model=llm, tools=tools_list, prompt=SYSTEM_PROMPT)
    result = agent.invoke({"messages": [
        ("user", f"Migrate the MySQL schema named {schema_name} to Snowflake.")]})
    last = result["messages"][-1]
    return last.content if isinstance(last.content, str) else str(last.content)


def _run_deterministic(by_name):
    by_name["extract"].invoke({})
    by_name["convert"].invoke({})
    validation = json.loads(by_name["validate"].invoke({}))
    attempts = 0
    while not validation["validationPassed"] and attempts < 2:
        attempts += 1
        feedback = json.dumps({"diffIssues": validation["diffIssues"],
                               "ruleViolations": validation["ruleViolations"]})
        by_name["convert"].invoke({"feedback": feedback})
        validation = json.loads(by_name["validate"].invoke({}))
    by_name["log_notify"].invoke({})
    return (f"Deterministic run complete after {attempts} retry attempt(s). Final validation: "
            f"{'passed' if validation['validationPassed'] else 'failed'}, "
            f"deploy: {validation['deployStatus']}.")


def _run_pipeline(schema_name, approved, run_id, emit, emit_event):
    summary = ""
    state = {"logNotifyCalled": False, "record": None}
    try:
        tools_list, by_name, state = create_pipeline_tools(run_id, schema_name, approved, emit, emit_event)
        provider = config.get("LLM_PROVIDER", "groq")
        use_real = provider != "mock" and bool(os.getenv("GROQ_API_KEY"))
        if use_real:
            emit("pipeline", "running",
                 "LangChain agent starting — deciding its own sequence of tool calls...")
            summary = _run_real_agent(tools_list, schema_name)
        else:
            emit("pipeline", "running",
                 "Agentic pipeline starting (offline mode) — running the four LangChain "
                 "agent tools in sequence...")
            summary = _run_deterministic(by_name)
    except Exception as e:
        import traceback
        print("=" * 60)
        print("PIPELINE CRASHED:")
        traceback.print_exc()
        print("=" * 60)
        emit("pipeline", "failed", f"Agentic pipeline error: {e}")
        summary = f"Run stopped with an error: {e}"
    finally:
        if not state.get("logNotifyCalled"):
            emit("log_notify", "failed", "Run could not complete — see pipeline error above.")


async def start_agentic_run(schema_name, approved, sio):
    """Schedule a run; returns immediately with the run id. The blocking
    pipeline executes in a worker thread and streams events back over the loop."""
    run_id = f"run_{uuid4().hex[:10]}"
    room = f"run:{run_id}"
    loop = asyncio.get_running_loop()

    def emit(agent, status, message):
        payload = {"runId": run_id, "agent": agent, "status": status,
                   "message": message, "timestamp": _now()}
        asyncio.run_coroutine_threadsafe(sio.emit("agent_event", payload, room=room), loop)

    def emit_event(name, payload):
        asyncio.run_coroutine_threadsafe(sio.emit(name, payload, room=room), loop)

    loop.run_in_executor(None, _run_pipeline, schema_name, approved, run_id, emit, emit_event)
    return run_id, room