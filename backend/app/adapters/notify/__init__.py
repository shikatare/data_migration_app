"""Notification fan-out — console always; Slack / SNS when configured."""
import os
import json
import urllib.request
from app import config


def _console(summary: dict) -> dict:
    print(f"[NOTIFY] {summary['status'].upper()} — run {summary['runId']}: {summary['message']}")
    return {"channel": "console", "ok": True}


def _slack(summary: dict) -> dict:
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook:
        return {"channel": "slack", "ok": False, "error": "SLACK_WEBHOOK_URL not set"}
    try:
        body = json.dumps({"text": f"*Migration run {summary['runId']}* — "
                                   f"{summary['status'].upper()}\n{summary['message']}"}).encode()
        req = urllib.request.Request(webhook, data=body,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        return {"channel": "slack", "ok": True}
    except Exception as e:
        return {"channel": "slack", "ok": False, "error": str(e)}


def publish_notification(summary: dict) -> list:
    mode = config.get("NOTIFY_MODE", "console")
    results = [_console(summary)]
    if mode == "slack":
        results.append(_slack(summary))
    return results