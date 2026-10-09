# Cost

Estimated monthly cost of forge running 24/7 in `ca-central-1`, from the AWS
price list on the day of writing (October 2026). Replace the "measured" column
with the Cost Explorer figure after 30 days of running; that number is the one
that goes in the README.

| Resource | Sizing | USD / month (list) | Measured |
|---|---|---:|---:|
| ECS Fargate, 1 task, 0.25 vCPU / 0.5 GB, ARM64 | 730 h | ~8.50 | |
| Application Load Balancer | 1 ALB + ~1 LCU | ~22.50 | |
| RDS PostgreSQL db.t4g.micro, 20 GB gp3 | single-AZ | ~14.50 (0 the first year if free-tier eligible) | |
| VPC interface endpoints x4 (ecr.api, ecr.dkr, logs, secretsmanager), 2 AZ | 8 ENI-hours | ~58 | |
| S3 gateway endpoint | | 0 | |
| KMS key | 1 key + requests | ~1.10 | |
| CloudTrail, first management trail | | 0 | |
| CloudWatch Logs (app + flow + trail), ~2 GB ingested | | ~1.20 | |
| CloudWatch alarms x4, metric filters | | ~0.40 | |
| Secrets Manager x2 | | ~0.80 | |
| ECR, ~1 GB | | ~0.10 | |
| S3 logs, a few GB with lifecycle | | ~0.20 | |
| SNS | | 0 | |
| **Total, running** | | **~107 (~93 with RDS free tier)** | |
| **Total after `make destroy`** | | **0** | |

## Where the money goes, and the two levers

Interface endpoints are more than half the bill. Four endpoints in two AZs
is eight ENIs at ~0.01 USD/h each. That is still cheaper than a NAT Gateway
(~32 USD/month plus data processing) in *one* AZ, and it is the design that
leaves the private subnets with no route to the internet, which is the point.

Levers, if this had to be cheaper for a demo:

1. **Single AZ for the endpoints** (not the ALB, which needs two): halves the
   endpoint line to ~29 USD. One parameter.
2. **Destroy between demos.** `make deploy` is under 20 minutes end to end,
   `make destroy` under 10. Running it only when someone is looking brings the
   month to a few dollars.

The NAT Gateway trap, for the record: a forgotten NAT costs ~32 USD/month
doing nothing. forge has none, and `infra/destroy.sh` lists any NAT in the
region at the end so you would see it.

## What `make destroy` does

Deletes the four stacks in reverse order, empties the two versioned buckets
first (every version and delete marker, otherwise the stack delete fails),
then lists what is left in the account that starts with `forge`: stacks, RDS
instances, NATs, load balancers, buckets, log groups. Empty lines mean zero
dollars.
