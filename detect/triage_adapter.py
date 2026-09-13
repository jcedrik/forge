#!/usr/bin/env python3
"""Turn api-llm security events into triage alerts.

Input: the JSON lines the app writes (app/events.py), either from a local
file, from stdin, or pulled from CloudWatch Logs with --log-group.
Output: triage's native JSON alert list, which `triage` then correlates,
scores and maps onto ATT&CK.

    python detect/triage_adapter.py events.jsonl > alerts.json
    triage alerts.json --pivot-src-ip --html incident.html --kql hunt.kql

    # straight from AWS, last 30 minutes
    python detect/triage_adapter.py --log-group /forge/api-llm --minutes 30 > alerts.json

Mapping decisions, so they are explicit:
  host       the service name (api-llm); every task is one logical host
  src_ip     the client ip part of client_id ("ip:tokenprefix")
  signature  the event name, prefixed so it reads well in a dashboard
  severity   from the event (app/events.py SEVERITY)
  technique  from the event (app/events.py TECHNIQUE)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Iterable

SIGNATURE = {
    "auth.failure": "api-llm: authentication failure",
    "ratelimit.exceeded": "api-llm: rate limit exceeded",
    "prompt.injection_detected": "api-llm: prompt injection attempt",
    "output.pii_redacted": "api-llm: PII redacted from model output",
    "input.oversize": "api-llm: oversized request",
    "input.invalid": "api-llm: malformed request",
    "db.query_error": "api-llm: database error",
    "model.error": "api-llm: model error",
}


def to_alert(ev: dict) -> dict | None:
    name = ev.get("event")
    if name not in SIGNATURE:
        return None
    client = ev.get("client_id", "")
    src_ip = client.split(":", 1)[0] if client else ""
    return {
        "timestamp": ev["ts"].replace("Z", ""),
        "host": ev.get("service", "api-llm"),
        "signature": SIGNATURE[name],
        "severity": ev.get("severity", "info"),
        "technique_id": ev.get("technique_id", ""),
        "category": name.split(".")[0],
        "src_ip": src_ip,
        "dst_ip": "",
        "raw": json.dumps(ev, separators=(",", ":"))[:500],
    }


def read_lines(lines: Iterable[str]) -> list[dict]:
    out = []
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        a = to_alert(ev)
        if a:
            out.append(a)
    return out


def read_cloudwatch(log_group: str, minutes: int, region: str | None) -> list[dict]:
    import boto3  # only needed for this path

    logs = boto3.client("logs", region_name=region)
    start = int((time.time() - minutes * 60) * 1000)
    paginator = logs.get_paginator("filter_log_events")
    raw = []
    for page in paginator.paginate(logGroupName=log_group, startTime=start, filterPattern='{ $.event = * }'):
        raw.extend(e["message"] for e in page.get("events", []))
    return read_lines(raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="events.jsonl (default: stdin)")
    ap.add_argument("--log-group", help="pull from CloudWatch Logs instead of a file")
    ap.add_argument("--minutes", type=int, default=30)
    ap.add_argument("--region", default=None)
    a = ap.parse_args()

    if a.log_group:
        alerts = read_cloudwatch(a.log_group, a.minutes, a.region)
    elif a.file:
        with open(a.file, encoding="utf-8") as fh:
            alerts = read_lines(fh)
    else:
        alerts = read_lines(sys.stdin)
    json.dump(alerts, sys.stdout, indent=1)
    print(file=sys.stdout)
    print(f"triage_adapter: {len(alerts)} alerts", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
