# Compliance matrix

What each gate refuses, and which control that refusal implements. The point
of the table is that every "no" the pipeline says can be traced to a named
requirement, which is what an auditor, or an AWS ProServe interviewer, asks
for.

## The eight cfn-guard rules (`infra/guard-rules/`)

| Rule | Refuses | PCI DSS v4 | NIST 800-53 r5 | ISO 27001:2022 | HIPAA |
|---|---|---|---|---|---|
| `s3-block-public` | A bucket with any of the four public-access flags off | 1.3 | AC-3 | A.8.20 | |
| `s3-encryption` | A bucket not defaulting to SSE-KMS with a customer key | 3.5 | SC-28 | A.8.24 | 164.312(a)(2)(iv) |
| `rds-encrypted` | A database with `StorageEncrypted` false or no KMS key | 3.5 | SC-28 | A.8.24 | 164.312(a)(2)(iv) |
| `rds-not-public` | A database with `PubliclyAccessible` true | 1.3 | SC-7 | A.8.20 | 164.312(e)(1) |
| `sg-no-open-admin` | A security group opening 22, 3389 or all traffic to 0.0.0.0/0 | 1.2, 1.3 | SC-7 | A.8.20 | |
| `iam-no-wildcard` | An Allow statement with `Action: "*"` | 7.2 | AC-6 | A.5.15, A.8.2 | 164.312(a)(1) |
| `ecs-no-root` | A container without a non-root user, a read-only root fs, or marked privileged | 2.2 | CM-7 | A.8.9 | |
| `cloudtrail-validation` | A trail without log file validation, not multi-region, or unencrypted | 10.3, 10.5 | AU-9, AU-12 | A.8.15 | 164.312(b) |

Companion rules in the same files (not counted in the eight): `rds-password-from-secrets-manager`, `iam-no-admin-managed-policy`, `ecs-no-public-ip`.

## The application gate (canary)

| canary rule | Refuses | OWASP LLM Top 10 | CWE | NIST 800-53 |
|---|---|---|---|---|
| `CANARY-PI-001` | User input interpolated into a prompt | LLM01 | CWE-94 | SI-10 |
| `CANARY-EA-001` | An agent tool that hands model arguments to a shell | LLM06 | CWE-78 | AC-6, SI-10 |
| `CANARY-SEC-001..005` | A credential committed in source | LLM02 | CWE-798 | IA-5 |
| `CANARY-PII-001` | Personal data written to logs | LLM02 | CWE-532 | AU-3, SI-12 |
| `CANARY-GR-001` | Model output used with no validation (advisory) | LLM05 | CWE-20 | SI-10 |

## Runtime controls (what the templates deploy)

| Control | Where | Requirement |
|---|---|---|
| TLS 1.2+ only at the edge, no port 80 | `02-compute` ALB listener, `00-network` ALB SG | PCI DSS 4.2, NIST SC-8 |
| Private subnets with no internet route; VPC endpoints instead of NAT | `00-network` | NIST SC-7(5) |
| ECS tasks: no public IP, capabilities dropped, init process | `02-compute` task definition and service | NIST CM-7, AC-6 |
| Secrets in Secrets Manager, injected at task start, never in templates | `01-data`, `02-compute` | PCI DSS 8.6, NIST IA-5(7) |
| KMS key with rotation; S3, RDS, logs, SNS, ECR all encrypted with it | `01-data`, `02-compute`, `03-audit` | PCI DSS 3.6, NIST SC-12 |
| VPC flow logs (rejects), ALB access logs, S3 access logs, CloudTrail | `03-audit`, `02-compute`, `01-data` | PCI DSS 10.2, NIST AU-2 |
| Alarms on auth failures, prompt-injection bursts, 5xx, unhealthy hosts | `03-audit` | PCI DSS 10.4, NIST SI-4 |
| Input guardrails, rate limiting, output PII redaction, event emission | `app/guardrails.py`, `app/events.py` | OWASP LLM01/02/05, Law 25 |
| Data minimisation: request metadata only, never prompts or answers at rest | `app/db.py` | Law 25 art. 3.2, GDPR art. 5(1)(c) |
| 90-day log retention and lifecycle expiry | `01-data`, `03-audit` | PCI DSS 10.7 (minimum), Law 25 |

## Accepted exceptions (documented, not hidden)

| Finding | Where | Why accepted |
|---|---|---|
| checkov CKV_AWS_157 Multi-AZ off | `01-data` Db | Doubles RDS cost for a demo storing request metadata. Turn on for production: one line. |
| checkov CKV_AWS_118 enhanced monitoring off | `01-data` Db | Per-instance-hour cost; alarms cover the app and the ALB. |
| checkov CKV_AWS_18 access-log bucket not logged | `01-data` AccessLogsBucket | It is the log destination; a bucket cannot log to itself. |
