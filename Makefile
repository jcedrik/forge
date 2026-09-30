# forge: build, verify, deploy, demo, destroy.
# Every target that touches AWS needs AWS_REGION and credentials in the env.
PROJECT   ?= forge
REGION    ?= $(or $(AWS_REGION),ca-central-1)
CERT_ARN  ?=
TAG       ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)
ACCOUNT    = $(shell aws sts get-caller-identity --query Account --output text)
ECR        = $(ACCOUNT).dkr.ecr.$(REGION).amazonaws.com/$(PROJECT)/api-llm
GUARD     ?= cfn-guard

.PHONY: help test lint scan guard verify build push deploy-network deploy-data deploy-compute deploy-audit deploy smoke demo destroy run

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  \033[1m%-16s\033[0m %s\n", $$1, $$2}'

# ---------- verify: the seven gates, same as CI ----------
test: ## 1. unit + integration tests for the app
	python -m pytest app/tests -q

scan: ## 2. canary: block prompt-injection sinks, hardcoded keys, PII in logs
	canary app/ --fail-on high --format sarif -o canary.sarif || (canary app/ --fail-on high; exit 1)
	canary app/ --fail-on high

lint: ## 3-5. cfn-lint, cfn-nag (if installed), checkov on the templates
	cfn-lint infra/*.yaml
	@command -v cfn_nag_scan >/dev/null && cfn_nag_scan --input-path infra --template-pattern '..*\.yaml' || echo "cfn_nag not installed, skipped (installed in CI)"
	checkov -d infra --framework cloudformation --quiet --compact

guard: ## 6. cfn-guard: the eight house rules
	@for t in infra/0*.yaml; do $(GUARD) validate -r infra/guard-rules -d $$t --show-summary fail || exit 1; done
	@echo "cfn-guard: all templates comply"

verify: test scan lint guard ## run every gate locally

# ---------- build ----------
build: ## build the api-llm image (arm64, matches Fargate)
	docker buildx build --platform linux/arm64 -t $(PROJECT)/api-llm:$(TAG) -f app/Dockerfile --load .

push: build ## push to ECR (needs 02-compute deployed once for the repo)
	aws ecr get-login-password --region $(REGION) | docker login --username AWS --password-stdin $(ECR)
	docker tag $(PROJECT)/api-llm:$(TAG) $(ECR):$(TAG)
	docker push $(ECR):$(TAG)

# ---------- deploy: four stacks, in order ----------
deploy-network:
	aws cloudformation deploy --region $(REGION) --stack-name $(PROJECT)-network --template-file infra/00-network.yaml --parameter-overrides Project=$(PROJECT)
deploy-data: deploy-network
	aws cloudformation deploy --region $(REGION) --stack-name $(PROJECT)-data --template-file infra/01-data.yaml --parameter-overrides Project=$(PROJECT)
deploy-compute: deploy-data
	@test -n "$(CERT_ARN)" || (echo "CERT_ARN is required (ACM certificate for the ALB)"; exit 1)
	aws cloudformation deploy --region $(REGION) --stack-name $(PROJECT)-compute --template-file infra/02-compute.yaml --capabilities CAPABILITY_IAM --parameter-overrides Project=$(PROJECT) CertificateArn=$(CERT_ARN) ImageTag=$(TAG)
deploy-audit: deploy-compute
	aws cloudformation deploy --region $(REGION) --stack-name $(PROJECT)-audit --template-file infra/03-audit.yaml --capabilities CAPABILITY_IAM --parameter-overrides Project=$(PROJECT)
deploy: verify deploy-audit smoke ## 7. verify, then deploy all four stacks and smoke test

smoke: ## hit /healthz through the ALB
	@ALB=$$(aws cloudformation describe-stacks --region $(REGION) --stack-name $(PROJECT)-compute --query "Stacks[0].Outputs[?OutputKey=='AlbDnsName'].OutputValue" --output text); \
	echo "https://$$ALB/healthz"; curl -fsS --max-time 10 https://$$ALB/healthz && echo

# ---------- demo ----------
run: ## run the app locally with the stub model
	MODEL_PROVIDER=stub uvicorn app.main:app --port 8000

demo: ## the three failure demos, locally (see demo/README.md)
	bash demo/run_all.sh

# ---------- destroy ----------
destroy: ## delete the four stacks in reverse order, empty buckets first, leave nothing billable
	bash infra/destroy.sh $(PROJECT) $(REGION)
