# Configuration Directory

This directory contains configuration files for the MCP First-Responder system.

## Files

### code-mapping.json

Maps CloudWatch log groups to source code file paths in S3.

**Purpose:**
- Tells the analyzer Lambda which code file to fetch for each log group
- Enables code context to be included in AI analysis
- Allows extracting specific code snippets around error lines

**Format:**
```json
{
  "/aws/log-group-name": "path/to/file.py",
  "/ecs/my-service": "services/my-service/main.go"
}
```

**Where it's used:**
- Uploaded to S3 at `s3://<bucket>/config/code-mapping.json`
- Read by analyzer Lambda's `CodeFetcher` class at initialization
- Falls back to default mapping (`/aws/test-app` → `test/test_app.py`) if file not found

**How to update:**
1. Edit this file to add/modify mappings
2. Upload to S3: `python scripts/upload_code_to_s3.py --auto --directory .`
3. CodeFetcher will automatically use new mappings (loaded at Lambda cold start)

**Examples:**

```json
{
  "comment": "Lambda functions",
  "/aws/lambda/api-handler": "lambdas/api/handler.py",
  "/aws/lambda/processor": "lambdas/processor/handler.py",

  "comment": "ECS services",
  "/ecs/user-service": "services/user/main.go",
  "/ecs/payment-service": "services/payment/app.js",

  "comment": "Test applications",
  "/aws/test-app": "test/test_app.py"
}
```

**Important:**
- Keys must exactly match CloudWatch log group names
- Values are relative paths from repository root
- Paths become S3 keys after upload
- Don't use absolute paths or `./` prefix

For more details, see: `docs/CODE_CONTEXT_SETUP.md`
