#!/usr/bin/env bash
# Publish Warp website to S3 + invalidate CloudFront
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Load environment
if [ ! -f .env ]; then
  echo "❌ .env file not found"
  exit 1
fi

set -a
source .env
set +a

: "${CLOUDFORMATION_STACK_NAME:?CLOUDFORMATION_STACK_NAME not set}"
: "${AWS_REGION:?AWS_REGION not set}"

echo "🔍 Fetching stack outputs..."

# Get outputs from CloudFormation
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name "$CLOUDFORMATION_STACK_NAME" \
  --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`SiteBucketName`].OutputValue' \
  --output text)

DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
  --stack-name "$CLOUDFORMATION_STACK_NAME" \
  --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' \
  --output text)

export REGISTER_FUNCTION_URL=$(aws cloudformation describe-stacks \
  --stack-name "$CLOUDFORMATION_STACK_NAME" \
  --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`RegisterFunctionUrl`].OutputValue' \
  --output text)

echo "   Bucket: $BUCKET_NAME"
echo "   Distribution: $DISTRIBUTION_ID"
echo "   Lambda URL: $REGISTER_FUNCTION_URL"

echo ""
echo "🏗️  Building website..."
npm run build

echo ""
echo "📤 Uploading to S3..."
aws s3 sync out/ "s3://$BUCKET_NAME/" \
  --delete \
  --cache-control "public, max-age=300" \
  --exclude ".DS_Store"

echo ""
echo "🔄 Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/*" \
  --query 'Invalidation.[Id,Status,CreateTime]' \
  --output table

echo ""
echo "✅ Website published successfully!"
echo ""
echo "🌐 URLs:"
aws cloudformation describe-stacks \
  --stack-name "$CLOUDFORMATION_STACK_NAME" \
  --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`PublicSiteUrl` || OutputKey==`PublicCustomUrl`].[OutputKey,OutputValue]' \
  --output table
