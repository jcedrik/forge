# Security events

One JSON object per line on stdout, shipped by the ECS awslogs driver to
`/forge/api-llm`. These are the contract between the app and the detection
layer (`detect/triage_adapter.py`) and the metric filters in `03-audit.yaml`.

| Event | Trigger | Severity | ATT&CK | Alarm |
|---|---|---|---|---|
| `auth.failure` | missing or wrong bearer token | medium | T1110 | > 20 in 5 min |
| `ratelimit.exceeded` | more than `RATE_LIMIT` requests per minute per client | low | T1498 | |
| `prompt.injection_detected` | input guardrail matched an override / leak pattern | high | T1059 | >= 5 in 5 min |
| `output.pii_redacted` | output guardrail redacted email, phone, SIN, card or key | medium | T1041 | |
| `input.oversize` | prompt over 4,000 characters | low | T1499 | |
| `input.invalid` | empty or non-string prompt | low | | |
| `db.query_error` | metadata insert failed | medium | T1190 | |
| `model.error` | model provider raised | medium | | |

Fields on every event:

```json
{"ts":"2026-10-11T02:07:14Z","event":"prompt.injection_detected","severity":"high",
 "technique_id":"T1059","client_id":"203.0.113.9:demo-tok","request_id":"3f9a1c2b7d0e",
 "service":"api-llm","detail":"ignore all previous instructions"}
```

`client_id` is `ip:first-8-chars-of-token`, which is enough to correlate a
client without storing the token. `detail` is the matched pattern (at most
60 characters), never the prompt. The prompt and the answer are never logged
and never stored; `app/db.py` keeps request id, client id, timestamp,
outcome and latency only.
