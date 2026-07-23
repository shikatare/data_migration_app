
import os
import json
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from app.agents.extract import run_extract_agent
from app.agents.convert import run_convert_agent
from app.agents.validate_deploy import run_validate_deploy_agent
from app.agents.log_notify import run_log_notify_agent
from app.pipelines import get_pipeline


class _NoArgs(BaseModel):
    pass


class _ConvertArgs(BaseModel):
    feedback: Optional[str] = Field(
        default=None,
        description="Specific validation issues to fix, from a prior failed validate_and_deploy call.",
    )


def create_pipeline_tools(run_id, schema_name, pipeline, approved, emit, emit_event=None):
    p = get_pipeline(pipeline)
    extract_tool_name = f"extract_{p['sourceLabel'].lower()}_schema"
    convert_tool_name = f"convert_to_{p['targetLabel'].lower()}_ddl"

    state = {
        "schemaName": schema_name, "pipeline": pipeline, "schema": None, "convertedTables": None,
        "stageOutcome": {}, "logNotifyCalled": False, "record": None,
        "forcedFailureUsed": False,
        "startedAt": datetime.now(timezone.utc).isoformat(),
    }

    def _extract() -> str:
        out = run_extract_agent(state["schemaName"], pipeline, emit)
        state["schema"] = out["schema"]
        state["stageOutcome"]["extract"] = {
            "tableCount": len(out["schema"]["tables"]),
            "flagCount": len(out["flags"]), "flags": out["flags"],
        }
        return json.dumps({"tableCount": len(out["schema"]["tables"]),
                           "tables": [t["name"] for t in out["schema"]["tables"]],
                           "flags": out["flags"]})

    def _convert(feedback: Optional[str] = None) -> str:
        if not state["schema"]:
            return f"ERROR: schema not extracted yet. Call {extract_tool_name} first."
        out = run_convert_agent(state["schema"], pipeline, emit, feedback)
        state["convertedTables"] = out["convertedTables"]
        state["stageOutcome"]["convert"] = {
            "tableCount": len(out["convertedTables"]),
            "warningCount": len(out["warnings"]), "warnings": out["warnings"],
            "unmappedTypes": out["unmappedTypes"], "convertedTables": out["convertedTables"],
        }
        return json.dumps({"tableCount": len(out["convertedTables"]),
                           "warnings": out["warnings"], "unmappedTypes": out["unmappedTypes"]})

    def _validate() -> str:
        if not state["convertedTables"]:
            return f"ERROR: no converted DDL yet. Call {convert_tool_name} first."
        if os.getenv("FORCE_VALIDATION_FAIL_ONCE") == "true" and not state["forcedFailureUsed"]:
            state["forcedFailureUsed"] = True
            return json.dumps({"validationPassed": False, "syntaxErrorCount": 0,
                               "diffIssues": [{"table": "CUSTOMERS", "issue": "missing_columns",
                                               "columns": ["LOYALTY_TIER"]}],
                               "ruleViolations": [], "deployStatus": "not_attempted"})
        result = run_validate_deploy_agent(state["schema"], state["convertedTables"],
                                           pipeline, run_id, approved, emit)
        state["stageOutcome"]["validateDeploy"] = result
        return json.dumps({"validationPassed": result["validationPassed"],
                           "syntaxErrorCount": len(result.get("syntaxErrors", [])),
                           "diffIssues": result["diffIssues"],
                           "ruleViolations": result["ruleViolations"],
                           "deployStatus": result["deployStatus"]})

    def _log_notify_impl() -> str:
        out = run_log_notify_agent(run_id, state["schemaName"], pipeline, state["startedAt"],
                                   state["stageOutcome"], emit)
        state["logNotifyCalled"] = True
        state["record"] = out["record"]
        if emit_event:
            emit_event("run_complete", out["record"])
        return json.dumps({"overallStatus": out["record"]["overallStatus"]})

    def _log_notify() -> str:
        if state["logNotifyCalled"]:
            return "ERROR: log_and_notify was already called. You're done, stop here."
        if state["schema"] is not None and not state["stageOutcome"].get("validateDeploy"):
            return ("ERROR: You have not completed validate_and_deploy yet. Call "
                    f"{convert_tool_name} (if not already done) and then "
                    "validate_and_deploy before calling log_and_notify.")
        return _log_notify_impl()

    extract_tool = StructuredTool.from_function(
        func=_extract, name=extract_tool_name, args_schema=_NoArgs,
        description=f"Extracts the {p['sourceLabel']} schema (tables, columns, DDL). Must be called first.")
    convert_tool = StructuredTool.from_function(
        func=_convert, name=convert_tool_name, args_schema=_ConvertArgs,
        description=(f"Converts extracted {p['sourceLabel']} DDL to {p['targetLabel']} DDL via an LLM. "
                     "If a prior validate_and_deploy failed, pass its issues as `feedback`."))
    validate_tool = StructuredTool.from_function(
        func=_validate, name="validate_and_deploy", args_schema=_NoArgs,
        description=("Validates converted DDL (syntax, structural diff, business rules) and "
                     "computes a confidence score. If validation fails, call convert again with "
                     "the issues as feedback, then validate again. Deploys only if validation "
                     "passes AND the run was pre-approved."))
    log_tool = StructuredTool.from_function(
        func=_log_notify, name="log_and_notify", args_schema=_NoArgs,
        description=("Records the run outcome and notifies. MUST be called exactly once as the "
                     "final action, no matter how the run went."))

    tools_list = [extract_tool, convert_tool, validate_tool, log_tool]
    by_name = {"extract": extract_tool, "convert": convert_tool,
               "validate": validate_tool, "log_notify": log_tool,
               "log_notify_raw": _log_notify_impl}
    return tools_list, by_name, state