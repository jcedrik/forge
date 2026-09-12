#!/usr/bin/env bash
# Tears down forge completely. Order matters: audit -> compute -> data -> network.
# Buckets are versioned, so every version and delete marker must go before
# the stack can delete the bucket. Verified at the end by listing what's left.
set -euo pipefail
PROJECT=${1:-forge}
REGION=${2:-ca-central-1}

stack_delete() {
  local name=$1
  if aws cloudformation describe-stacks --region "$REGION" --stack-name "$name" >/dev/null 2>&1; then
    echo "deleting $name"
    aws cloudformation delete-stack --region "$REGION" --stack-name "$name"
    aws cloudformation wait stack-delete-complete --region "$REGION" --stack-name "$name"
  else
    echo "$name: not present"
  fi
}

empty_bucket() {
  local b=$1
  aws s3api head-bucket --bucket "$b" 2>/dev/null || { echo "$b: not present"; return; }
  echo "emptying $b (all versions)"
  python3 - "$b" <<'PY'
import boto3, sys
b = sys.argv[1]; s3 = boto3.client("s3")
paginator = s3.get_paginator("list_object_versions")
for page in paginator.paginate(Bucket=b):
    objs = [{"Key": v["Key"], "VersionId": v["VersionId"]} for k in ("Versions", "DeleteMarkers") for v in page.get(k, [])]
    for i in range(0, len(objs), 1000):
        s3.delete_objects(Bucket=b, Delete={"Objects": objs[i:i+1000], "Quiet": True})
print("emptied", b)
PY
}

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
stack_delete "$PROJECT-audit"
stack_delete "$PROJECT-compute"
empty_bucket "$PROJECT-logs-$ACCOUNT-$REGION"
empty_bucket "$PROJECT-s3-access-$ACCOUNT-$REGION"
stack_delete "$PROJECT-data"
stack_delete "$PROJECT-network"

echo "--- what is left that could bill ---"
aws cloudformation list-stacks --region "$REGION" --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE DELETE_FAILED --query "StackSummaries[?starts_with(StackName, '$PROJECT')].StackName" --output text
aws rds describe-db-instances --region "$REGION" --query "DBInstances[?starts_with(DBInstanceIdentifier, '$PROJECT')].DBInstanceIdentifier" --output text
aws ec2 describe-nat-gateways --region "$REGION" --filter Name=state,Values=available --query "NatGateways[].NatGatewayId" --output text
aws elbv2 describe-load-balancers --region "$REGION" --query "LoadBalancers[?starts_with(LoadBalancerName, '$PROJECT')].LoadBalancerName" --output text
aws s3api list-buckets --query "Buckets[?starts_with(Name, '$PROJECT')].Name" --output text
aws logs describe-log-groups --region "$REGION" --log-group-name-prefix "/$PROJECT" --query "logGroups[].logGroupName" --output text
echo "(empty lines above mean nothing is left)"
