#!/usr/bin/env bash
# infra/queues.sh — Provision or verify AWS SQS/SNS queues for Resume Ranker
# ===========================================================================
# Prerequisites: aws CLI configured with profile "aws" and region ap-south-1.
# Run: bash infra/queues.sh [--check]
#
# With --check flag: verify resources exist without creating them.
# Without flag: create/upsert all required resources.
#
# All resources are tagged with Service=resume-ranker for cost allocation.
#
set -euo pipefail

PROFILE="aws"
REGION="ap-south-1"
ACCOUNT="445567096027"
TAG_KEY="Service"
TAG_VALUE="resume-ranker"

# ── Queue names ──────────────────────────────────────────────────────────────
FAST_PARSE_QUEUE="resume-ranker-fast-parse"
ODL_BATCH_QUEUE="resume-ranker-odl-batch"
NOVA_QUEUE="resume-ranker-nova"
FINAL_RANK_QUEUE="resume-ranker-final-rank"
DLQ_NAME="resume-ranker-dlq"
SNS_TOPIC="resume-ranker-events"

CHECK_ONLY="${1:-}"

log() { echo "[$(date +%H:%M:%S)] $*"; }
err() { echo "[ERROR] $*" >&2; exit 1; }

AWS="aws --profile $PROFILE --region $REGION"

# ── Helpers ──────────────────────────────────────────────────────────────────

get_queue_url() {
  local name="$1"
  $AWS sqs get-queue-url --queue-name "$name" --query "QueueUrl" --output text 2>/dev/null || echo ""
}

get_queue_arn() {
  local url="$1"
  $AWS sqs get-queue-attributes \
    --queue-url "$url" \
    --attribute-names QueueArn \
    --query "Attributes.QueueArn" \
    --output text
}

create_or_verify_queue() {
  local name="$1"
  local extra_attrs="${2:-}"
  local url
  url=$(get_queue_url "$name")

  if [[ -n "$url" ]]; then
    log "Queue exists: $name ($url)"
    echo "$url"
    return
  fi

  if [[ "$CHECK_ONLY" == "--check" ]]; then
    err "Queue missing (check mode): $name"
  fi

  log "Creating queue: $name"
  local create_args=(
    --queue-name "$name"
    --attributes "VisibilityTimeout=300,MessageRetentionPeriod=86400,ReceiveMessageWaitTimeSeconds=20"
  )
  if [[ -n "$extra_attrs" ]]; then
    create_args+=(--attributes "$extra_attrs,VisibilityTimeout=300,MessageRetentionPeriod=86400,ReceiveMessageWaitTimeSeconds=20")
  fi

  url=$($AWS sqs create-queue "${create_args[@]}" --query "QueueUrl" --output text)
  $AWS sqs tag-queue --queue-url "$url" --tags "$TAG_KEY=$TAG_VALUE"
  log "Created: $url"
  echo "$url"
}

# ── 1. Dead-letter queue ─────────────────────────────────────────────────────
log "=== Dead-letter queue ==="
DLQ_URL=$(create_or_verify_queue "$DLQ_NAME")
DLQ_ARN=$(get_queue_arn "$DLQ_URL")
log "DLQ ARN: $DLQ_ARN"

REDRIVE_POLICY="{\"deadLetterTargetArn\":\"$DLQ_ARN\",\"maxReceiveCount\":\"5\"}"

# ── 2. Fast-parse queue ───────────────────────────────────────────────────────
log "=== Fast-parse queue ==="
FAST_URL=$(create_or_verify_queue "$FAST_PARSE_QUEUE" \
  "RedrivePolicy=$(echo "$REDRIVE_POLICY" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))')")
FAST_ARN=$(get_queue_arn "$FAST_URL")
log "fast-parse ARN: $FAST_ARN"
log "fast-parse URL: $FAST_URL"

# ── 3. ODL batch queue ────────────────────────────────────────────────────────
log "=== ODL batch queue ==="
ODL_URL=$(create_or_verify_queue "$ODL_BATCH_QUEUE" \
  "RedrivePolicy=$(echo "$REDRIVE_POLICY" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))')")
log "odl-batch URL: $ODL_URL"

# ── 4. Nova queue ─────────────────────────────────────────────────────────────
log "=== Nova queue ==="
NOVA_URL=$(create_or_verify_queue "$NOVA_QUEUE" \
  "RedrivePolicy=$(echo "$REDRIVE_POLICY" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))')")
log "nova URL: $NOVA_URL"

# ── 5. Final rank queue ───────────────────────────────────────────────────────
log "=== Final rank queue ==="
RANK_URL=$(create_or_verify_queue "$FINAL_RANK_QUEUE" \
  "RedrivePolicy=$(echo "$REDRIVE_POLICY" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))')")
log "final-rank URL: $RANK_URL"

# ── 6. SNS topic ──────────────────────────────────────────────────────────────
log "=== SNS topic ==="
SNS_ARN=$($AWS sns list-topics --query "Topics[?ends_with(TopicArn, ':$SNS_TOPIC')].TopicArn" --output text)
if [[ -z "$SNS_ARN" ]]; then
  if [[ "$CHECK_ONLY" == "--check" ]]; then
    err "SNS topic missing (check mode): $SNS_TOPIC"
  fi
  log "Creating SNS topic: $SNS_TOPIC"
  SNS_ARN=$($AWS sns create-topic --name "$SNS_TOPIC" --query "TopicArn" --output text)
  $AWS sns tag-resource --resource-arn "$SNS_ARN" --tags "Key=$TAG_KEY,Value=$TAG_VALUE"
fi
log "SNS topic ARN: $SNS_ARN"

# ── 7. SNS → fast-parse SQS subscription ────────────────────────────────────
log "=== SNS → fast-parse SQS subscription ==="
EXISTING_SUB=$($AWS sns list-subscriptions-by-topic \
  --topic-arn "$SNS_ARN" \
  --query "Subscriptions[?Endpoint=='$FAST_ARN'].SubscriptionArn" \
  --output text 2>/dev/null || echo "")

if [[ -z "$EXISTING_SUB" || "$EXISTING_SUB" == "None" ]]; then
  if [[ "$CHECK_ONLY" == "--check" ]]; then
    err "SNS subscription missing (check mode)"
  fi
  log "Subscribing fast-parse SQS to SNS..."
  # Set SQS access policy to allow SNS to send messages
  POLICY="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"sns.amazonaws.com\"},\"Action\":\"sqs:SendMessage\",\"Resource\":\"$FAST_ARN\",\"Condition\":{\"ArnEquals\":{\"aws:SourceArn\":\"$SNS_ARN\"}}}]}"
  $AWS sqs set-queue-attributes \
    --queue-url "$FAST_URL" \
    --attributes "Policy=$(echo "$POLICY" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))')"

  SUB_ARN=$($AWS sns subscribe \
    --topic-arn "$SNS_ARN" \
    --protocol sqs \
    --notification-endpoint "$FAST_ARN" \
    --query "SubscriptionArn" \
    --output text)
  log "Subscription ARN: $SUB_ARN"
else
  log "Subscription already exists: $EXISTING_SUB"
fi

# ── 8. Summary ───────────────────────────────────────────────────────────────
log ""
log "════════════════════════════════════════════════════════════════"
log "  Queue provisioning complete. Add these to backend/.env:"
log "════════════════════════════════════════════════════════════════"
echo ""
echo "SNS_EVENTS_TOPIC_ARN=$SNS_ARN"
echo "SQS_FAST_PARSE_URL=$FAST_URL"
echo "SQS_ODL_BATCH_URL=$ODL_URL"
echo "SQS_NOVA_URL=$NOVA_URL"
echo "SQS_FINAL_RANK_URL=$RANK_URL"
echo "USE_REAL_SQS=true"
echo "RUN_LOCAL_WORKERS=true"
echo ""
