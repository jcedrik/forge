# The three failure demos

A pipeline that only ever passes proves nothing. These three patches each
introduce one realistic mistake and the matching gate refuses it. `make demo`
runs all three locally in about ten seconds; CI runs them on every push as
gate 7, so the pipeline tests its own gates.

| # | Patch | Mistake | Gate | Result |
|---|---|---|---|---|
| 1 | `01-bad-prompt-sink.patch` | user text concatenated into the system prompt, a `sk-proj-...` key committed, the prompt printed to logs | canary | exit 1: `CANARY-PI-001` High, `CANARY-SEC-001` Critical. The build stops before the image exists. |
| 2 | `02-public-bucket.patch` | `BlockPublicAcls: false` on the logs bucket, port 22 opened to 0.0.0.0/0 on the ECS security group | cfn-guard | `s3-block-public` and `sg-no-open-admin` fail. CloudFormation is never called. |
| 3 | `03-attack-simulation.sh` | 6 bad-token requests, 2 prompt injections, 1 oversized request from one client in one minute | triage | 9 alerts become **1 incident at risk 92**, kill chain Credential Access -> Execution -> Impact. Not seven separate pages. |

Recording the 90-second video: run `make demo` in a terminal with a large
font, no narration. Put the link at the top of the README.

Outputs of demo 3 are written here (`alerts.json`, `incident.html`,
`incident.json`, `hunt.kql`) and are gitignored.
