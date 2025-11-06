# Demo Button Setup Instructions

This guide explains how to connect the "Trigger Demo Alert" button on the landing page to your actual AWS infrastructure.

## 🎯 What This Does

When someone clicks "Trigger Demo Alert" on your GitHub Pages site, it will:
1. Send a real alert to your AWS Lambda function
2. Trigger the full incident response pipeline
3. Generate AI analysis with infrastructure context
4. Send notification to your Slack channel
5. Show the animated timeline on the web page

## 📋 Prerequisites

- Terraform infrastructure deployed to AWS
- GitHub Pages site published
- AWS credentials configured locally

## 🚀 Setup Steps

### Step 1: Deploy Infrastructure with Lambda Function URL

The Lambda Function URL has already been added to your Terraform configuration. Deploy it:

```bash
cd terraform

# Initialize Terraform (if not done)
terraform init -backend-config=environments/dev-backend.tfvars

# Deploy infrastructure
terraform apply -var-file=environments/dev.tfvars
```

### Step 2: Get the Lambda Function URL

After deployment, get the public URL:

```bash
terraform output ingestor_demo_url
```

You'll get something like:
```
https://abc123xyz.lambda-url.us-east-1.on.aws/
```

**Copy this URL!** ✂️

### Step 3: Update script.js

Open `docs/script.js` and replace the placeholder:

```javascript
// Find this line (around line 41):
const LAMBDA_DEMO_URL = 'YOUR_LAMBDA_URL_HERE';

// Replace with your actual URL:
const LAMBDA_DEMO_URL = 'https://abc123xyz.lambda-url.us-east-1.on.aws/';
```

### Step 4: Commit and Push

```bash
git add docs/script.js
git commit -m "Configure Lambda demo URL"
git push origin main
```

GitHub Pages will automatically rebuild (takes 1-2 minutes).

### Step 5: Test It!

1. Go to your GitHub Pages site: `https://yourusername.github.io/your-repo/`
2. Scroll to the "Demo" section
3. Click **"Trigger Demo Alert"**
4. Check your browser console (F12) for logs
5. Check your Slack channel for the notification!

## 🔍 Verification

### Check if it worked:

**1. Browser Console:**
```
✅ Alert triggered successfully: {statusCode: 200, ...}
```

**2. CloudWatch Logs:**
```bash
# View ingestor logs
terraform output view_logs_ingestor | bash

# View analyzer logs
terraform output view_logs_analyzer | bash
```

**3. Slack Channel:**
- You should see a formatted alert with Block Kit
- Infrastructure context included
- Interactive buttons visible

### If something goes wrong:

**Button shows "Demo Running (Simulated)":**
- You haven't updated the LAMBDA_DEMO_URL yet
- It will run animation only, not trigger real alert

**Button shows "❌ Failed":**
- Check browser console for error details
- Verify Lambda URL is correct
- Check CORS is enabled on Lambda
- Verify Lambda function is deployed

**No Slack notification:**
- Check CloudWatch logs for analyzer Lambda
- Verify Slack bot token secret exists
- Check distribution queue has messages

## 🔒 Security Considerations

### Public Lambda URL

⚠️ The Lambda Function URL is **publicly accessible**. This is intentional for the demo button, but consider:

**Built-in Protection:**
- Rate limiting via Lambda reserved concurrency (already configured)
- No AWS credentials exposed
- Only triggers test alerts (not destructive)

**Additional Hardening (Optional):**

1. **Add API Key:**
```javascript
headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'your-secret-key'
}
```

2. **Check Referer Header in Lambda:**
```python
referer = event.get('headers', {}).get('referer', '')
if 'github.io' not in referer:
    return {'statusCode': 403, 'body': 'Forbidden'}
```

3. **Enable CloudWatch Alarms:**
```bash
# Already configured in Terraform
# Monitors: Lambda errors, DLQ depth
```

## 🎨 Customizing the Demo

### Change Demo Alert Message

Edit `docs/script.js` line 80-86:

```javascript
body: JSON.stringify({
    message: 'YOUR CUSTOM ALERT MESSAGE HERE',
    severity: 'CRITICAL',  // CRITICAL | HIGH | MEDIUM | LOW
    source: 'demo-web-page',
    log_group: '/aws/lambda/demo-app',
    log_stream: 'demo-stream'
})
```

### Disable Real Triggering

To go back to animation-only:

```javascript
const LAMBDA_DEMO_URL = 'YOUR_LAMBDA_URL_HERE';
```

## 📊 Monitoring Demo Usage

Track how many times the demo is triggered:

```bash
# View ingestor logs
aws logs tail /aws/lambda/dev-mcp-first-responder-ingestor --follow

# Count demo alerts in last hour
aws logs filter-pattern --log-group-name /aws/lambda/dev-mcp-first-responder-ingestor \
  --filter-pattern "demo-web-page" \
  --start-time $(date -v-1H +%s)000
```

## 🐛 Troubleshooting

### CORS Error in Browser

```
Access to fetch at '...' has been blocked by CORS policy
```

**Solution:** CORS is already configured in Terraform. Redeploy:
```bash
terraform apply -var-file=environments/dev.tfvars
```

### Lambda Returns 403

**Possible causes:**
- Function URL not enabled
- Authorization type is not NONE

**Check:**
```bash
aws lambda get-function-url-config \
  --function-name dev-mcp-first-responder-ingestor
```

### Demo works but no Slack message

**Check pipeline:**
```bash
# 1. Check processing queue has messages
terraform output check_queue_depth | bash

# 2. Check analyzer logs
terraform output view_logs_analyzer | bash

# 3. Check distribution queue
aws sqs get-queue-attributes \
  --queue-url $(terraform output -raw distribution_queue_url) \
  --attribute-names ApproximateNumberOfMessagesVisible
```

## 🎓 Next Steps

- **Add Analytics:** Track button clicks with Google Analytics
- **Add Rate Limiting:** Implement client-side throttling
- **Add Loading Indicators:** Show spinner while waiting
- **Add Success Message:** Display confirmation after alert sent

## 📚 Related Documentation

- [Terraform Setup](../TERRAFORM_QUICKSTART.md)
- [Main README](../README.md)
- [CLAUDE.md](../CLAUDE.md) - Full project documentation

---

**Questions?** Check the main README or open an issue on GitHub.
