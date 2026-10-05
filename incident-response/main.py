import json
import os
import shlex
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException


app = FastAPI(title="Order Tracker Incident Responder")

WORKSPACE = Path(os.getenv("AGENT_WORKSPACE", "/workspace")).resolve()
ALERT_STORAGE_PATH = Path(
    os.getenv("ALERT_STORAGE_PATH", str(Path(__file__).parent / "alerts"))
)
AGENT_TIMEOUT_SECONDS = int(os.getenv("AGENT_TIMEOUT_SECONDS", "300"))
CODING_AGENT_COMMAND = os.getenv(
    "CODING_AGENT_COMMAND", "claude -p --dangerously-skip-permissions"
)
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://app:8000")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def alert_endpoint(alert: dict[str, Any]) -> str | None:
    labels = alert.get("labels", {})
    return labels.get("endpoint") or labels.get("http_route") or labels.get("route")


def build_agent_prompt(record: dict[str, Any]) -> str:
    return f"""You are the incident-response coding agent for the order-tracker repository.

Work in {WORKSPACE}. The application is reachable at {APP_BASE_URL}.

An alert webhook was received. Investigate it end to end:
1. Read the alert details below.
2. Inspect the relevant source, tests, and available Docker Compose logs.
3. Reproduce the issue with focused tests or requests where possible.
4. If there is a real bug, make the smallest correct fix, run the relevant tests, and commit the fix with a clear message.
5. If it is a false positive or cannot be reproduced, explain the evidence and do not change code.
6. Never commit secrets or unrelated changes.

Alert record:
{json.dumps(record, indent=2, sort_keys=True)}

At the end, give a concise conclusion whose final line is exactly one useful sentence describing the result: fixed and committed, false positive, or unable to reproduce.
"""


def persist_record(record: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def run_coding_agent(record: dict[str, Any]) -> tuple[str, str, str | None]:
    command = shlex.split(CODING_AGENT_COMMAND)
    if not command:
        return (
            "unavailable",
            "No coding agent command was configured.",
            "No coding agent command was configured.",
        )

    try:
        result = subprocess.run(
            command,
            cwd=WORKSPACE,
            input=build_agent_prompt(record),
            text=True,
            capture_output=True,
            timeout=AGENT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        message = (
            "No coding agent executable was available; configure "
            "CODING_AGENT_COMMAND or install Claude Code."
        )
        return "unavailable", message, message
    except subprocess.TimeoutExpired:
        message = f"Coding agent timed out after {AGENT_TIMEOUT_SECONDS} seconds."
        return "timeout", message, message

    output = (result.stdout or result.stderr).strip()
    if not output:
        output = f"Coding agent exited with status {result.returncode}."
    last_line = output.splitlines()[-1]
    status = "completed" if result.returncode == 0 else "failed"
    return status, output, last_line


@app.post("/alerts", status_code=202)
def receive_alert(payload: dict[str, Any]):
    alerts = payload.get("alerts")
    if not isinstance(alerts, list) or not alerts:
        raise HTTPException(status_code=400, detail="Grafana payload must contain alerts")

    received_at = utc_now()
    alert_id = uuid.uuid4().hex
    record = {
        "id": alert_id,
        "received_at": received_at,
        "alert_count": len(alerts),
        "alerts": alerts,
        "endpoints": sorted(
            endpoint for endpoint in (alert_endpoint(alert) for alert in alerts) if endpoint
        ),
    }

    ALERT_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    record_path = ALERT_STORAGE_PATH / f"{received_at.replace(':', '').replace('+00:00', 'Z')}-{alert_id}.json"
    record["record_path"] = str(record_path)
    persist_record({**record, "agent_status": "starting"}, record_path)

    agent_status, agent_output, agent_last_line = run_coding_agent(record)
    record.update(
        {
            "agent_status": agent_status,
            "agent_response": agent_output,
            "agent_last_line": agent_last_line,
            "completed_at": utc_now(),
        }
    )
    persist_record(record, record_path)
    return record
