"""Structured security events.

One JSON object per line on stdout, which is what the ECS awslogs driver
ships to CloudWatch Logs. The detection layer (detect/triage_adapter.py)
reads these back and feeds them to triage. The field names are fixed and
documented in docs/events.md; changing one here means changing the adapter.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

SEVERITY = {
    "auth.failure": "medium",
    "ratelimit.exceeded": "low",
    "prompt.injection_detected": "high",
    "output.pii_redacted": "medium",
    "input.oversize": "low",
    "input.invalid": "low",
    "db.query_error": "medium",
    "model.error": "medium",
}

# MITRE ATT&CK technique each event is evidence of, so triage can place it
# on the kill chain without a lookup table of its own.
TECHNIQUE = {
    "auth.failure": "T1110",            # brute force
    "ratelimit.exceeded": "T1498",      # (abuse / DoS)
    "prompt.injection_detected": "T1059",  # execution via instruction
    "output.pii_redacted": "T1041",     # exfiltration attempt
    "input.oversize": "T1499",          # resource exhaustion
    "db.query_error": "T1190",          # exploit attempt against the app
}


def emit(event: str, client_id: str, request_id: str, **fields: Any) -> dict:
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "severity": SEVERITY.get(event, "info"),
        "technique_id": TECHNIQUE.get(event, ""),
        "client_id": client_id,
        "request_id": request_id,
        "service": "api-llm",
        **fields,
    }
    # Never log the prompt itself. Guardrail detail is a short pattern match,
    # not user content; canary's PII rule is wired into CI to keep it that way.
    sys.stdout.write(json.dumps(record, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return record
