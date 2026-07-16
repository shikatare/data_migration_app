
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
_pending_runs = {}


def _columns_from_ddl(ddl):
    
    import sqlglot
    try:
        parsed = sqlglot.parse_one(ddl, read="snowflake")
        return [c.name.upper() for c in parsed.find_all(sqlglot.exp.ColumnDef)]
    except Exception:
        return None  # malformed edit — let syntax validation catch it downstream


def _run_review_phase1(schema_name, run_id, emit, emit_event):
    from app.agents.extract import run_extract_agent
    from app.agents.convert import run_convert_agent

    started_at = _now()
    state = {"schemaName": schema_name, "startedAt": started_at, "stageOutcome": {}}
    try:
        emit("pipeline", "running", "Review mode — running Extract and Convert, then pausing for your review...")
        extract_out = run_extract_agent(schema_name, emit)
        state["schema"] = extract_out["schema"]
        state["stageOutcome"]["extract"] = {
            "tableCount": len(extract_out["schema"]["tables"]),
            "flagCount": len(extract_out["flags"]), "flags": extract_out["flags"],
        }

        convert_out = run_convert_agent(state["schema"], emit)
        state["convertedTables"] = convert_out["convertedTables"]
        state["stageOutcome"]["convert"] = {
            "tableCount": len(convert_out["convertedTables"]),
            "warningCount": len(convert_out["warnings"]), "warnings": convert_out["warnings"],
            "unmappedTypes": convert_out["unmappedTypes"], "convertedTables": convert_out["convertedTables"],
        }

        _pending_runs[run_id] = state
        emit("convert", "success", f"Converted {len(convert_out['convertedTables'])} table(s). Paused for review.")
        emit_event("awaiting_review", {
            "runId": run_id,
            "convertedTables": convert_out["convertedTables"],
            "warnings": convert_out["warnings"],
            "unmappedTypes": convert_out["unmappedTypes"],
        })
    except Exception as e:
        emit("pipeline", "failed", f"Review-mode pipeline error before pause: {e}")
        emit_event("run_complete_summary", {"runId": run_id, "summary": f"Run stopped with an error: {e}"})


def _run_review_phase2(run_id, approved, edited_tables, emit, emit_event):
    from app.agents.validate_deploy import run_validate_deploy_agent
    from app.agents.log_notify import run_log_notify_agent

    state = _pending_runs.pop(run_id, None)
    if state is None:
        emit("pipeline", "failed", "No paused run found for this ID — it may have already been resumed or expired.")
        return

    if edited_tables:
        by_name = {t["name"]: t for t in edited_tables}
        for t in state["convertedTables"]:
            if t["name"] in by_name:
                new_ddl = by_name[t["name"]]["ddl"]
                t["ddl"] = new_ddl
                real_cols = _columns_from_ddl(new_ddl)
                if real_cols is not None:
                    t["columns"] = real_cols
        emit("convert", "success", f"Applied manual edits to {len(edited_tables)} table(s) before validating.")

    result = run_validate_deploy_agent(state["schema"], state["convertedTables"], run_id, approved, emit)
    state["stageOutcome"]["validateDeploy"] = result

    if not result["validationPassed"]:
        _pending_runs[run_id] = state
        emit_event("awaiting_review", {
            "runId": run_id,
            "convertedTables": state["convertedTables"],
            "warnings": [],
            "unmappedTypes": [],
            "validationFailed": True,
            "diffIssues": result["diffIssues"],
            "ruleViolations": result["ruleViolations"],
            "syntaxErrors": result.get("syntaxErrors", []),
        })
        return

    out = run_log_notify_agent(run_id, state["schemaName"], state["startedAt"], state["stageOutcome"], emit)
    emit_event("run_complete", out["record"])
    emit_event("run_complete_summary", {
        "runId": run_id,
        "summary": f"Review-mode run complete. Deploy: {result['deployStatus']}.",
    })


async def start_review_run(schema_name, sio):

    run_id = f"run_{uuid4().hex[:10]}"
    room = f"run:{run_id}"
    loop = asyncio.get_running_loop()

    def emit(agent, status, message):
        payload = {"runId": run_id, "agent": agent, "status": status,
                   "message": message, "timestamp": _now()}
        asyncio.run_coroutine_threadsafe(sio.emit("agent_event", payload, room=room), loop)

    def emit_event(name, payload):
        asyncio.run_coroutine_threadsafe(sio.emit(name, payload, room=room), loop)

    loop.run_in_executor(None, _run_review_phase1, schema_name, run_id, emit, emit_event)
    return run_id, room


async def continue_review_run(run_id, approved, edited_tables, sio):

    room = f"run:{run_id}"
    loop = asyncio.get_running_loop()

    def emit(agent, status, message):
        payload = {"runId": run_id, "agent": agent, "status": status,
                   "message": message, "timestamp": _now()}
        asyncio.run_coroutine_threadsafe(sio.emit("agent_event", payload, room=room), loop)

    def emit_event(name, payload):
        asyncio.run_coroutine_threadsafe(sio.emit(name, payload, room=room), loop)

    loop.run_in_executor(None, _run_review_phase2, run_id, approved, edited_tables, emit, emit_event)
    return {"runId": run_id, "room": room}