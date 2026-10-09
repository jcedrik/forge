# At 100x

forge serves one small LLM endpoint. This note names where the design breaks
when load, team size, or rule count grows by two orders of magnitude, and
what changes. Orders of magnitude, not benchmarks: the point is to show the
bottlenecks were thought about, not to pretend they were measured.

## Traffic: 1 request/s to 100 request/s

**First thing that breaks: the rate limiter.** It is an in-process dict
(`app/guardrails.py`). With two or more Fargate tasks behind the ALB, each
task counts separately, so the real limit is `limit x tasks` and a client
pinned to different tasks is never limited. Fix: move the counter to
ElastiCache (Redis `INCR` with TTL) or use AWS WAF rate-based rules in front
of the ALB, which also moves the work off the app entirely. WAF is the better
answer at 100x: it is the same control for every service.

**Second: the model call.** At 100 req/s with a real provider the task spends
its time waiting on the network. 0.25 vCPU handles that fine, but one task
does not: target-tracking autoscaling on `ALBRequestCountPerTarget` (say 50
per task) with a ceiling of 10 tasks. The task definition and service are
already shaped for it; it is an `AWS::ApplicationAutoScaling::ScalableTarget`
plus a policy, about 30 lines in `02-compute`.

**Third: the database.** Request metadata is one insert per request; a
`db.t4g.micro` sustains hundreds per second. Not a bottleneck at 100x. At
1000x, batch inserts or drop the table for a Kinesis stream into S3, because
nobody queries this table live.

**What does not break:** the ALB (it scales itself), the guardrail regexes
(microseconds), CloudWatch Logs ingestion (pay more, same design).

## Events: 10 security events/min to 1,000/min

The detection path is `CloudWatch Logs -> triage_adapter.py (pull) -> triage`.
Pulling 1,000 events a minute through `filter_log_events` is slow and costs
per GB scanned. Replace the pull with a push: a CloudWatch Logs subscription
filter on `{ $.event = * }` into a Kinesis Data Firehose, landing JSON in S3,
and run triage on a schedule over the last hour. Or send the same stream to
Sentinel through the Azure Monitor agent and let the KQL that triage already
emits do the correlation there. The app changes nothing: it keeps writing
one JSON line per event.

triage itself is O(n log n) in alerts per host; 60,000 alerts an hour is
seconds. Its in-memory model would need the `--pivot-src-ip` union-find to
stay bounded (it is O(incidents^2) today, fine under 10,000 incidents, not
fine at 100,000). SCALE note filed upstream.

## Rules: 8 guard rules to 800

cfn-guard evaluates every rule against every template on every push; 800
rules x 4 templates is still under a minute. The problem is ownership, not
speed: 800 rules need a registry (which team owns which rule, what control it
maps to, how to request an exception). That is `docs/compliance-matrix.md`
turned into a table in a database with an approval workflow, and it is
exactly what AWS Config conformance packs and Security Hub standards are.
At 100x you stop writing guard rules by hand and generate them from the
control catalogue.

## Services: 1 service to 100

Four stacks per service is 400 stacks. The fix is to make `infra/` a
template, not a copy: a CDK construct or a Service Catalog product that
takes `Project`, image, and size, and stamps out the same four stacks with
the same guard rules attached. The guard rules live in one repo and every
service's pipeline pulls them, so a new rule lands everywhere on the next
push. The pipeline becomes a reusable workflow (`workflow_call`) that every
service repo invokes with three lines.

## Honest limits of the current design

- One region. Multi-region needs Route 53 health checks, a second set of
  stacks, and a decision about the database (read replica or Aurora Global).
- No WAF. At any real exposure, put WAF with the AWS managed rule groups and
  a rate rule in front of the ALB before anything else on this page.
- The stub model hides the real cost center. With a real provider, model
  spend will exceed the whole AWS bill by the second day; the `/metrics`
  counters are what you would alarm on.
