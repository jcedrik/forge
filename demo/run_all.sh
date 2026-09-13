#!/usr/bin/env bash
# Runs the three failure demos locally. Each one proves a gate refuses.
#   1. canary refuses a prompt-injection sink + hardcoded key in app code
#   2. cfn-guard refuses a public bucket + a world-open port 22
#   3. triage correlates an attack sequence into one high-risk incident
set -uo pipefail
cd "$(dirname "$0")/.."
GUARD=${GUARD:-cfn-guard}
fail=0

echo "=============== demo 1: canary must block ==============="
tmp=$(mktemp -d); cp -r app "$tmp/app"
(cd "$tmp" && patch -s -p1 < "$OLDPWD/demo/01-bad-prompt-sink.patch")
if canary "$tmp/app" --fail-on high; then echo "demo 1 FAILED: canary let it through"; fail=1; else echo "demo 1 PASSED: build refused (exit 1)"; fi
rm -rf "$tmp"

echo; echo "=============== demo 2: cfn-guard must refuse ==============="
tmp=$(mktemp -d); cp -r infra "$tmp/infra"
(cd "$tmp" && patch -s -p1 < "$OLDPWD/demo/02-public-bucket.patch")
ok=1
for t in "$tmp"/infra/0*.yaml; do $GUARD validate -r infra/guard-rules -d "$t" --show-summary fail >/dev/null 2>&1 || ok=0; done
if [ $ok = 1 ]; then echo "demo 2 FAILED: cfn-guard accepted a public bucket"; fail=1; else
  $GUARD validate -r infra/guard-rules -d "$tmp/infra/01-data.yaml" --show-summary fail 2>/dev/null | grep -E "FAIL|s3-block" | head -4
  $GUARD validate -r infra/guard-rules -d "$tmp/infra/00-network.yaml" --show-summary fail 2>/dev/null | grep -E "FAIL|sg-no-open" | head -4
  echo "demo 2 PASSED: deployment never happens"; fi
rm -rf "$tmp"

echo; echo "=============== demo 3: triage must correlate ==============="
bash demo/03-attack-simulation.sh || fail=1

echo; [ $fail = 0 ] && echo "ALL THREE DEMOS PASSED" || { echo "A DEMO FAILED"; exit 1; }
