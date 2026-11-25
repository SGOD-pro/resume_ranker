# SAM Dev Stack Deployment Guide

> **MANDATE**: Do NOT deploy to the production stack. This guide documents how to deploy an isolated development stack with custom parameters, dedicated S3 storage, separate DynamoDB table, independent SQS queues and DLQs, and zero production impact.

---

## 1. Architecture Isolation Guarantees

The dev stack (`infra/template.dev.yaml`) is completely decoupled from production:
- **Dedicated S3 Bucket**: `resume-ranker-dev-isolated-storage-<account_id>` (with 7-day auto-purge).
- **Dedicated DynamoDB Table**: `ResumePlatformDev` (single-table schema with PAY_PER_REQUEST billing).
- **Isolated Queues & DLQs**: Unique queue names with `-dev` suffix.
- **Dedicated Lambdas**: Execution roles with least-privilege policies; zero hardcoded credentials.
- **Cost Guardrails**: `AWS::Budgets::Budget` alarm configured to alert at 80% of $15/month.

---

## 2. Prerequisites

1. AWS CLI configured with active credentials:
   ```bash
   aws sts get-caller-identity
   ```
2. AWS SAM CLI installed:
   ```bash
   sam --version
   ```

---

## 3. Step-by-Step Deployment Commands

### Step 3.1: Build the SAM Application
From repository root:
```bash
sam build -t infra/template.dev.yaml
```

### Step 3.2: Deploy Dev Stack with Parameter Overrides
Substitute your AWS Account ID in the bucket name to ensure globally unique S3 naming:
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
DEV_BUCKET="resume-ranker-dev-${ACCOUNT_ID}"
DEV_STACK_NAME="resume-ranker-dev-stack"

sam deploy \
  --stack-name "${DEV_STACK_NAME}" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
      Environment=dev \
      S3BucketName="${DEV_BUCKET}" \
      DynamoDBTableName="ResumePlatformDev" \
      BudgetLimitUSD=15 \
  --resolve-s3 \
  --no-confirm-changeset
```

### Step 3.3: Verify Deployed Outputs
Query the dev stack outputs:
```bash
aws cloudformation describe-stacks \
  --stack-name "${DEV_STACK_NAME}" \
  --query "Stacks[0].Outputs" \
  --output table
```
Take note of `ApiUrl` (e.g. `https://<api-id>.execute-api.ap-south-1.amazonaws.com`).

---

## 4. Teardown / Deletion
To completely destroy the dev stack and eliminate all AWS resources and charges:
```bash
# 1. Empty the dev S3 bucket
aws s3 rm "s3://${DEV_BUCKET}" --recursive

# 2. Delete CloudFormation stack
sam delete --stack-name "${DEV_STACK_NAME}" --no-prompts
```
