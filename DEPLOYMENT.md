# Warp Website Deployment Guide

## Architecture

- **S3**: Private bucket for website content
- **CloudFront**: CDN with Origin Access Control (OAC)
- **ACM**: SSL certificate in us-east-1 (*.maiolabs.ai)
- **Lambda**: Contact form API (Function URL)
- **Cloudflare**: DNS proxy to CloudFront (Full strict mode)

## Prerequisites

1. AWS CLI configured with appropriate credentials
2. SAM CLI installed (`brew install aws-sam-cli`)
3. Node.js 20+ installed
4. Resend API key

## Initial Deployment

### 1. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set:
- `RESEND_API_KEY` - Your Resend API key
- Other variables are pre-configured for warp.maiolabs.ai

### 2. Deploy SAM Stack

```bash
./scripts/deploy-stack.sh
```

This creates:
- S3 bucket: `warp-site-site`
- CloudFront distribution with custom domain
- Lambda function for contact form
- IAM policies and OAC

### 3. Deploy Website

```bash
./scripts/publish-public.sh
```

This:
- Builds website with Lambda URL injected
- Syncs to S3
- Invalidates CloudFront cache

### 4. Configure Cloudflare DNS

Add CNAME record:
- **Name**: `warp`
- **Target**: `<cloudfront-id>.cloudfront.net` (from stack outputs)
- **Proxy**: ✅ Enabled (orange cloud)
- **SSL/TLS mode**: Full (strict)

## GitHub Actions Setup

Required secrets (Settings → Secrets → Actions):

```
AWS_DEPLOY_ROLE_ARN=arn:aws:iam::857119674988:role/github-oidc-warp
S3_BUCKET_NAME=warp-site-site
CLOUDFRONT_DISTRIBUTION_ID=<from stack outputs>
REGISTER_FUNCTION_URL=<from stack outputs>
```

Push to `main` branch to trigger automatic deployment.

## Manual Commands

```bash
# Deploy everything
make deploy

# Just deploy stack
make deploy-stack

# Just deploy website
make deploy-site

# Local development
make website-dev
# or
npm run dev
```

## Stack Outputs

View outputs anytime:

```bash
aws cloudformation describe-stacks \
  --stack-name warp-site \
  --region eu-west-1 \
  --query 'Stacks[0].Outputs'
```

## Teardown

```bash
# Empty S3 bucket first
aws s3 rm s3://warp-site-site/ --recursive

# Delete stack
aws cloudformation delete-stack \
  --stack-name warp-site \
  --region eu-west-1
```

## Troubleshooting

### CloudFront shows 403

- Check OAC permissions on S3 bucket policy
- Verify distribution origin points to bucket regional domain name

### SSL cert mismatch

- Ensure ACM cert is in **us-east-1** (CloudFront requirement)
- Verify cert covers `warp.maiolabs.ai` (wildcard `*.maiolabs.ai`)

### Lambda CORS errors

- Check `ALLOWED_ORIGIN` matches exact public URL
- Must be `https://warp.maiolabs.ai` (no trailing slash)

### CloudFront cache issues

Always invalidate after deploy:
```bash
aws cloudfront create-invalidation \
  --distribution-id <dist-id> \
  --paths "/*"
```

## URLs

- **Production**: https://warp.maiolabs.ai
- **CloudFront direct**: https://<dist-id>.cloudfront.net
- **Lambda API**: https://<random>.lambda-url.eu-west-1.on.aws/
