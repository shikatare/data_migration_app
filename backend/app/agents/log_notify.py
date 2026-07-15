"""Log & Notify Agent — always runs; writes one audit record and notifies."""
from datetime import datetime, timezone
from app.adapters import storage, notify


def _overall_status(stage: dict) -> str:
    vd = stage.get("validateDeploy")
    if vd:
        if vd.get("deployStatus") == "success":
            return "success"
        if vd.get("deployStatus") == "awaiting_approval":
            return "awaiting_approval"
        if not vd.get("validationPassed"):
            return "validation_failed"
        if vd.get("deployStatus") == "failed":
            return "deploy_failed"
    if stage.get("error"):
        return "error"
    return "partial"


def _summarize(record: dict) -> str:
    parts = [f"Schema: {record['schemaName']}", f"Status: {record['overallStatus']}"]
    if record.get("extract"):
        parts.append(f"Extracted {record['extract']['tableCount']} table(s), "
                     f"{record['extract']['flagCount']} flagged")
    if record.get("convert"):
        parts.append(f"Converted {record['convert']['tableCount']} table(s), "
                     f"{record['convert']['warningCount']} warning(s)")
    if record.get("validateDeploy"):
        parts.append(f"Deploy: {record['validateDeploy']['deployStatus']}")
    if record.get("confidence") is not None:
        parts.append(f"Confidence: {int(record['confidence'] * 100)}%")
    return " | ".join(parts)


def run_log_notify_agent(run_id, schema_name, started_at, stage_outcome, emit) -> dict:
    emit("log_notify", "running", "Recording run metadata and publishing summary...")
    vd = stage_outcome.get("validateDeploy") or {}
    scoring = vd.get("scoring") or {}
    record = {
        "runId": run_id,
        "schemaName": schema_name,
        "startedAt": started_at,
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "overallStatus": _overall_status(stage_outcome),
        "confidence": scoring.get("overallConfidence"),
        "extract": stage_outcome.get("extract"),
        "convert": stage_outcome.get("convert"),
        "validateDeploy": vd or None,
    }

    storage_ok = True
    try:
        storage.put_run_record(record)
    except Exception as e:
        storage_ok = False
        emit("log_notify", "running", f"Warning: failed to write run record — {e}")

    results = notify.publish_notification(
        {"runId": run_id, "status": record["overallStatus"], "message": _summarize(record)})
    emit("log_notify", "success",
         f"Run recorded (storage {'ok' if storage_ok else 'failed'}). "
         f"Notified via: {', '.join(r['channel'] for r in results)}.")
    return {"record": record, "notifyResults": results}