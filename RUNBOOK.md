# Runbook

How to deploy, destroy, and debug forge. Written so someone who has never
seen the repo can run it in under 20 minutes.

## Prerequisites

- AWS account with admin rights for the first deploy, `aws` CLI v2 configured, `AWS_REGION` set (default `ca-central-1`).
- An ACM certificate in that region for the ALB (any domain you control; a self-signed import works for a demo). Its ARN goes in `CERT_ARN`.
- Docker with buildx (the image is ARM64, Fargate's cheaper architecture).
- Python 3.12, `pip install -r app/requirements.txt -r requirements-dev.txt`.
- `cfn-guard` v3 on the PATH (release tarball from the cloudformation-guard repo) and `cfn_nag` (`gem install cfn-nag`) for `make lint`.

## Deploy

```bash
make verify                    # the seven gates, locally, about 90 seconds
make deploy CERT_ARN=arn:aws:acm:ca-central-1:123456789012:certificate/...
```

`make deploy` runs the gates again, then the four stacks in order:

| Order | Stack | What | Time |
|---|---|---|---|
| 1 | `forge-network` | VPC, subnets, security groups, endpoints | ~3 min |
| 2 | `forge-data` | KMS, buckets, Secrets Manager, RDS | ~8 min (RDS) |
| 3 | `forge-compute` | ECR, cluster, task, service, ALB | ~4 min |
| 4 | `forge-audit` | CloudTrail, flow logs, metric filters, alarms | ~2 min |

Between 2 and 3 the image has to exist in ECR, so a first deploy is:

```bash
make deploy-data
make deploy-compute CERT_ARN=... DesiredCount=0   # creates the repo with no tasks
make push
make deploy-compute CERT_ARN=...                  # now with the image
make deploy-audit
make smoke
```

In CI this ordering is already encoded in `.github/workflows/ci.yaml`.

Then:

```bash
ALB=$(aws cloudformation describe-stacks --stack-name forge-compute --query "Stacks[0].Outputs[?OutputKey=='AlbDnsName'].OutputValue" --output text)
TOKEN=$(aws secretsmanager get-secret-value --secret-id forge/api-token --query SecretString --output text)
curl -sk https://$ALB/healthz
curl -sk -X POST https://$ALB/chat -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"prompt":"Hello"}'
```

## Destroy

```bash
make destroy
```

Deletes audit, compute, data, network in that order, emptying the versioned
buckets first, and prints anything left in the account that starts with
`forge`. Check that the lines are empty. Then check the console once: Cost
Explorer the next day should show the forge tags at zero.

## Debug: the three most likely failures

### 1. The service never becomes healthy (`UnHealthyHostCount` alarm, deploy circuit breaker rolls back)

```bash
aws ecs describe-services --cluster forge --services api-llm --query "services[0].events[:5]"
aws logs tail /forge/api-llm --since 10m
```

Usual causes, in order seen:
- **Image not in ECR for that tag.** `make push TAG=<sha>` then redeploy with the same `TAG`.
- **Task cannot reach Secrets Manager or ECR**: the endpoint security group is missing the ECS ingress, or private DNS is off. `aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=<vpc>` and check `PrivateDnsEnabled`.
- **Container exits immediately**: `DB_CREDENTIALS` JSON not parsable or RDS unreachable. The app still answers `/healthz` with 503 and `"db": false`, so if you see no logs at all it is the image, not the database.

### 2. `/chat` returns 401 for everyone

The task reads `API_TOKEN` from Secrets Manager at start. If the secret was
rotated after the task started, the task has the old value. Force a new
deployment: `aws ecs update-service --cluster forge --service api-llm --force-new-deployment`.

### 3. A gate blocks a push and you believe it is wrong

- **canary**: read the finding. If it is a true positive, fix the code. If it is accepted on purpose, add `# canary: ignore CANARY-XX-NNN` on that line with a comment saying why, and the reviewer sees both.
- **cfn-guard**: the message names the rule and the control. The rule is right more often than the template. If you need an exception, it goes in `docs/compliance-matrix.md` under "Accepted exceptions" *and* the guard rule gets a `when` clause excluding that resource by name, so the exception is visible in two places.
- **checkov**: `Metadata.checkov.skip` on the resource with a comment, same as the three already there.

## One-time setup for CI deploys (OIDC, no AWS keys in GitHub)

1. Create an IAM OIDC provider for `token.actions.githubusercontent.com` in the account.
2. Create a role `forge-github-deploy` trusted by that provider, condition `repo:jcedrik/forge:ref:refs/heads/main`, with the permissions CloudFormation needs for these four stacks (start from `PowerUserAccess` plus `iam:*Role*`/`iam:*Policy*` scoped to `forge-*`, then narrow with Access Analyzer after the first deploy).
3. GitHub repo settings: environment `production` with secrets `AWS_DEPLOY_ROLE_ARN` and `ACM_CERTIFICATE_ARN`.

## Rotate the API token

```bash
aws secretsmanager update-secret --secret-id forge/api-token --secret-string "$(openssl rand -hex 20)"
aws ecs update-service --cluster forge --service api-llm --force-new-deployment
```
