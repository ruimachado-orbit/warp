#!/usr/bin/env bash
# Deploy Warp SAM stack to AWS
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Load environment
if [ ! -f .env ]; then
  echo "❌ .env file not found. Copy .env.example and fill in values."
  exit 1
fi

set -a
source .env
set +a

# Required variables
: "${CLOUDFORMATION_STACK_NAME:?CLOUDFORMATION_STACK_NAME not set}"
: "${AWS_REGION:?AWS_REGION not set}"
: "${RESEND_API_KEY:?RESEND_API_KEY not set}"
: "${RESEND_FROM:?RESEND_FROM not set}"
: "${RESEND_TO:?RESEND_TO not set}"

# Optional
SITE_HOSTNAME="${SITE_HOSTNAME:-}"
ACM_CERTIFICATE_ARN="${ACM_CERTIFICATE_ARN:-}"
ALLOWED_ORIGIN="${ALLOWED_ORIGIN:-*}"

echo "🚀 Deploying Warp SAM stack..."
echo "   Stack: $CLOUDFORMATION_STACK_NAME"
echo "   Region: $AWS_REGION"
echo "   Domain: ${SITE_HOSTNAME:-[none - using CloudFront default]}"

# Create temporary parameter file with proper JSON escaping
PARAMS_FILE=$(mktemp)
trap "rm -f $PARAMS_FILE" EXIT

cat > "$PARAMS_FILE" <<EOF
SiteHostname="$SITE_HOSTNAME"
AcmCertificateArn="$ACM_CERTIFICATE_ARN"
AllowedOrigin="$ALLOWED_ORIGIN"
ResendApiKey="$RESEND_API_KEY"
ResendFrom="$RESEND_FROM"
ResendTo="$RESEND_TO"
EOF

echo ""
echo "📦 Building and deploying with SAM..."

sam build --template template.yaml

sam deploy \
  --stack-name "$CLOUDFORMATION_STACK_NAME" \
  --region "$AWS_REGION" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides "$(cat $PARAMS_FILE)" \
  --no-fail-on-empty-changeset \
  --resolve-s3

echo ""
echo "✅ Stack deployed successfully!"
echo ""
echo "📋 Outputs:"
aws cloudformation describe-stacks \
  --stack-name "$CLOUDFORMATION_STACK_NAME" \
  --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
  --output table

echo ""
echo "Next step: Run ./scripts/publish-public.sh to deploy the website"
