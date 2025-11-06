# Code Context Setup Guide

This guide explains how to set up the S3-based code context feature that provides relevant source code to AI analysis.

## Overview

The code context feature enhances AI analysis by:
- Fetching relevant source code files from S3
- Extracting specific code snippets around error locations
- Providing code context alongside infrastructure context
- Enabling better root cause analysis with actual code visibility

## Architecture

```
Alert with Stack Trace
       ↓
Analyzer Lambda
       ↓
Context Gatherer → Code Fetcher → S3 Bucket
       ↓                             ↓
   [Line 42]              [test/test_app.py]
       ↓
Extract 10 lines before/after line 42
       ↓
Send to Gemini API with code snippet
```

## Prerequisites

1. Terraform infrastructure deployed (S3 bucket created)
2. AWS credentials configured locally
3. Python 3.8+ with boto3 installed

## Setup Steps

### 1. Configure Code Mapping

Edit `config/code-mapping.json` to map your log groups to code files:

```json
{
  "/aws/lambda/my-api": "src/api/handler.py",
  "/ecs/my-service": "services/my-service/main.py",
  "/aws/test-app": "test/test_app.py"
}
```

**Format:**
- Key: CloudWatch log group name (must match exactly)
- Value: Relative path to code file (will be used as S3 key)

### 2. Upload Code to S3

Upload your code files to the S3 bucket created by Terraform:

**Option A: Auto-detect bucket from Terraform (Recommended)**

```bash
# Upload entire codebase
python scripts/upload_code_to_s3.py --auto --directory .

# Upload specific directory
python scripts/upload_code_to_s3.py --auto --directory ./lambdas

# Upload with S3 prefix (subdirectory)
python scripts/upload_code_to_s3.py --auto --directory ./src --prefix production
```

**Option B: Specify bucket name manually**

```bash
python scripts/upload_code_to_s3.py \
  --bucket-name dev-madabot-code-storage \
  --directory .
```

**Dry run (preview what would be uploaded):**

```bash
python scripts/upload_code_to_s3.py --auto --directory . --dry-run
```

### 3. Verify Upload

Check that files are in S3:

```bash
# List all files in bucket
aws s3 ls s3://$(terraform -chdir=terraform output -raw code_storage_bucket_name)/ --recursive

# Check mapping config
aws s3 cp s3://$(terraform -chdir=terraform output -raw code_storage_bucket_name)/config/code-mapping.json -
```

### 4. Deploy Lambda Changes

If you modified `code_fetcher.py` or `context_gatherer.py`:

```bash
cd terraform
terraform apply -var-file=environments/dev.tfvars
```

### 5. Test End-to-End

Trigger a test alert and verify code context is included:

```bash
# Trigger test alert
aws lambda invoke \
  --function-name $(terraform -chdir=terraform output -raw ingestor_function_name) \
  --payload '{"message":"Error at line 42: Database connection failed","severity":"HIGH","log_group":"/aws/test-app"}' \
  response.json

# Wait ~30 seconds for processing

# Check analyzer logs for code context
aws logs tail /aws/lambda/$(terraform -chdir=terraform output -raw analyzer_function_name) --follow
```

**Expected log output:**
```
✅ Loaded code mapping from S3: 3 entries
📄 Fetching code context for /aws/test-app → test/test_app.py
✅ Read code file from S3: test/test_app.py (1234 chars)
Context gathered successfully. Length: 2500 chars
```

## File Types Uploaded

The upload script automatically uploads these file types:
- Python: `.py`
- JavaScript/TypeScript: `.js`, `.ts`, `.jsx`, `.tsx`
- Go: `.go`
- Java: `.java`
- Ruby: `.rb`
- PHP: `.php`
- Config: `.yaml`, `.yml`, `.json`, `.tf`
- Shell: `.sh`, `.bash`
- SQL: `.sql`

**Directories automatically skipped:**
- `__pycache__`, `.git`, `node_modules`, `.terraform`
- `venv`, `env`, `.venv`, `dist`, `build`
- `.pytest_cache`, `.mypy_cache`, `coverage`

## Code Mapping Best Practices

### 1. Map Log Groups to Entry Points

Map each log group to the main entry point file:

```json
{
  "/aws/lambda/api-handler": "lambdas/api/handler.py",
  "/ecs/user-service": "services/user/main.go"
}
```

### 2. Use Relative Paths

Paths should be relative to your repository root:

```json
{
  "/aws/app": "src/app.py"           // ✅ Correct
  "/aws/app": "/src/app.py"          // ❌ Don't use absolute paths
  "/aws/app": "./src/app.py"         // ❌ Don't use ./
}
```

### 3. Multiple Services

If you have multiple services in one repo:

```json
{
  "/ecs/frontend": "services/frontend/server.js",
  "/ecs/backend": "services/backend/main.go",
  "/lambda/processor": "lambdas/processor/handler.py"
}
```

### 4. Environment-Specific Mapping

For different environments:

```json
{
  "/aws/prod/api": "src/api/handler.py",
  "/aws/staging/api": "src/api/handler.py",
  "/aws/dev/api": "src/api/handler.py"
}
```

## Updating Code

When you update your code, re-upload to S3:

```bash
# Upload latest code
python scripts/upload_code_to_s3.py --auto --directory .

# S3 versioning is enabled - old versions are retained
```

## Troubleshooting

### "No code mapping for log group: /aws/my-app"

**Cause:** Log group not in `code-mapping.json`

**Fix:**
1. Add mapping to `config/code-mapping.json`
2. Re-upload: `python scripts/upload_code_to_s3.py --auto --directory .`

### "Code file not found in S3: src/app.py"

**Cause:** File not uploaded to S3 or wrong path in mapping

**Fix:**
1. Verify file exists locally: `ls src/app.py`
2. Check S3: `aws s3 ls s3://<bucket>/src/app.py`
3. Re-upload: `python scripts/upload_code_to_s3.py --auto --directory .`

### "S3 client not initialized - CODE_BUCKET not configured"

**Cause:** Lambda environment variable not set

**Fix:**
1. Check Terraform applied: `terraform -chdir=terraform plan`
2. Verify env var in console: Lambda → Configuration → Environment variables
3. Redeploy if needed: `terraform apply`

### "Context gathered successfully. Length: 0 chars"

**Cause:** Either no mapping or no infrastructure context available

**Fix:**
1. Verify `log_group` field in alert (check ingestor logs)
2. Verify mapping exists: `aws s3 cp s3://<bucket>/config/code-mapping.json -`
3. Check code file uploaded: `aws s3 ls s3://<bucket>/ --recursive`

### Permission Denied Errors

**Cause:** Analyzer Lambda IAM role missing S3 permissions

**Fix:**
1. Verify IAM policy in Terraform (`terraform/main.tf` lines 368-378)
2. Check policy attached: AWS Console → IAM → Roles → analyzer role
3. Redeploy: `terraform apply`

## Cost Considerations

**S3 Storage:**
- Small codebase (<100MB): ~$0.023/month
- Medium codebase (1GB): ~$0.23/month
- Large codebase (10GB): ~$2.30/month

**S3 Requests:**
- GetObject calls: ~$0.0004 per 1,000 requests
- For 100 alerts/day: ~$0.01/month

**Total additional cost: ~$0.25-$2.50/month** (negligible compared to AI API costs)

## Security

### S3 Bucket Security

- ✅ Public access blocked (default)
- ✅ Server-side encryption enabled (AES256)
- ✅ Versioning enabled (retain old versions)
- ✅ Least-privilege IAM (analyzer Lambda only)

### Code Sensitivity

**⚠️ Do NOT upload sensitive files:**
- API keys, credentials
- `.env` files
- Private keys (`.pem`, `.key`)
- Customer data

**Tip:** Add `.s3ignore` patterns to upload script if needed.

### IAM Permissions

Analyzer Lambda has:
- `s3:GetObject` - Read code files
- `s3:ListBucket` - List bucket contents

**No write access** - code uploads must be done externally.

## Advanced Usage

### Custom Upload Script

Create a CI/CD pipeline to auto-upload on deployment:

```yaml
# .github/workflows/upload-code.yml
name: Upload Code to S3
on:
  push:
    branches: [main]

jobs:
  upload:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: aws-actions/configure-aws-credentials@v1
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - name: Upload code
        run: python scripts/upload_code_to_s3.py --auto --directory .
```

### Multiple Environments

Use different S3 prefixes for environments:

```bash
# Production
python scripts/upload_code_to_s3.py --auto --directory . --prefix production

# Staging
python scripts/upload_code_to_s3.py --auto --directory . --prefix staging
```

Update `code_fetcher.py` to read from environment-specific prefix.

### Large Repositories

For very large codebases, consider:
1. Upload only relevant directories (`--directory ./src`)
2. Use `.s3ignore` patterns
3. Implement lazy loading (fetch on-demand vs. at Lambda init)

## Next Steps

After setting up code context:
1. Monitor analyzer logs for code context retrieval
2. Review AI analysis quality improvement
3. Expand code mapping to cover all services
4. Set up automated code uploads on deployment

## Support

If you encounter issues:
1. Check CloudWatch logs for analyzer Lambda
2. Verify S3 bucket contents
3. Test with a simple manual alert
4. Review IAM permissions

For more information, see:
- Main documentation: `README.md`
- Terraform outputs: `terraform output`
- Lambda logs: `aws logs tail /aws/lambda/<function-name> --follow`
